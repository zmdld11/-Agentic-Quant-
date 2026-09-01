"""滚动样本外验证（walk-forward）：比单次训练/测试分割更接近实战的检验。

单次分割的问题：测试集只有一段历史，结论运气成分大。
walk-forward 模拟真实时间流：
    用过去 5 年数据选参数 → 只用选出的参数交易【下一年】 → 滚动推进
    2020: 用 2015-2019 选参 → 交易 2020
    2021: 用 2016-2020 选参 → 交易 2021
    ...每年都在"只能看到过去"的约束下决策，把各年样本外收益拼起来，
    得到的净值才是这套流程（策略+选参方法）的真实样本外成绩。

同时对照：全程只用固定默认参数 5/60 —— 如果"每年重新选最优"打不过
"从头到尾不选"，就再次证明选参环节没有附加值。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from quant import metrics as met
from quant import scan
from quant.datasource import UNIVERSE
from quant.plotting import plot_backtest
from quant.preprocess import load_bars
from strategies.s1_ma_cross import make_engine

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"

WF_FIRST_YEAR = 2020   # 训练窗口5年 → 最早可测2020
WF_LAST_YEAR = 2026
TRAIN_YEARS = 5
WARMUP_START = "{y}-07-01"  # 回看一年半给 MA250 热身


def run_walkforward(symbol: str = "510300", refresh: bool = False) -> pd.DataFrame:
    meta = UNIVERSE[symbol]
    chosen_rows = []
    wf_segments, default_segments = [], []

    for y in range(WF_FIRST_YEAR, WF_LAST_YEAR + 1):
        train_start = f"{y - TRAIN_YEARS}-01-01"
        train_end = f"{y - 1}-12-31"
        grid = scan.run_grid(symbol, train_start, None, train_end)
        best = grid.loc[grid["夏普比率"].idxmax()]
        s, l = int(best["short"]), int(best["long"])
        chosen_rows.append({
            "测试年": y,
            "训练区间": f"{y - TRAIN_YEARS}-{y - 1}",
            "训练集选出": f"MA{s}/{l}", "训练夏普": f"{best['夏普比率']:+.2f}",
        })

        # 引擎从上一年7月启动（给MA250热身并带仓位入1月），绩效只统计测试年
        run_start = WARMUP_START.format(y=y - 1)
        end = f"{y}-12-31" if y < WF_LAST_YEAR else None
        wf_seg = scan.backtest_period(symbol, s, l, run_start, None, end)["equity"]["equity"]
        def_seg = scan.backtest_period(symbol, 5, 60, run_start, None, end)["equity"]["equity"]
        wf_segments.append(wf_seg.loc[f"{y}-01-01":])
        default_segments.append(def_seg.loc[f"{y}-01-01":])

    # 各年样本外净值首尾相接复合
    def compound(segments: list[pd.Series]) -> pd.Series:
        total = segments[0]
        for seg in segments[1:]:
            total = pd.concat([total, seg / seg.iloc[0] * total.iloc[-1]])
        return total

    wf_eq = compound(wf_segments)
    def_eq = compound(default_segments)

    bars = load_bars(symbol, meta["kind"], f"{WF_FIRST_YEAR - 2}-07-01", None, refresh)
    bh_equity, _ = make_engine(symbol).run_buy_hold(bars, limit_pct=meta["limit_pct"])
    bh_eq = bh_equity["equity"].loc[f"{WF_FIRST_YEAR}-01-01":]

    wf_stats = met.compute(wf_eq)
    def_stats = met.compute(def_eq)
    bh_stats = met.compute(bh_eq)

    out = RESULTS_DIR / "walkforward" / symbol
    out.mkdir(parents=True, exist_ok=True)
    chosen_df = pd.DataFrame(chosen_rows)
    chosen_df.to_csv(out / "chosen_params.csv", index=False, encoding="utf-8-sig")
    wf_eq.to_csv(out / "equity_walkforward.csv", encoding="utf-8-sig")

    plot_backtest(
        wf_eq, benchmark=def_eq, benchmark_label="对照：固定参数 MA5/60",
        title=f"Walk-Forward 滚动样本外 · 每年用过去{TRAIN_YEARS}年重选参数 · {meta['name']}({symbol})",
        save_path=out / "chart.png",
    )
    plot_backtest(
        wf_eq, benchmark=bh_eq, benchmark_label="对照：买入持有",
        title=f"Walk-Forward vs 买入持有 · {meta['name']}({symbol}) 2020-2026",
        save_path=out / "chart_vs_bh.png",
    )

    report = (
        "每年选出的参数（不稳定本身就是结论）：\n" + chosen_df.to_string(index=False)
        + "\n\n" + met.format_report(wf_stats, "Walk-Forward 样本外净值")
        + "\n\n--- 对照：固定参数 MA5/60（全程不选参） ---\n" + met.format_report(def_stats)
        + "\n\n--- 对照：买入持有 ---\n" + met.format_report(bh_stats)
    )
    (out / "report.txt").write_text(report, encoding="utf-8")
    print(report)
    return chosen_df
