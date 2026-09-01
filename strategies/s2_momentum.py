"""策略2：ETF 动量轮动（月度）—— 散户最实用的低频策略原型。

规则（一句话）：每月最后一个交易日收盘后，计算池内各 ETF 过去 ~21 个交易日的
涨幅（动量），下月第一个交易日开盘切换到动量最强的一只（若最强者也在下跌，
则空仓持币）。

金融直觉：「强者恒强」——近期跑赢的资产短期内倾向继续跑赢（动量效应，
几乎所有市场都被反复验证过的现象）。轮动的本质是：永远把钱放在
"最近被市场选出来的赢家"里，同时用"全都不涨就持币"躲过大熊市。

为什么用 ETF 而不是个股：避免个股暴雷/退市风险，且免印花税、费率低。
池子构成刻意跨资产：A股权重(510300) + A股中小盘(510500) + 券商(512880)
+ 黄金(518880) + 纳指(513100) —— 不同资产轮动起来才有意义。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from quant import metrics as met
from quant.datasource import UNIVERSE
from quant.engine import BacktestEngine, CostModel
from quant.plotting import plot_backtest
from quant.portfolio import PortfolioEngine
from quant.preprocess import load_bars

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"

ROTATION_POOL = ["510300", "510500", "512880", "518880", "513100"]


def build_panel(start: str = "2015-01-01", end: str | None = None,
                refresh: bool = False) -> dict[str, pd.DataFrame]:
    """加载池内全部 ETF 并对齐到共同交易日历（512880 2016-08 上市，面板从那时起）。"""
    bars = {s: load_bars(s, UNIVERSE[s]["kind"], start, end, refresh) for s in ROTATION_POOL}
    common = sorted(set.intersection(*(set(df.index) for df in bars.values())))
    return {s: df.loc[common] for s, df in bars.items()}


def generate_weights(panel: dict[str, pd.DataFrame], lookback: int = 21, topk: int = 1) -> pd.DataFrame:
    """行情 → 每日目标权重矩阵。

    只在月末交易日更新持仓选择（月内保持不动，降低换手和过拟合空间）；
    要求入选标的动量为正（强中选强，全负则空仓）。
    """
    closes = pd.DataFrame({s: df["close"] for s, df in panel.items()})
    mom = closes / closes.shift(lookback) - 1

    # 每个自然月的最后一个交易日
    month_last = set(closes.index.to_series().groupby(closes.index.to_period("M")).max())

    weights = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    current: list[str] = []
    for date in closes.index:
        if date in month_last:
            row = mom.loc[date].dropna()
            if len(row):
                top = row.nlargest(topk)
                current = [s for s in top.index if top[s] > 0]
        for s in current:
            weights.loc[date, s] = 1.0 / len(current)
    return weights


def run(lookback: int = 21, topk: int = 1, refresh: bool = False) -> dict:
    """完整回测：动量轮动 vs 沪深300ETF 买入持有。"""
    panel = build_panel(refresh=refresh)
    weights = generate_weights(panel, lookback, topk)

    engine = PortfolioEngine(cost=CostModel(stamp_tax_rate=0.0))
    equity, trades = engine.run(panel, weights, limit_pct=0.10)

    bh_engine = BacktestEngine(cost=CostModel(stamp_tax_rate=0.0))
    bh_equity, _ = bh_engine.run_buy_hold(panel["510300"], limit_pct=0.10)

    stats = met.compute(equity["equity"], trades)
    bh_stats = met.compute(bh_equity["equity"])

    title = f"S2 ETF动量轮动({lookback}日动量, 持有前{topk}) · 2016-08 起"
    out = RESULTS_DIR / "s2_momentum"
    out.mkdir(parents=True, exist_ok=True)
    equity.to_csv(out / "equity.csv", encoding="utf-8-sig")
    trades.to_csv(out / "trades.csv", index=False, encoding="utf-8-sig")
    plot_backtest(
        equity["equity"], benchmark=bh_equity["equity"],
        benchmark_label="基准：沪深300ETF买入持有",
        trades=trades, title=title, save_path=out / "chart.png",
    )

    report = (
        met.format_report(stats, title)
        + "\n\n--- 基准：沪深300ETF 买入持有 ---\n"
        + met.format_report(bh_stats)
    )
    (out / "report.txt").write_text(report, encoding="utf-8")
    print(report)

    # 附：持仓分布——轮动策略把时间花在哪
    w_cols = [c for c in equity.columns if c.startswith("w_")]
    held = (equity[w_cols] > 0.01).sum() / len(equity)
    print("\n持仓时间占比: " + ", ".join(
        f"{UNIVERSE[c[2:]]['name']} {v:.0%}" for c, v in held.items() if v > 0))
    return {"equity": equity, "trades": trades, "stats": stats}
