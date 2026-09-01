"""横截面因子研究：从"什么时候买"（择时）升级到"买哪些"（选股）。

思路转变：不再预测大盘涨跌，而是问"这 300 只成分股里，下个月哪些更可能
跑赢哪些"。给每只股票按因子打分，检验分数与未来收益的关系。

三个经典价格因子（方向统一为：分越高 = 预期收益越高）：
    动量60日   过去60个交易日涨幅 —— 强者恒强（动量效应）
    反转20日   过去20日涨幅取负 —— 超卖反弹（短期反转）
    低波动60日 60日波动率取负 —— 低波动异象（风险低的反而赚得多）

两个标准检验（比看净值曲线更早、更诚实地回答"因子有没有用"）：
    IC   每月【因子分】与【下月收益】的全截面 Spearman 秩相关。
         经验标准：|IC均值| > 0.03 且 ICIR > 0.3 算可用，> 0.5 相当好。
    分组  每月按因子分 5 组等权持有，收益单调才算因子真实存在。

必须声明的偏差：成分股名单取自【今天】的沪深300——用今天的赢家名单
回测历史（幸存者偏差），收益会被系统性高估。结论看相对强弱（因子间、
组间对比）可信，绝对收益数字要打折。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def factor_definitions() -> dict[str, object]:
    return {
        "动量60日": lambda closes, ret: closes / closes.shift(60) - 1,
        "反转20日": lambda closes, ret: -(closes / closes.shift(20) - 1),
        "低波动60日": lambda closes, ret: -(ret.rolling(60).std() * np.sqrt(252)),
    }


def load_closes(start: str = "2016-06-01", end: str | None = None,
                min_days: int = 250) -> pd.DataFrame:
    """读全部成分股的日收盘价，拼成 date × code 的宽表。

    停牌日为 NaN（当月没数据的股票自动退出当期横截面）；上市不足
    min_days 天的剔除（因子算不稳）。
    """
    files = sorted(DATA_DIR.glob("stock_*.parquet"))
    if len(files) < 50:
        raise RuntimeError("成分股数据不足：先运行 python main.py factors --download")
    series = {}
    for f in files:
        code = f.stem.replace("stock_", "")
        df = pd.read_parquet(f)
        s = df["close"].dropna()
        s = s[s > 0]
        if len(s) >= min_days:
            series[code] = s
    closes = pd.DataFrame(series).loc[start: end]
    return closes


def load_wide_panel(start: str = "2016-06-01", end: str | None = None,
                    min_days: int = 250) -> dict[str, pd.DataFrame]:
    """读全部成分股的 OHLCV+成交额，拼成 {字段: date×code 宽表}。

    供 WorldQuant 式公式因子使用；vwap 用 (O+H+L+C)/4 近似——
    成交额/成交量算出的是不复权均价，与后复权价格混用会破坏跨股可比性，
    用 OHLC 均值近似则与价格同口径（自洽且截面可比）。
    """
    files = sorted(DATA_DIR.glob("stock_*.parquet"))
    if len(files) < 50:
        raise RuntimeError("成分股数据不足：先运行 python main.py factors --download")
    fields = ("open", "high", "low", "close", "volume", "amount")
    cols: dict[str, dict[str, pd.Series]] = {f: {} for f in fields}
    for f in files:
        code = f.stem.replace("stock_", "")
        df = pd.read_parquet(f)
        if len(df) < min_days:
            continue
        for field in fields:
            cols[field][code] = df[field]
    panel = {field: pd.DataFrame(d).loc[start: end] for field, d in cols.items()}
    return panel


def month_end_factors(closes: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """各因子的月末快照（date × code）。"""
    ret = closes.pct_change()
    out = {}
    for name, fn in factor_definitions().items():
        out[name] = fn(closes, ret).resample("ME").last()
    return out


def compute_ics(closes: pd.DataFrame, start: str = "2019-01-01",
                min_stocks: int = 50) -> pd.DataFrame:
    """逐月计算各因子的秩相关 IC（因子分 vs 下月收益）。"""
    return ics_from_frames(month_end_factors(closes), closes, start, min_stocks)


def ics_from_frames(month_factors: dict[str, pd.DataFrame], closes: pd.DataFrame,
                    start: str = "2019-01-01", min_stocks: int = 50) -> pd.DataFrame:
    """通用版 IC 计算：传入任意"月末因子快照 dict"，逐月与下月收益做 Spearman。

    WQ101 等自定义因子研究走这个入口（与 s5 用同一把尺子）。
    """
    monthly = closes.resample("ME").last()
    fwd = (monthly.shift(-1) / monthly - 1).loc[start:]   # 下月收益，对齐在当月末行
    ic_cols = {}
    for name, f in month_factors.items():
        f = f.loc[start:]
        ics = {}
        for date, row in f.iterrows():
            y = fwd.loc[date] if date in fwd.index else None
            if y is None:
                continue
            both = pd.concat([row, y], axis=1).dropna()
            if len(both) >= min_stocks:
                ics[date] = both.iloc[:, 0].corr(both.iloc[:, 1], method="spearman")
        ic_cols[name] = pd.Series(ics)
    return pd.DataFrame(ic_cols)


def ic_summary(ic_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, s in ic_df.items():
        s = s.dropna()
        if len(s) < 2:
            continue
        rows.append({
            "因子": name,
            "IC均值": s.mean(),
            "IC标准差": s.std(),
            "ICIR": s.mean() / s.std(),
            "t值": s.mean() / s.std() * np.sqrt(len(s)),
            "IC>0占比": (s > 0).mean(),
            "月数": len(s),
        })
    return pd.DataFrame(rows)


def quantile_backtest(
    closes: pd.DataFrame,
    factor: pd.DataFrame,
    start: str = "2019-01-01",
    n_groups: int = 5,
    cost_one_way: float = 0.0015,
) -> pd.DataFrame:
    """按因子分 N 组等权、月度调仓的净值（Q1 = 因子分最高组）。

    成本：换手 Σ|Δw| × 单边费率(0.15%，含佣金滑点冲击)。
    返回 date × [Q1..Qn] 的净值DataFrame，用于画"单调性"。
    """
    factor = factor.loc[start:]
    monthly = closes.resample("ME").last()
    fwd = (monthly.shift(-1) / monthly - 1).loc[start:]
    n_months = len(factor.index) - 1

    net_rets = {g: [] for g in range(1, n_groups + 1)}
    dates = []
    prev_w = {g: None for g in range(1, n_groups + 1)}
    for t in factor.index[:n_months]:
        row = factor.loc[t].dropna()
        if len(row) < n_groups * 10:
            continue
        fr = fwd.loc[t].reindex(row.index)
        valid = fr.dropna().index
        row = row.reindex(valid)
        if len(row) < n_groups * 10:
            continue
        dates.append(t)
        ranks = row.rank(ascending=False)
        size = len(ranks) // n_groups
        for g in range(1, n_groups + 1):
            sel = ranks[(ranks > (g - 1) * size) & (ranks <= g * size)].index
            w = pd.Series(0.0, index=valid)
            w[sel] = 1.0 / len(sel)
            gross = float((w * fwd.loc[t].reindex(valid)).sum())
            turnover = float((w - (prev_w[g] if prev_w[g] is not None else 0.0)).abs().sum())
            net_rets[g].append(gross - turnover * cost_one_way)
            prev_w[g] = w

    out = pd.DataFrame(
        {f"Q{g}": pd.Series(v, index=dates[:len(v)]) for g, v in net_rets.items()})
    return (1 + out.fillna(0)).cumprod()


def composite_score(closes: pd.DataFrame) -> pd.DataFrame:
    """三因子横截面 z-score 等权合成（每月、每因子里做标准化后取平均）。"""
    factors = month_end_factors(closes)
    zs = []
    for f in factors.values():
        mean = f.mean(axis=1)
        std = f.std(axis=1)
        z = f.sub(mean, axis=0).div(std.replace(0, np.nan), axis=0)
        zs.append(z.clip(-3, 3))          # 去极值：截断±3σ
    return sum(zs) / len(zs)


def topn_monthly_backtest(
    closes: pd.DataFrame,
    score: pd.DataFrame,
    topn: int = 30,
    start: str = "2019-01-01",
    cost_one_way: float = 0.0015,
) -> pd.DataFrame:
    """月度持有 score 最高的 topn 只（等权），返回净值。

    附带两个基准：全池等权（同样的月度再平衡和费率）、沪深300指数。
    这是"解析式"回测：月度收益 = Σ权重×下月收益 − 换手×费率，
    简洁透明；逐笔撮合级别的模拟留给单标的引擎（教学分工）。
    """
    score = score.loc[start:]
    monthly = closes.resample("ME").last()
    fwd = (monthly.shift(-1) / monthly - 1).loc[start:]
    n_months = len(score.index) - 1

    def _run(weight_fn):
        rets, prev_w, dates = [], None, []
        for t in score.index[:n_months]:
            row = score.loc[t].dropna()
            fr = fwd.loc[t].reindex(row.index).dropna()
            row = row.reindex(fr.index)
            if len(row) < topn:
                continue
            w = weight_fn(row)
            gross = float((w * fr).sum())
            turnover = float((w - (prev_w if prev_w is not None else 0.0)).abs().sum())
            rets.append(gross - turnover * cost_one_way)
            prev_w = w
            dates.append(t)
        s = pd.Series(rets, index=dates)
        return (1 + s).cumprod()

    top_curve = _run(lambda row: _topn_weight(row, topn))
    ew_curve = _run(lambda row: pd.Series(1.0 / len(row), index=row.index))
    return pd.DataFrame({"策略Top%d" % topn: top_curve, "全池等权": ew_curve})


def _topn_weight(row: pd.Series, topn: int) -> pd.Series:
    sel = row.nlargest(topn).index
    w = pd.Series(0.0, index=row.index)
    w[sel] = 1.0 / topn
    return w
