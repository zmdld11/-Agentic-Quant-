"""数据从哪来：akshare 封装 + 本地缓存。

akshare 是爬取公开财经网站（东方财富等）的免费数据库，无需注册 token。
缺点：上游网站改版会导致接口偶尔失效 —— 所以所有 akshare 调用只出现在
这个文件里，坏了一个接口只需要修这里，其他模块不受影响。

缓存策略：首次下载存 data/raw/{kind}_{symbol}.parquet，之后直接读本地。
想强制重新下载传 refresh=True（上游数据更新或接口修复后用）。
"""

from __future__ import annotations

import os
import time
from pathlib import Path

# 东财等数据源都是国内站，不需要代理。若系统配置了代理客户端(如 Clash)而其未运行，
# requests 会读取 Windows 注册表里的系统代理导致 ProxyError —— 对本进程禁用代理。
# 只影响当前 Python 进程，不修改系统设置。
os.environ.setdefault("NO_PROXY", "*")

import akshare as ak
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

# akshare 返回中文列名，统一映射成英文，后续代码只见英文
_COLUMN_MAP = {
    "日期": "date", "开盘": "open", "收盘": "close", "最高": "high",
    "最低": "low", "成交量": "volume", "成交额": "amount",
    "涨跌幅": "pct_chg", "换手率": "turnover",
}
_KEEP = ["date", "open", "high", "low", "close", "volume", "amount", "pct_chg"]

# 默认下载起点：覆盖 2015 牛市→股灾→2018 熊→2019-21 牛→2022-24 熊→2024-09 暴力反弹
# 一整个牛熊周期，回测结论才有说服力
DEFAULT_START = "2015-01-01"

# 新浪指数源需要"市场前缀+代码"形式的代码
_INDEX_SRC = {"000300": "sh000300"}

# 我们跟踪的标的池（阶段1先小而精；kind 决定用哪个接口，limit_pct 是涨跌停幅度）
UNIVERSE: dict[str, dict] = {
    "510300": {"name": "沪深300ETF", "kind": "etf",   "limit_pct": 0.10},
    "510500": {"name": "中证500ETF", "kind": "etf",   "limit_pct": 0.10},
    "512880": {"name": "证券ETF",    "kind": "etf",   "limit_pct": 0.10},
    "518880": {"name": "黄金ETF",    "kind": "etf",   "limit_pct": 0.10},
    "513100": {"name": "纳指ETF",    "kind": "etf",   "limit_pct": 0.10},
    "600519": {"name": "贵州茅台",   "kind": "stock", "limit_pct": 0.10},
    "300750": {"name": "宁德时代",   "kind": "stock", "limit_pct": 0.20},
    "000300": {"name": "沪深300指数", "kind": "index", "limit_pct": 0.10},
}


def _retry(fn, times: int = 5, wait_sec: float = 2.0):
    """爬虫接口偶发失败（连接被重置/限流），递增等待重试再放弃。"""
    last_err = None
    for i in range(times):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - akshare 抛的异常类型不稳定
            last_err = e
            time.sleep(wait_sec * (i + 1))
    raise RuntimeError(f"akshare 请求连续 {times} 次失败: {last_err}") from last_err


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=_COLUMN_MAP)
    df = df[[c for c in _KEEP if c in df.columns]].copy()
    if df.empty:
        raise ValueError("akshare 返回了空数据，接口可能改版，检查 datasource.py")
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df.astype("float64")


def download_bars(
    symbol: str,
    kind: str,
    start: str = DEFAULT_START,
    end: str | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """下载（或读缓存）日线行情，返回按日期索引的 DataFrame。

    kind: "stock" A股个股 | "etf" 场内ETF | "index" 股票指数

    个股/ETF 用后复权价（adjust="hfq"），两个原因：
    1. 回测要的是"分红再投资"的真实总回报序列，这正是 hfq 的定义；
    2. 东财的前复权(qfq)在长历史+高分红个股上会算出负价格
       （茅台 2015 年 qfq 收盘价是 -117 元），直接毁掉回测。
    hfq 唯一的副作用是价格数值偏大，所以回测初始资金设为 100 万配合一手门槛。
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cache = DATA_DIR / f"{kind}_{symbol}.parquet"
    if cache.exists() and not refresh:
        df = pd.read_parquet(cache)
    else:
        start_s = pd.Timestamp(start).strftime("%Y%m%d")
        end_s = pd.Timestamp(end or pd.Timestamp.now()).strftime("%Y%m%d")
        if kind == "stock":
            raw = _retry(lambda: ak.stock_zh_a_hist(
                symbol=symbol, period="daily", start_date=start_s, end_date=end_s, adjust="hfq"))
        elif kind == "etf":
            raw = _retry(lambda: ak.fund_etf_hist_em(
                symbol=symbol, period="daily", start_date=start_s, end_date=end_s, adjust="hfq"))
        elif kind == "index":
            # 指数走新浪源：东财 index_zh_a_hist 内部要分17页抓全市场代码表，
            # 连发请求极易被限流掐断；新浪源单请求拿全量历史，稳定得多。
            raw = _retry(lambda: ak.stock_zh_index_daily(symbol=_INDEX_SRC[symbol]))
        else:
            raise ValueError(f"未知 kind: {kind}（可选 stock/etf/index）")
        df = _clean(raw)
        df.to_parquet(cache)
    # 缓存里是全量数据，按请求区间切片后返回
    return df.loc[start: end or df.index[-1]]


def download_universe(refresh: bool = False) -> None:
    """把 UNIVERSE 里所有标的的数据拉到本地（数据热身用）。"""
    for symbol, meta in UNIVERSE.items():
        df = download_bars(symbol, meta["kind"], refresh=refresh)
        print(f"  {symbol} {meta['name']:<8} {len(df):>5} 根日线  {df.index[0].date()} ~ {df.index[-1].date()}")
