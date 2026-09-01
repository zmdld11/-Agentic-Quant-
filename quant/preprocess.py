"""数据清洗与单标的加载。

回测前最起码的两件事：
1. 剔除停牌日（成交量为 0 的日子没有可成交价格）
2. 算好日收益率 ret（后面指标和回测都靠它）
"""

from __future__ import annotations

import pandas as pd

from .datasource import download_bars


def load_bars(
    symbol: str,
    kind: str,
    start: str = "2015-01-01",
    end: str | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """读取清洗后的日线：open/high/low/close/volume/amount/ret。"""
    df = download_bars(symbol, kind, start, end, refresh).copy()
    df = df[df["volume"] > 0]                      # 停牌日：无法成交，剔除
    df = df.dropna(subset=["open", "high", "low", "close"])
    df["ret"] = df["close"].pct_change()
    return df


def load_index(series_symbol: str = "000300", start: str = "2015-01-01",
               end: str | None = None, refresh: bool = False) -> pd.DataFrame:
    """加载指数日线（作为市场基准）。"""
    df = download_bars(series_symbol, "index", start, end, refresh).copy()
    df = df.dropna(subset=["close"])
    df["ret"] = df["close"].pct_change()
    return df
