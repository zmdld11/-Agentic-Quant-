"""策略6：网格交易 —— 波动率收割机，趋势粉碎机。

规则（一句话）：在价格区间上画 N 条格线，价格每跌穿一条线买入一份，
每涨穿一条线卖出一份，赚"震荡往返"的钱。

它是唯一一个"不需要观点"的策略：不预测方向，只收割波动。
代价是两种经典死法（本策略会原样演给你看）：
    跌破网格下界 → 满仓套牢，没钱继续补
    涨破网格上界 → 空仓踏空，眼看着涨

诚实设定（不做任何优化）：
- 网格上下界 = 校准期（前244个交易日）的最高/最低价，之后永不重算
  ——校准期即训练集，之后全是样本外，和调参考古完全不同
- 等份网格：总资金分 N+1 份；起始日买入"上方格数"份
  （涨一格有货可卖、跌一格有钱可买）
- 日线模拟：用当日 [low, high] 判断穿越了哪些格线，成交价=格线价。
  日内先跌后涨还是先涨后跌无法从日线分辨，本模拟保守地先处理买入，
  且当日买入受 T+1 限制不可卖——两者都倾向于低估网格收益，宁可少算
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from quant import metrics as met
from quant.datasource import UNIVERSE
from quant.engine import CostModel
from quant.plotting import plot_backtest
from quant.preprocess import load_bars

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
CALIB_DAYS = 244  # 一年交易日做校准


def run_grid(
    bars: pd.DataFrame,
    n_grids: int = 20,
    initial_cash: float = 1_000_000.0,
    cost: CostModel | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """在给定日线数据上跑网格。返回 (每日账本, 交易流水, 网格参数)。"""
    cost = cost or CostModel()
    cal = bars.iloc[:CALIB_DAYS]
    p_low, p_high = float(cal["low"].min()), float(cal["high"].max())
    step = (p_high - p_low) / n_grids
    if step <= 0:
        raise ValueError("校准期无价格区间，无法建网格")

    bars = bars.iloc[CALIB_DAYS:]           # 校准期之后才是"交易期"（样本外）
    unit_cash = initial_cash / (n_grids + 1)
    cash = initial_cash
    shares = 0

    def level_idx(p: float) -> int:
        return max(0, min(n_grids, int((p - p_low) / step)))

    def lots(price: float, budget: float) -> int:
        """按预算买得起的股数（向下取整到100股的整数倍）。"""
        return int(min(unit_cash, budget) / (price * 100)) * 100

    ledger, trades = [], []

    def _buy(date, price, n) -> bool:
        nonlocal cash, shares
        amount = n * price
        fee = cost.buy_cost(amount)
        if amount + fee > cash or n < 100:
            return False
        cash -= amount + fee
        shares += n
        trades.append({"date": date, "action": "BUY", "price": round(price, 4),
                       "shares": n, "amount": round(amount, 2),
                       "cost": round(fee, 2), "cash_after": round(cash, 2)})
        return True

    def _sell(date, price, n) -> bool:
        nonlocal cash, shares
        n = min(n, shares)
        if n <= 0:
            return False
        amount = n * price
        fee = cost.sell_cost(amount)
        cash += amount - fee
        shares -= n
        trades.append({"date": date, "action": "SELL", "price": round(price, 4),
                       "shares": n, "amount": round(amount, 2),
                       "cost": round(fee, 2), "cash_after": round(cash, 2)})
        return True

    prev_i = None
    for date, bar in bars.iterrows():
        bought_today = False
        if prev_i is None:
            # 起始建仓：买入"上方格数"份，涨一格有货卖、跌一格有钱补
            price0 = float(bar["close"])
            for _ in range(n_grids - level_idx(price0)):
                if not _buy(date, price0, lots(price0, cash)):
                    break
                bought_today = True
        else:
            hi_i, lo_i = level_idx(float(bar["high"])), level_idx(float(bar["low"]))
            # ① 下跌穿越：从紧邻下方那条格线起，每线买一份
            for k in range(prev_i - 1, lo_i - 1, -1):
                price = p_low + k * step
                if _buy(date, price, lots(price, cash)):
                    bought_today = True
            # ② 上涨穿越：每线卖一份（当日买入的受 T+1 限制不可卖）
            if not bought_today:
                for k in range(prev_i + 1, hi_i + 1):
                    price = p_low + k * step
                    n = max(lots(price, unit_cash), 100)
                    _sell(date, price, n)

        equity = cash + shares * float(bar["close"])
        ledger.append({"date": date, "close": float(bar["close"]),
                       "shares": shares, "cash": cash, "equity": equity})
        prev_i = level_idx(float(bar["close"]))

    equity_df = pd.DataFrame(ledger).set_index("date")
    equity_df["ret"] = equity_df["equity"].pct_change()
    trades_df = pd.DataFrame(trades)
    info = {"p_low": p_low, "p_high": p_high, "n_grids": n_grids, "step": step,
            "calibration_until": str(bars.index[0].date())}
    return equity_df, trades_df, info


def run(symbol: str = "512880", n_grids: int = 20, refresh: bool = False) -> dict:
    """跑网格并落盘：全期 + 前后半场拆分（看震荡市/趋势市的表现差）。"""
    meta = UNIVERSE[symbol]
    bars = load_bars(symbol, meta["kind"], start="2015-01-01", refresh=refresh)
    cost = CostModel(stamp_tax_rate=0.0 if meta["kind"] == "etf" else 5e-4)
    equity, trades, info = run_grid(bars, n_grids=n_grids, cost=cost)

    # 基准：同区间买入持有
    from strategies.s1_ma_cross import make_engine
    bh_equity, _ = make_engine(symbol).run_buy_hold(
        bars.iloc[CALIB_DAYS:], limit_pct=meta["limit_pct"])

    stats = met.compute(equity["equity"], trades if len(trades) else None)
    bh_stats = met.compute(bh_equity["equity"])

    # 前后半场：同一策略在不同市场结构下的命运
    mid = equity.index[len(equity) // 2]
    half1 = met.compute(equity["equity"].loc[:mid])
    half2 = met.compute(equity["equity"].loc[mid:])

    out = RESULTS_DIR / "s6_grid" / symbol
    out.mkdir(parents=True, exist_ok=True)
    equity.to_csv(out / "equity.csv", encoding="utf-8-sig")
    if len(trades):
        trades.to_csv(out / "trades.csv", index=False, encoding="utf-8-sig")
    plot_backtest(equity["equity"], benchmark=bh_equity["equity"],
                  trades=trades if len(trades) else None,
                  title=f"S6 网格({n_grids}格) · {meta['name']}({symbol})",
                  save_path=out / "chart.png")

    report = (
        f"网格区间: {info['p_low']:.3f} ~ {info['p_high']:.3f}（校准期高低点，之后固定）\n"
        + met.format_report(stats, f"S6 网格 · {meta['name']}({symbol})")
        + f"\n\n--- 前半场 ({equity.index[0].date()} ~ {mid.date()}) ---\n"
        + met.format_report(half1)
        + f"\n\n--- 后半场 ({mid.date()} ~ {equity.index[-1].date()}) ---\n"
        + met.format_report(half2)
        + "\n\n--- 基准：买入持有 ---\n" + met.format_report(bh_stats)
    )
    (out / "report.txt").write_text(report, encoding="utf-8")
    print(report)
    return {"equity": equity, "stats": stats}
