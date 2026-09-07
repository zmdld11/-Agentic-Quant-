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

# akshare 的请求层不传 timeout（实测：财联社接口异常时裸连接挂死 +
# 指数退避重试10次 ≈ 17分钟"假死"，2026-09-07 踩坑）。给全进程所有
# requests.get 补默认 30s 超时；已显式传 timeout 的调用不受影响。
import requests as _requests  # noqa: E402

_orig_requests_get = _requests.get

def _requests_get_with_default_timeout(*args, **kwargs):  # noqa: E301
    kwargs.setdefault("timeout", 30)
    return _orig_requests_get(*args, **kwargs)

_requests.get = _requests_get_with_default_timeout

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


def _bs_fetch_daily(symbol: str, start: str, end: str) -> pd.DataFrame:
    """baostock 后复权日线（股票与 ETF 通用），东财限流时的兜底源。

    注意：baostock 的后复权基准(anchor)与东财不同。直接混用会让同一条
    价格序列出现台阶 → 调用方须做锚点对齐（见 _align_anchor）。
    """
    import baostock as bs  # noqa: PLC0415

    prefix = "sh." if symbol.startswith(("5", "6", "9")) else "sz."
    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(f"baostock 登录失败: {lg.error_msg}")
    try:
        rs = bs.query_history_k_data_plus(
            prefix + symbol, "date,open,high,low,close,volume,amount",
            start_date=start, end_date=end, frequency="d", adjustflag="1")
        rows = []
        while rs.error_code == "0" and rs.next():
            rows.append(rs.get_row_data())
    finally:
        bs.logout()
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close",
                                     "volume", "amount"])
    if df.empty:
        raise RuntimeError(f"baostock 无数据: {symbol}")
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index().astype("float64")
    return df[df["volume"] > 0]


def _align_anchor(new_df: pd.DataFrame, cache: Path) -> pd.DataFrame:
    """把兜底源的新数据缩放到与缓存一致的复权锚点（防换源造成价格台阶）。

    做法：取两边最近 60 个共同交易日的收盘比值作为缩放系数。
    无缓存或重叠不足时不处理（全新标的，锚点无所谓）。
    """
    if not cache.exists():
        return new_df
    try:
        old = pd.read_parquet(cache)
        joined = pd.concat([old["close"].rename("old"), new_df["close"].rename("new")],
                           axis=1, join="inner").dropna()
        if len(joined) >= 20:
            factor = float(joined["old"].iloc[-1] / joined["new"].iloc[-1])
            if 0.1 < factor < 10:   # 合理区间外的比值视为异常，放弃对齐
                return new_df * factor
    except Exception:  # noqa: BLE001 - 对齐失败就原样返回，宁可不修不能改错
        pass
    return new_df


def _merge_with_cache(new_df: pd.DataFrame, cache: Path) -> pd.DataFrame:
    """兜底源与缓存合并而非替换：保留全部历史，只用新数据补尾部。

    背景坑（2026-09-07 实测）：baostock 的 ETF 数据只有 2026 年以后
    （股票却是全历史）——直接替换会把 2015-2026 的回测历史冲掉。
    新旧衔接处用对齐过的锚点，接缝两侧价格一致。
    """
    if not cache.exists():
        return new_df
    old = pd.read_parquet(cache)
    common = new_df.index.intersection(old.index)
    if len(common):
        # 重叠期以新数据为准（最近几日可能有数据修订），更早的沿用缓存
        cut = common[0]
        return pd.concat([old.loc[:cut], new_df.loc[cut:]])
    # 无重叠（baostock 只给近期而缓存停更更早？）→ 拼接并告警
    print(f"  [warn] 兜底数据与缓存无重叠：{cache.stem} 缓存止于 {old.index[-1].date()}，"
          f"新数据始于 {new_df.index[0].date()}，中间可能有缺口")
    return pd.concat([old, new_df[new_df.index > old.index[-1]]])


