"""策略3：布林带均值回归 —— "跌深了买，回到均值卖"。

规则（一句话）：收盘价低于 20 日均线减 2 倍标准差（超卖区）→ 次日买入；
回升穿越 20 日均线（回到中枢）→ 次日清仓。

金融直觉：震荡市里价格围绕均值来回摆动，恐慌性超卖往往会被拉回 ——
低买高卖的机械化版本。它是趋势策略的镜像对手：趋势策略赚"延续"的钱，
均值回归赚"反转"的钱。

必须提前知道的死法（回测会展示）：单边下跌里"跌深"可以更深，
每一次"看起来够便宜了"都只是半山腰 —— 俗称"接飞刀"。
均值回归适合高波动、强周期、无长期趋势的标的（如券商ETF），
不适合长牛股（每一次回调都是上车机会，但你会早早下车）。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from quant import indicators as ind
from quant import metrics as met
from quant.datasource import UNIVERSE
from quant.plotting import plot_backtest
from quant.preprocess import load_bars
from strategies.s1_ma_cross import make_engine

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"


def generate_target(bars: pd.DataFrame, n: int = 20, k: float = 2.0) -> pd.Series:
    """行情 → 目标仓位。z 值 = (收盘 − n日均线) / n日标准差。

    这是"状态机"式信号的向量化写法：入场事件(z < −k)记 1，
    离场事件(z ≥ 0)记 0，其余日子沿用上一个状态(ffill)——
    比逐日循环简洁且不可能引入未来数据。
    """
    ma_s = ind.ma(bars["close"], n)
    std = bars["close"].rolling(n).std()
    z = (bars["close"] - ma_s) / std

    sig = pd.Series(float("nan"), index=bars.index)
    sig[z < -k] = 1.0    # 跌入超卖区 → 想持有
    sig[z >= 0] = 0.0    # 回到均值之上 → 想离场
    return sig.ffill().fillna(0.0)


def run(
    symbol: str = "512880",
    n: int = 20,
    k: float = 2.0,
    start: str = "2015-01-01",
    end: str | None = None,
    refresh: bool = False,
) -> dict:
    """默认在券商ETF上跑（高波动强周期，均值回归的主场），另跑 510300 做对照。"""
    meta = UNIVERSE[symbol]
    bars = load_bars(symbol, meta["kind"], start, end, refresh)
    target = generate_target(bars, n, k)
    engine = make_engine(symbol)

    equity, trades = engine.run(bars, target, limit_pct=meta["limit_pct"])
    bh_equity, _ = engine.run_buy_hold(bars, limit_pct=meta["limit_pct"])
    stats = met.compute(equity["equity"], trades)
    bh_stats = met.compute(bh_equity["equity"])

    title = f"S3 均值回归(BOLL {n}日 ±{k:g}σ) · {meta['name']}({symbol})"
    out = RESULTS_DIR / "s3_mean_revert" / symbol
    out.mkdir(parents=True, exist_ok=True)
    equity.to_csv(out / "equity.csv", encoding="utf-8-sig")
    if trades is not None and len(trades):
        trades.to_csv(out / "trades.csv", index=False, encoding="utf-8-sig")
    plot_backtest(
        equity["equity"], benchmark=bh_equity["equity"],
        trades=trades, title=title, save_path=out / "chart.png",
    )

    report = (
        met.format_report(stats, title)
        + "\n\n--- 基准：同标的买入持有 ---\n"
        + met.format_report(bh_stats)
    )
    (out / "report.txt").write_text(report, encoding="utf-8")
    print(report)
    return stats
