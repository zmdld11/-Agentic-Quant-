"""回测引擎 v0.1 —— 单标的、全仓/空仓切换。

这就是整个项目的"模拟器"：给它一段日线行情和一个目标仓位序列，
它模拟出一个真实交易者在 A 股会遇到的所有限制，返回每天的钱和每一笔交易。

核心原则（量化的第一课，结构上强制保证）：
1. 防前视偏差：策略在第 t 天【收盘后】算出目标仓位 target[t]，
   引擎最早在第 t+1 天的开盘价成交。决策用的信息永远早于成交的价格。
   你在回测里"看到"收盘价才决定今天收盘买入，实盘根本做不到。
2. 模拟 A 股现实约束：
   - 100 股一手：买卖必须是 100 股的整数倍
   - T+1：今天买入的股票，最早明天才能卖
   - 涨跌停：开盘相对昨收涨幅接近涨停 → 买不进；接近跌停 → 卖不出
     （简化：按开盘价判断，无法成交就顺延，信号不变则次日继续尝试）
   - 交易成本：佣金（万 2.5，最低 5 元）+ 卖出印花税（个股 0.05%，ETF 免）+ 滑点
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class CostModel:
    """交易成本参数。滑点是成交价与你看到的价的差距，小资金按 0.1% 估。"""
    commission_rate: float = 2.5e-4   # 佣金 万分之2.5
    min_commission: float = 5.0       # 单笔最低佣金 5 元
    stamp_tax_rate: float = 5e-4      # 印花税：仅卖出收，个股 0.05%，ETF 免（传 0）
    slippage_rate: float = 1e-3       # 滑点：买入价上浮/卖出价下压 0.1%

    def buy_cost(self, amount: float) -> float:
        return max(amount * self.commission_rate, self.min_commission)

    def sell_cost(self, amount: float) -> float:
        return self.buy_cost(amount) + amount * self.stamp_tax_rate


class BacktestEngine:
    """单标的回测引擎。用法：
        engine = BacktestEngine()  # 初始资金默认100万（配合后复权价格的一手门槛）
        equity, trades = engine.run(bars, target, limit_pct=0.10)
    """

    def __init__(self, initial_cash: float = 1_000_000.0, cost: CostModel | None = None):
        self.initial_cash = initial_cash
        self.cost = cost or CostModel()

    def run(
        self,
        bars: pd.DataFrame,
        target: pd.Series,
        limit_pct: float = 0.10,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """跑回测。

        bars:   日线，DatetimeIndex + open/high/low/close 列
        target: 目标仓位序列（1=想满仓，0=想空仓），t 日的值代表
                【t 日收盘后】根据当时信息做出的决定
        limit_pct: 涨跌停幅度：主板/ETF 10%，创业板/科创板 20%

        返回 (equity, trades)：
        equity  每日账本：close/position/shares/cash/equity
        trades  交易流水：date/action/price/shares/amount/cost/cash_after，
                以及被涨跌停/T+1 挡下的 SKIP_BUY/SKIP_SELL（cost=0，只做记录）
        """
        # 关键一步：今天执行的是【昨天收盘后】算出的信号 —— 防前视偏差
        exec_target = target.shift(1)
        cost = self.cost

        cash = self.initial_cash
        shares = 0
        last_buy_i = -1          # T+1 检查：记住最后一笔买入发生在第几行
        prev_close: float | None = None
        ledger: list[dict] = []
        trades: list[dict] = []

        for i, (date, bar) in enumerate(bars.iterrows()):
            open_price = float(bar["open"])

            # 用开盘价相对昨收的涨幅近似判断涨跌停（一字板必无成交，普通板简化处理）
            can_buy, can_sell = True, True
            if prev_close is not None:
                open_ret = open_price / prev_close - 1
                if open_ret >= limit_pct * 0.98:
                    can_buy = False
                if open_ret <= -limit_pct * 0.98:
                    can_sell = False

            want = exec_target.iloc[i]   # 昨天收盘后想要的仓位（首日为 NaN → 不动）
            want = 0 if pd.isna(want) else int(want)

            def _trade(action, price, n, fee, cash_after, reason=""):
                trades.append({
                    "date": date, "action": action, "price": round(price, 3),
                    "shares": n, "amount": round(n * price, 2),
                    "cost": round(fee, 2), "cash_after": round(cash_after, 2),
                    "reason": reason,
                })

            if want == 1 and shares == 0 and not pd.isna(exec_target.iloc[i]):
                # 目标满仓而当前空仓 → 以开盘价(加滑点)全仓买入
                if not can_buy:
                    _trade("SKIP_BUY", open_price, 0, 0.0, cash, "开盘涨停，买不进")
                else:
                    p = open_price * (1 + cost.slippage_rate)
                    lots = int(cash // (p * 100))       # A股一手100股
                    if lots >= 1:
                        n = lots * 100
                        amount = n * p
                        fee = cost.buy_cost(amount)
                        cash -= amount + fee
                        shares = n
                        last_buy_i = i
                        _trade("BUY", p, n, fee, cash)
                    else:
                        _trade("SKIP_BUY", open_price, 0, 0.0, cash, "现金不足一手")

            elif want == 0 and shares > 0:
                # 目标空仓而当前持仓 → 以开盘价(减滑点)全部卖出
                if i == last_buy_i:
                    _trade("SKIP_SELL", open_price, shares, 0.0, cash, "T+1：当日买入不可卖")
                elif not can_sell:
                    _trade("SKIP_SELL", open_price, shares, 0.0, cash, "开盘跌停，卖不出")
                else:
                    p = open_price * (1 - cost.slippage_rate)
                    amount = shares * p
                    fee = cost.sell_cost(amount)
                    cash += amount - fee
                    _trade("SELL", p, shares, fee, cash)
                    shares = 0

            equity = cash + shares * float(bar["close"])
            ledger.append({
                "date": date, "close": float(bar["close"]),
                "position": 1 if shares > 0 else 0, "shares": shares,
                "cash": cash, "equity": equity,
            })
            prev_close = float(bar["close"])

        equity_df = pd.DataFrame(ledger).set_index("date")
        equity_df["ret"] = equity_df["equity"].pct_change()
        trades_df = pd.DataFrame(trades)
        return equity_df, trades_df

    def run_buy_hold(self, bars: pd.DataFrame, limit_pct: float = 0.10
                     ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """基准：第一天全仓买入后一直拿着。策略打得过它才值得讨论。"""
        target = pd.Series(1, index=bars.index)
        return self.run(bars, target, limit_pct)