def download_bars(
    symbol: str,
    kind: str,
    start: str = DEFAULT_START,
    end: str | None = None,
    refresh: bool = False,
    retries: int = 5,
) -> pd.DataFrame:
    """下载（或读缓存）日线行情，返回按日期索引的 DataFrame。

    kind: "stock" A股个股 | "etf" 场内ETF | "index" 股票指数

    个股/ETF 用后复权价（adjust="hfq"），两个原因：
    1. 回测要的是"分红再投资"的真实总回报序列，这正是 hfq 的定义；
    2. 东财的前复权(qfq)在长历史+高分红个股上会算出负价格
       （茅台 2015 年 qfq 收盘价是 -117 元），直接毁掉回测。
    hfq 唯一的副作用是价格数值偏大，所以回测初始资金设为 100 万配合一手门槛。

    兜底链：个股/ETF 主走东财(akshare)，被限流掐连接时自动切 baostock，
    并做锚点对齐保证与历史缓存无缝衔接——无人值守定时任务的可靠性靠这层。
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cache = DATA_DIR / f"{kind}_{symbol}.parquet"
    if cache.exists() and not refresh:
        df = pd.read_parquet(cache)
    else:
        start_s = pd.Timestamp(start).strftime("%Y%m%d")
        end_s = pd.Timestamp(end or pd.Timestamp.now()).strftime("%Y%m%d")
        try:
            if kind == "stock":
                raw = _retry(lambda: ak.stock_zh_a_hist(
                    symbol=symbol, period="daily", start_date=start_s, end_date=end_s, adjust="hfq"),
                    times=retries)
                df = _clean(raw)
            elif kind == "etf":
                raw = _retry(lambda: ak.fund_etf_hist_em(
                    symbol=symbol, period="daily", start_date=start_s, end_date=end_s, adjust="hfq"),
                    times=retries)
                df = _clean(raw)
            elif kind == "index":
                # 指数走新浪源：东财 index_zh_a_hist 内部要分17页抓全市场代码表，
                # 连发请求极易被限流掐断；新浪源单请求拿全量历史，稳定得多。
                raw = _retry(lambda: ak.stock_zh_index_daily(symbol=_INDEX_SRC[symbol]))
                df = _clean(raw)
            else:
                raise ValueError(f"未知 kind: {kind}（可选 stock/etf/index）")
        except Exception as e:  # noqa: BLE001 - 东财失败 → baostock 兜底（只补尾部增量）
            if kind not in ("stock", "etf"):
                raise
            print(f"  [fallback] {symbol} 东财失败({type(e).__name__})，改用 baostock")
            df = _retry(lambda: _bs_fetch_daily(
                symbol, start, (end or str(pd.Timestamp.now().date()))), times=2)
            df = _align_anchor(df, cache)
            df = _merge_with_cache(df, cache)
        df.to_parquet(cache)
    # 缓存里是全量数据，按请求区间切片后返回
    return df.loc[start: end or df.index[-1]]


def download_universe(refresh: bool = False) -> None:
    """把 UNIVERSE 里所有标的的数据拉到本地（数据热身用）。"""
    for symbol, meta in UNIVERSE.items():
        df = download_bars(symbol, meta["kind"], refresh=refresh)
        print(f"  {symbol} {meta['name']:<8} {len(df):>5} 根日线  {df.index[0].date()} ~ {df.index[-1].date()}")


# ---------------------------------------------------------------------------
# 横截面研究：指数成分股批量下载
# ---------------------------------------------------------------------------

STOCKS_DIR = DATA_DIR / "stocks"


def get_index_constituents(index_code: str = "000300", refresh: bool = False) -> pd.DataFrame:
    """指数成分股列表 [code, name]。

    重要局限：免费数据只能拿到【当前】成分股。用今天的名单回测历史存在
    幸存者偏差（能进沪深300的是过去的赢家，中途退市/被剔除的看不到），
    系统性高估收益 —— 实验记录里必须声明这一点。
    """
    cache = DATA_DIR / f"cons_{index_code}.parquet"
    if cache.exists() and not refresh:
        return pd.read_parquet(cache)
    raw = _retry(lambda: ak.index_stock_cons_csindex(symbol=index_code))
    df = raw.rename(columns={"成分券代码": "code", "成分券名称": "name"})[["code", "name"]].copy()
    df.to_parquet(cache)
    return df


def download_stock_universe(
    index_code: str = "000300",
    start: str = "2016-06-01",
    refresh: bool = False,
    verbose_every: int = 50,
    part: tuple[int, int] | None = None,
) -> tuple[int, list[str]]:
    """批量下载成分股后复权日线，缓存到 data/raw/stock_{code}.parquet。

    走 baostock 而不是 akshare：批量300只时东财接口会被限流间歇掐连接，
    baostock 一次登录后连续查询，快且稳。两家的后复权基准(anchor)不同，
    但我们只做基于"收益率"的横截面比较，逐只自身可比即可，互不影响。

    part: (起始行, 结束行) 切片——多进程并行下载时各管一段，互不重叠。
    """
    cons = get_index_constituents(index_code, refresh=refresh)
    if part is not None:
        cons = cons.iloc[part[0]:part[1]]
    import baostock as bs  # 局部导入：只有批量下载需要它

    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(f"baostock 登录失败: {lg.error_msg}")

    ok, failed = 0, []
    try:
        for i, row in cons.iterrows():
            code = row["code"]
            cache = DATA_DIR / f"stock_{code}.parquet"
            if cache.exists() and not refresh:
                ok += 1
                continue
            # baostock 需要 交易所.代码 形式：6/5 开头是沪市，其余深市
            bs_code = ("sh." if code.startswith(("6", "5")) else "sz.") + code
            rs = bs.query_history_k_data_plus(
                bs_code, "date,open,high,low,close,volume,amount",
                start_date=start, end_date=pd.Timestamp.now().strftime("%Y-%m-%d"),
                frequency="d", adjustflag="1")   # 1=后复权
            rows = []
            while rs.error_code == "0" and rs.next():
                rows.append(rs.get_row_data())
            if rows:
                df = pd.DataFrame(rows, columns=rs.fields)
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date").sort_index()
                for col in ("open", "high", "low", "close", "volume", "amount"):
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df = df[df["volume"] > 0]        # 停牌日剔除
                df.to_parquet(cache)
                ok += 1
            else:
                failed.append(f"{code} {row['name']}")
            if verbose_every and (i + 1) % verbose_every == 0:
                print(f"  ... {i + 1}/{len(cons)}（失败 {len(failed)}）")
    finally:
        bs.logout()
    print(f"成分股下载完成：成功 {ok}/{len(cons)}"
          + (f"，失败: {failed[:10]}{'...' if len(failed) > 10 else ''}" if failed else ""))
    return ok, failed
