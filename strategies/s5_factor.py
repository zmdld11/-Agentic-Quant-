"""策略5：横截面多因子选股 —— 本项目第一个"机构味"策略。

流程（标准多因子研究三步）：
1. IC 检验：因子分对下月收益有没有预测力（先问"有没有信号"）
2. 分组回测：按因子分5组，收益是否单调（再问"信号能不能落地"）
3. 组合回测：三因子 z-score 合成，月度持有 Top30，对比全池等权和沪深300

诚实声明（写进报告）：
- 成分股是【今天】的沪深300名单 → 幸存者偏差，绝对收益高估
- "哪个因子进合成"是看过全区间表现后定的 → 轻度过拟合（下一课的素材）
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from quant import factors as fac
from quant import metrics as met
from quant.plotting import plot_lines

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
START = "2019-01-01"


def run(topn: int = 30, cost: float = 0.0015, refresh: bool = False) -> dict:
    closes = fac.load_closes()
    out = RESULTS_DIR / "s5_factor"
    out.mkdir(parents=True, exist_ok=True)

    # --- 1. IC 检验 ---
    ic_df = fac.compute_ics(closes, start=START)
    ic_df.to_csv(out / "ic_series.csv", encoding="utf-8-sig")
    summary = fac.ic_summary(ic_df)
    summary.to_csv(out / "ic_summary.csv", index=False, encoding="utf-8-sig")

    # 累计IC曲线：斜率=平均IC，一眼看出哪个因子持续有预测力
    plot_lines(
        {name: ic_df[name].dropna().cumsum() for name in ic_df.columns},
        title="累计IC（斜率=平均IC，>0 因子有效） · 沪深300成分股 月频 2019-2026",
        ylabel="累计IC", save_path=out / "chart_ic_cum.png")

    # --- 2. 分组回测（每个因子一张图，看单调性） ---
    month_factors = fac.month_end_factors(closes)
    quantile_curves = {}
    for name, f in month_factors.items():
        q = fac.quantile_backtest(closes, f, start=START, cost_one_way=cost)
        last = f"Q{q.shape[1]}"
        q.columns = [
            f"{name}·Q1(因子最高)" if c == "Q1"
            else (f"{name}·{last}(因子最低)" if c == last else f"{name}·{c}")
            for c in q.columns
        ]
        quantile_curves[name] = q
        q.to_csv(out / f"quantile_{name}.csv", encoding="utf-8-sig")
        plot_lines(dict(zip(q.columns, [q[c] for c in q.columns])),
                   title=f"分组回测 · {name} · 月度调仓(单边成本{cost:.2%})",
                   save_path=out / f"chart_quantile_{name}.png")

    # --- 3. 合成因子 Top-N 组合 ---
    score = fac.composite_score(closes)
    curves = fac.topn_monthly_backtest(closes, score, topn=topn, start=START, cost_one_way=cost)
    # 基准：沪深300指数（月频）
    idx = pd.read_parquet(Path(fac.DATA_DIR) / "index_000300.parquet")["close"]
    idx_m = idx.resample("ME").last().loc[START:]
    idx_curve = idx_m / idx_m.iloc[0]
    idx_curve.index = idx_curve.index + pd.offsets.MonthEnd(0)
    curves["沪深300指数"] = idx_curve.reindex(curves.index).ffill()
    curves.to_csv(out / "strategy_equity.csv", encoding="utf-8-sig")

    stats = met.compute(curves.iloc[:, 0], periods_per_year=12)
    ew_stats = met.compute(curves["全池等权"], periods_per_year=12)
    idx_stats = met.compute(curves["沪深300指数"], periods_per_year=12)

    plot_lines({c: curves[c] for c in curves.columns},
               title=f"S5 三因子合成 · 月度持有Top{topn} vs 全池等权 vs 沪深300",
               save_path=out / "chart_strategy.png")

    report = (
        "【IC 检验】因子分 vs 下月收益（Spearman秩相关，月频）\n"
        + summary.to_string(index=False,
                            formatters={"IC均值": "{:+.4f}".format, "IC标准差": "{:.4f}".format,
                                        "ICIR": "{:+.2f}".format, "t值": "{:+.1f}".format,
                                        "IC>0占比": "{:.0%}".format})
        + f"\n\n【组合回测】月度 Top{topn} 等权，单边成本 {cost:.2%}（2019-01 起）\n"
        + met.format_report(stats, f"策略 Top{topn}")
        + "\n\n--- 基准：全池等权(同再平衡同费率) ---\n" + met.format_report(ew_stats)
        + "\n\n--- 基准：沪深300指数 ---\n" + met.format_report(idx_stats)
        + "\n\n【诚实声明】成分股为当前名单(幸存者偏差,绝对收益偏高估)；"
          "因子合成权重未做样本外验证(轻度过拟合)。"
    )
    (out / "report.txt").write_text(report, encoding="utf-8")
    print(report)
    return {"ic": summary, "curves": curves, "stats": stats}
