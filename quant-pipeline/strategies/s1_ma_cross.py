"""策略1：双均线交叉 —— 趋势跟踪的"Hello World"。

规则（一句话）：短期均线在长期均线之上 → 满仓做多；反之 → 清仓空仓。

金融直觉：趋势的形成和结束都需要时间，均线是"用滞后换确定性"的过滤器。
它永远抓不到最低点也逃不掉最高点，但期望是：吃掉趋势的中段，
在漫长的阴跌里保持空仓。它是无数趋势策略的最简原型。

一个必须提前知道的事实：均线参数（5/20、10/60……）怎么选，
回测收益差别巨大 —— 这就是阶段4"参数扫描/过拟合"实验的入口。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from quant import indicators as ind
from quant import metrics as met
from quant.datasource import UNIVERSE
from quant.engine import BacktestEngine, CostModel
from quant.plotting import plot_backtest
from quant.preprocess import load_bars

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"


def generate_target(bars: pd.DataFrame, short: int = 5, long: int = 60) -> pd.Series:
    """行情 → 目标仓位（1=想持有，0=想空仓）。

    均线还没算出来的开头几天，比较结果为 False → 默认空仓，安全侧。
    """
    ma_s = ind.ma(bars["close"], short)
    ma_l = ind.ma(bars["close"], long)
    return (ma_s > ma_l).astype(int)


def make_engine(symbol: str) -> BacktestEngine:
    """按标的类型配置引擎（ETF 免印花税，个股卖出收 0.05%）。"""
    kind = UNIVERSE[symbol]["kind"]
    stamp = 0.0 if kind == "etf" else 5e-4
    return BacktestEngine(cost=CostModel(stamp_tax_rate=stamp))


def backtest(
    symbol: str,
    short: int = 5,
    long: int = 60,
    start: str = "2015-01-01",
    end: str | None = None,
    refresh: bool = False,
) -> dict:
    """只跑回测不落盘，返回 bars/equity/trades/stats —— 参数扫描复用这个。"""
    meta = UNIVERSE[symbol]
    bars = load_bars(symbol, meta["kind"], start, end, refresh)
    target = generate_target(bars, short, long)
    engine = make_engine(symbol)
    equity, trades = engine.run(bars, target, limit_pct=meta["limit_pct"])
    stats = met.compute(equity["equity"], trades)
    return {
        "symbol": symbol, "short": short, "long": long,
        "bars": bars, "equity": equity, "trades": trades, "stats": stats,
    }


def run(
    symbol: str = "510300",
    short: int = 5,
    long: int = 60,
    start: str = "2015-01-01",
    end: str | None = None,
    refresh: bool = False,
) -> dict:
    """完整跑一次并存结果（报告+图+csv）。"""
    res = backtest(symbol, short, long, start, end, refresh)
    meta = UNIVERSE[symbol]
    engine = make_engine(symbol)
    bh_equity, _ = engine.run_buy_hold(res["bars"], limit_pct=meta["limit_pct"])
    bh_stats = met.compute(bh_equity["equity"])

    title = f"S1 双均线({short}/{long}) · {meta['name']}({symbol})"
    out = RESULTS_DIR / "s1_ma_cross" / symbol
    out.mkdir(parents=True, exist_ok=True)
    res["equity"].to_csv(out / "equity.csv", encoding="utf-8-sig")
    if res["trades"] is not None and len(res["trades"]):
        res["trades"].to_csv(out / "trades.csv", index=False, encoding="utf-8-sig")
    plot_backtest(
        res["equity"]["equity"], benchmark=bh_equity["equity"],
        trades=res["trades"], title=title, save_path=out / "chart.png",
    )

    report = (
        met.format_report(res["stats"], title)
        + "\n\n--- 基准：同标的买入持有 ---\n"
        + met.format_report(bh_stats)
    )
    (out / "report.txt").write_text(report, encoding="utf-8")
    print(report)
    return res
