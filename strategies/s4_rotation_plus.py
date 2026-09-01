"""策略4：动量轮动 + 波动率目标仓位 —— S2 的"风险预算"升级版。

S2 的问题（见实验记录）：收益不错，但回撤没降 —— 2022 年危机时池内资产
一起跌，轮动无处可躲。本策略加一层**仓位管理**：

规则：仍是月末选 21 日动量最强的 ETF，但仓位不是全仓，而是
    仓位 = min(1, 目标波动率 / 该ETF近期实际波动率)
即"每年愿意承受 ~15% 的波动，资产越颠簸就买越少，省下的钱持币"。

金融直觉：波动率有聚集性（GARCH 效应）——刚发生过大波动的资产，
接下来大概率还是大波动。用已实现波动率缩放仓位，等于在风暴来临前
自动减仓。它不能预测方向，但能管理"颠簸程度"，直接压回撤和卡玛。

对照：S2（全仓轮动） vs S4（波动率目标轮动） vs 沪深300 买入持有。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from quant import metrics as met
from quant.datasource import UNIVERSE
from quant.engine import BacktestEngine, CostModel
from quant.plotting import plot_backtest
from quant.portfolio import PortfolioEngine
from strategies.s2_momentum import ROTATION_POOL, build_panel

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"


def generate_weights(
    panel: dict[str, pd.DataFrame],
    lookback: int = 21,
    vol_window: int = 60,
    target_vol: float = 0.15,
) -> pd.DataFrame:
    """月末选动量最强者，按 目标波动/实际波动 缩放仓位（波动率目标）。"""
    closes = pd.DataFrame({s: df["close"] for s, df in panel.items()})
    mom = closes / closes.shift(lookback) - 1
    # 年化已实现波动率：日收益标准差 × √252
    vols = closes.pct_change().rolling(vol_window).std() * np.sqrt(252)

    month_last = set(closes.index.to_series().groupby(closes.index.to_period("M")).max())
    weights = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    current: dict[str, float] = {}
    for date in closes.index:
        if date in month_last:
            row = mom.loc[date].dropna()
            current = {}
            if len(row):
                top = row.nlargest(1)
                s = top.index[0]
                if top.iloc[0] > 0:          # 绝对动量过滤：最强者也在跌就持币
                    v = vols.loc[date, s]
                    current = {s: min(1.0, target_vol / v) if v and v > 0 else 0.0}
        for s, w in current.items():
            weights.loc[date, s] = w
    return weights


def run(lookback: int = 21, vol_window: int = 60, target_vol: float = 0.15,
        refresh: bool = False) -> dict:
    panel = build_panel(refresh=refresh)
    weights = generate_weights(panel, lookback, vol_window, target_vol)

    engine = PortfolioEngine(cost=CostModel(stamp_tax_rate=0.0))
    equity, trades = engine.run(panel, weights, limit_pct=0.10)

    # 对照1：S2 全仓轮动；对照2：沪深300 买入持有
    from strategies.s2_momentum import generate_weights as s2_weights
    s2_eq, s2_tr = engine.run(panel, s2_weights(panel, lookback), limit_pct=0.10)
    bh_engine = BacktestEngine(cost=CostModel(stamp_tax_rate=0.0))
    bh_equity, _ = bh_engine.run_buy_hold(panel["510300"], limit_pct=0.10)

    stats = met.compute(equity["equity"], trades)
    s2_stats = met.compute(s2_eq["equity"], s2_tr)
    bh_stats = met.compute(bh_equity["equity"])

    title = f"S4 波动率目标轮动(动量{lookback}日, 目标波动{target_vol:.0%})"
    out = RESULTS_DIR / "s4_vol_target"
    out.mkdir(parents=True, exist_ok=True)
    equity.to_csv(out / "equity.csv", encoding="utf-8-sig")
    trades.to_csv(out / "trades.csv", index=False, encoding="utf-8-sig")
    plot_backtest(
        equity["equity"], benchmark=s2_eq["equity"],
        benchmark_label="对照：S2全仓轮动",
        trades=trades, title=title, save_path=out / "chart.png",
    )
    plot_backtest(
        equity["equity"], benchmark=bh_equity["equity"],
        benchmark_label="对照：沪深300ETF买入持有",
        trades=trades, title=title, save_path=out / "chart_vs300.png",
    )

    report = (
        met.format_report(stats, title)
        + "\n\n--- 对照：S2 全仓轮动 ---\n"
        + met.format_report(s2_stats)
        + "\n\n--- 对照：沪深300ETF 买入持有 ---\n"
        + met.format_report(bh_stats)
    )
    (out / "report.txt").write_text(report, encoding="utf-8")
    print(report)
    return {"equity": equity, "stats": stats}
