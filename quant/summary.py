"""全项目策略总览：把所有跑过的策略放到同一时间窗、同一基准下对比。

公平性说明：
- 统一从"最晚启动策略"的起点开始重定基（S6网格有校准期），
  所有策略在同一窗口、同一成本口径下比较
- S5 因子选股是月频+幸存者偏差严重的股票池，不纳入本图（见其实验记录）
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from quant import metrics as met
from quant.datasource import DATA_DIR
from quant.plotting import plot_lines

RESULTS = Path(__file__).resolve().parent.parent / "results"

# 策略名 → 净值csv（都在 results/ 下，含 equity 列）
STRATEGY_FILES = {
    "S1 双均线(510300)": "s1_ma_cross/510300/equity.csv",
    "S2 ETF动量轮动": "s2_momentum/equity.csv",
    "S3 均值回归(券商ETF)": "s3_mean_revert/512880/equity.csv",
    "S4 波动率目标top1": "s4_vol_target_top1/equity.csv",
    "S4 波动率目标top2": "s4_vol_target_top2/equity.csv",
    "S6 网格(中证500)": "s6_grid/510500/equity.csv",
    "S6 网格(券商)": "s6_grid/512880/equity.csv",
}


def run() -> pd.DataFrame:
    curves = {}
    for name, rel in STRATEGY_FILES.items():
        p = RESULTS / rel
        if not p.exists():
            print(f"跳过（无结果）：{name}，先运行对应策略")
            continue
        s = pd.read_csv(p, index_col=0, parse_dates=True)["equity"].dropna()
        curves[name] = s
    if not curves:
        raise RuntimeError("没有任何策略结果，先跑几个策略")

    # 基准：沪深300指数
    idx = pd.read_parquet(DATA_DIR / "index_000300.parquet")["close"]
    curves["沪深300指数"] = idx

    start = max(s.index[0] for s in curves.values())   # 公共起点
    rebased = {name: (s.loc[start:] / s.loc[start:].iloc[0]) for name, s in curves.items()}

    out = RESULTS / "summary"
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rebased).to_csv(out / "all_curves.csv", encoding="utf-8-sig")

    table = pd.DataFrame({name: met.compute(s) for name, s in rebased.items()}).T
    keep = ["总收益率", "年化收益率", "年化波动率", "夏普比率", "最大回撤", "卡玛比率"]
    table = table[keep]
    table.to_csv(out / "summary.csv", encoding="utf-8-sig")

    plot_lines(rebased, title=f"全策略同窗对比（{start.date()} 起，净值重定基）",
               save_path=out / "chart.png")

    print(f"公共起点 {start.date()}，各策略同窗表现：\n")
    print(table.to_string(formatters={c: "{:+.2%}".format for c in
                                      ["总收益率", "年化收益率", "年化波动率", "最大回撤"]}
                          | {"夏普比率": "{:.2f}".format, "卡玛比率": "{:.2f}".format}))
    print("\n注意：回测收益≠未来收益；各策略均含交易成本；详见 research/ 各实验记录。")
    return table
