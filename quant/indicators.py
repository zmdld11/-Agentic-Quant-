"""技术指标库：全部 pandas 向量化实现，没有循环。

注意：所有指标都只用「当天及以前」的数据（rolling/ewm 天然满足），
所以指标本身不引入未来信息 —— 未来信息往往死于「信号和成交同一天」。
"""

from __future__ import annotations

import pandas as pd


def ma(s: pd.Series, n: int) -> pd.Series:
    """n 日简单移动平均。"""
    return s.rolling(n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    """n 日指数移动平均（越近的价格权重越大）。"""
    return s.ewm(span=n, adjust=False).mean()


def roc(s: pd.Series, n: int) -> pd.Series:
    """n 日动量：今天相对 n 天前涨跌了多少（收益率形式）。"""
    return s / s.shift(n) - 1


def vol(s: pd.Series, n: int) -> pd.Series:
    """n 日波动率：日收益率的标准差。"""
    return s.pct_change().rolling(n).std()


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    """相对强弱指标 RSI（Wilder 平滑版）。

    直觉：最近 n 天里涨的力量 vs 跌的力量。RSI > 70 常被称为超买，
    < 30 超卖 —— 但"超买"不等于马上跌，趋势强时可以一直超买。
    """
    diff = s.diff()
    up = diff.clip(lower=0)
    down = (-diff).clip(lower=0)
    avg_up = up.ewm(alpha=1 / n, adjust=False).mean()
    avg_down = down.ewm(alpha=1 / n, adjust=False).mean()
    rs = avg_up / avg_down
    return 100 - 100 / (1 + rs)


def bollinger(s: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    """布林带：中轨 = n日均线，上下轨 = 中轨 ± k 倍标准差。

    价格触及下轨 → 相对便宜（超卖），触及上轨 → 相对贵（超买）。
    """
    mid = ma(s, n)
    std = s.rolling(n).std()
    return pd.DataFrame({"mid": mid, "upper": mid + k * std, "lower": mid - k * std})
