"""组合回测引擎：多标的、按目标权重调仓。

与单标的 engine.py 的关系（保真度 vs 复杂度的取舍，也是教学点）：
- engine.py 精确到"股"，一手一手地模拟成交 —— 单标的策略用它
- 本引擎以"目标权重"为语言，份额允许小数 —— 月度轮动这类低频组合策略用它。
  100 万资金、几元一股的 ETF，一手(100股)颗粒度误差 <0.01%，近似完全够用，
  而代码量只有一半。

同样遵守铁律：t 日收盘算出权重，t+1 日开盘调仓（内部对 weights 做 shift(1)）。
调仓触发：任一标的"目标权重 − 当前权重"超过阈值（默认 0.5%）才动，避免每天微调。
涨跌停：开盘接近涨停的标的当日不买入、接近跌停不卖出，目标不变则次日自动重试。
（简化：组合引擎不记录被挡下的流水，也不模拟一手整数——单标的引擎里有精确版。）
"""

from __future__ import annotations

import pandas as pd

from .engine import CostModel

REBALANCE_TOL = 0.005  # 权重变化超过 0.5% 才调仓


class PortfolioEngine:
    """多标的权重回测引擎。用法：
        engine = PortfolioEngine(cost=CostModel(stamp_tax_rate=0.0))  # ETF组合免印花税
        equity, trades = engine.run(panel, weights, limit_pct=0.10)

    panel:   {symbol: 日线DataFrame}，所有标的已在同一交易日历上对齐
    weights: DataFrame(date × symbol)，t 行 = t 日收盘后想要的目标权重（每行和 ≤ 1）
    """

    def __init__(self, initial_cash: float = 1_000_000.0, cost: CostModel | None = None):
        self.initial_cash = initial_cash
        self.cost = cost or CostModel()

    def run(
        self,
        panel: dict[str, pd.DataFrame],
        weights: pd.DataFrame,
        limit_pct: float = 0.10,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        syms = list(weights.columns)
        opens = pd.DataFrame({s: panel[s]["open"] for s in syms}).reindex(weights.index)
        closes = pd.DataFrame({s: panel[s]["close"] for s in syms}).reindex(weights.index)
        prev_closes = closes.shift(1)
        exec_w = weights.shift(1).fillna(0.0)   # 防前视：今天执行昨天收盘的权重
        cost = self.cost

        cash = self.initial_cash
        hold = pd.Series(0.0, index=syms)       # 各标的持仓份额（允许小数）
        ledger: list[dict] = []
        trades: list[dict] = []

        def _trade(date, s, action, price, shares, fee, cash_after):
            trades.append({
                "date": date, "symbol": s, "action": action, "price": round(price, 4),
                "shares": round(shares, 2), "amount": round(shares * price, 2),
                "cost": round(fee, 2), "cash_after": round(cash_after, 2),
            })

        for date in exec_w.index:
            o, c, pc = opens.loc[date], closes.loc[date], prev_closes.loc[date]
            tw = exec_w.loc[date]
            if o.isna().any() or c.isna().any():
                continue  # 对齐缺陷保护：缺价格的日子跳过（正常不会发生）

            equity_open = cash + float((hold * o).sum())
            if equity_open <= 0:
                break
            cur_w = hold * o / equity_open

            # 开盘涨跌停判定（首日无昨收 → NaN 比较为 False → 视为可交易）
            open_ret = o / pc - 1
            blocked_buy = open_ret >= limit_pct * 0.98
            blocked_sell = open_ret <= -limit_pct * 0.98

            delta = tw - cur_w
            todo = delta.abs() > REBALANCE_TOL
            if todo.any():
                target_hold = tw * equity_open / o
                # 先卖后买（先回收现金）
                for s in syms:
                    if todo[s] and target_hold[s] < hold[s] and not blocked_sell[s]:
                        dn = hold[s] - target_hold[s]
                        price = o[s] * (1 - cost.slippage_rate)
                        amount = dn * price
                        fee = cost.sell_cost(amount)
                        cash += amount - fee
                        hold[s] = target_hold[s]
                        _trade(date, s, "SELL", price, dn, fee, cash)
                for s in syms:
                    if todo[s] and target_hold[s] > hold[s] and not blocked_buy[s]:
                        dn = target_hold[s] - hold[s]
                        price = o[s] * (1 + cost.slippage_rate)
                        if dn * price > cash:            # 费用吃掉零头时的保护
                            dn = max(cash, 0.0) / price
                        if dn <= 0:
                            continue
                        amount = dn * price
                        fee = cost.buy_cost(amount)
                        cash -= amount + fee
                        hold[s] += dn
                        _trade(date, s, "BUY", price, dn, fee, cash)

            equity_close = cash + float((hold * c).sum())
            row = {"date": date, "cash": cash, "equity": equity_close}
            for s in syms:
                row[f"w_{s}"] = hold[s] * c[s] / equity_close if equity_close > 0 else 0.0
            ledger.append(row)

        equity_df = pd.DataFrame(ledger).set_index("date")
        equity_df["ret"] = equity_df["equity"].pct_change()
        trades_df = pd.DataFrame(
            trades, columns=["date", "symbol", "action", "price", "shares", "amount", "cost", "cash_after"])
        return equity_df, trades_df
