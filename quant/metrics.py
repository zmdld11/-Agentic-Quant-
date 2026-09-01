"""绩效指标：回测赚不赚钱、回撤多深、拿得住吗。

看回测结果的正确顺序：先看最大回撤（能不能拿得住），再看年化收益，
最后才看夏普。只看收益率选策略 = 只看分数不看代价。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252  # A 股一年约 244 个交易日，业界惯例用 252，差别不影响结论


def drawdown_series(equity: pd.Series) -> pd.Series:
    """每天相对历史最高点的回撤（负数）。"""
    return equity / equity.cummax() - 1


def max_drawdown(equity: pd.Series) -> tuple[float, pd.Timestamp | None]:
    """最大回撤及其发生日期：从峰值最深跌了多少。这是"拿不拿得住"的量化。"""
    dd = drawdown_series(equity)
    if dd.empty:
        return 0.0, None
    worst_i = dd.idxmin()
    return float(dd.loc[worst_i]), worst_i


def compute(equity: pd.Series, trades: pd.DataFrame | None = None) -> dict:
    """算全套绩效指标。equity 是引擎输出的每日总资产序列。"""
    ret = equity.pct_change().dropna()
    n_days = len(equity)
    years = n_days / TRADING_DAYS

    total_return = equity.iloc[-1] / equity.iloc[0] - 1
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1 if years > 0 else np.nan
    ann_vol = ret.std() * np.sqrt(TRADING_DAYS)
    sharpe = ret.mean() / ret.std() * np.sqrt(TRADING_DAYS) if ret.std() > 0 else np.nan
    mdd, mdd_date = max_drawdown(equity)
    calmar = cagr / abs(mdd) if mdd < 0 else np.nan

    stats = {
        "区间": f"{equity.index[0].date()} ~ {equity.index[-1].date()}",
        "交易日数": n_days,
        "期末资产": equity.iloc[-1],
        "总收益率": total_return,
        "年化收益率": cagr,
        "年化波动率": ann_vol,
        "夏普比率": sharpe,
        "最大回撤": mdd,
        "最大回撤日": mdd_date.strftime("%Y-%m-%d") if mdd_date is not None else "-",
        "卡玛比率": calmar,
    }

    if trades is not None and len(trades) > 0:
        executed = trades[trades["action"].isin(["BUY", "SELL"])]
        stats["成交笔数"] = len(executed)
        stats["涨停/跌停/T+1挡单"] = int((trades["action"].str.startswith("SKIP")).sum())
        rounds = trade_rounds(trades)
        if rounds:
            stats["完整交易回合"] = len(rounds)
            stats["回合胜率"] = sum(r["win"] for r in rounds) / len(rounds)
            pnls = [r["pnl"] for r in rounds]
            stats["回合平均盈亏"] = float(np.mean(pnls))
            holds = [r["hold_days"] for r in rounds]
            stats["平均持仓天数"] = float(np.mean(holds))
    return stats


def trade_rounds(trades: pd.DataFrame) -> list[dict]:
    """把一买一卖配成一个回合，统计每回合盈亏（衡量"这套规则下单次出手赚不赚"）。"""
    rounds = []
    open_buy: dict | None = None
    for _, t in trades.iterrows():
        if t["action"] == "BUY":
            # 买入总支出 = 成交额 + 佣金
            open_buy = {"date": t["date"], "cost_out": t["amount"] + t["cost"]}
        elif t["action"] == "SELL" and open_buy is not None:
            net_in = t["amount"] - t["cost"]          # 卖出净入账
            pnl = net_in - open_buy["cost_out"]
            rounds.append({
                "pnl": pnl,
                "win": pnl > 0,
                "hold_days": (t["date"] - open_buy["date"]).days,
            })
            open_buy = None
    return rounds


def format_report(stats: dict, title: str = "") -> str:
    """把指标字典排成对齐的文本报告。"""
    pct_keys = {"总收益率", "年化收益率", "年化波动率", "最大回撤", "回合胜率"}
    lines = [f"===== 回测报告{(' · ' + title) if title else ''} ====="]
    for k, v in stats.items():
        if k == "最大回撤日":
            continue
        if k in pct_keys:
            val = f"{v:+.2%}" if isinstance(v, (int, float)) and not pd.isna(v) else "-"
        elif isinstance(v, float):
            val = f"{v:,.2f}" if abs(v) >= 1000 else (f"{v:.3f}" if not pd.isna(v) else "-")
        else:
            val = str(v)
        lines.append(f"{k:<16}{val:>16}")
    lines.append(f"{'最大回撤日':<16}{stats.get('最大回撤日', '-'):>16}")
    return "\n".join(lines)
