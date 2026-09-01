"""WorldQuant 101 Formulaic Alphas 的自研实现（精选 26 个）。

来源论文：Kakushadze (2015) "101 Formulaic Alphas" (arXiv:1601.00991)。
这批因子是 2015 年 WorldQuant 公开的真实生产线公式，由 rank/correlation/
时序算子组合而成——史上最著名的一批"公开 alpha"。

与参考实现（如 yli188/WorldQuant_alpha101_code）的差异与本仓库约定：
- 只选纯价格/成交量公式（跳过含 IndNeutralize 的——我们没有行业分类数据）
- 价格输入为后复权(hfq)，vwap 用 (O+H+L+C)/4 近似（成交额算出的不复权均价
  与后复权价格混用会破坏跨股可比性，见 factors.load_wide_panel 说明）
- 所有除零产生的 ±inf 统一替换为 NaN，由横截面 dropna 兜底

为什么值得做：HN 上有著名质疑——"这 101 个可能只是随机生成+样本内幸存的
公式"。本模块的 run_research 用训练/测试 IC 分割来验尸：
训练期(2019-2022) IC 最高的因子，测试期(2023-2026) 还活着吗？
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from quant import factors as fac
from quant.plotting import plot_heatmap, plot_scatter

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"


# ---------------------------------------------------------------------------
# 算子库：输入输出都是 date × code 宽表
# ---------------------------------------------------------------------------

def rank(df: pd.DataFrame) -> pd.DataFrame:
    """截面排名（每天把全市场排成 0~1 的分位）。"""
    return df.rank(axis=1, pct=True)


def delay(df: pd.DataFrame, d: int) -> pd.DataFrame:
    return df.shift(d)


def delta(df: pd.DataFrame, d: int) -> pd.DataFrame:
    return df - df.shift(d)


def ts_sum(df: pd.DataFrame, d: int) -> pd.DataFrame:
    return df.rolling(d).sum()


def ts_min(df: pd.DataFrame, d: int) -> pd.DataFrame:
    return df.rolling(d).min()


def ts_max(df: pd.DataFrame, d: int) -> pd.DataFrame:
    return df.rolling(d).max()


def ts_rank(df: pd.DataFrame, d: int) -> pd.DataFrame:
    """时序排名：今天的价格在过去 d 天里处于什么分位（0~1）。"""
    return df.rolling(d).apply(lambda a: a.argsort().argsort()[-1] / (len(a) - 1), raw=True)


def ts_argmin(df: pd.DataFrame, d: int) -> pd.DataFrame:
    return df.rolling(d).apply(np.argmin, raw=True)


def ts_argmax(df: pd.DataFrame, d: int) -> pd.DataFrame:
    return df.rolling(d).apply(np.argmax, raw=True)


def correlation(x: pd.DataFrame, y: pd.DataFrame, d: int) -> pd.DataFrame:
    return x.rolling(d).corr(y)


def covariance(x: pd.DataFrame, y: pd.DataFrame, d: int) -> pd.DataFrame:
    return x.rolling(d).cov(y)


def std(df: pd.DataFrame, d: int) -> pd.DataFrame:
    return df.rolling(d).std()


def scale(df: pd.DataFrame) -> pd.DataFrame:
    """截面归一：每天把全市场的绝对值和缩放为 1（保留相对大小与符号）。"""
    return df.div(df.abs().sum(axis=1), axis=0)


def sign(df: pd.DataFrame) -> pd.DataFrame:
    return np.sign(df)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """除零兜底：±inf → NaN。"""
    return df.replace([np.inf, -np.inf], np.nan)


# ---------------------------------------------------------------------------
# 精选公式（编号对应论文原始编号，公式忠实原意）
# ---------------------------------------------------------------------------

def build_alphas(panel: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    o, h, l, c = panel["open"], panel["high"], panel["low"], panel["close"]
    v, amt = panel["volume"], panel["amount"]
    rets = c.pct_change()
    vwap = (o + h + l + c) / 4
    adv20 = amt.rolling(20).mean()

    def A2():  return -correlation(rank(delta(np.log(v), 2)), rank((c - o) / o), 6)
    def A3():  return -correlation(rank(o), rank(v), 10)
    def A4():  return -ts_rank(rank(l), 9)
    def A6():  return -correlation(o, v, 10)
    def A7():  # 放量时：跌得越急越看多（反转逻辑）；缩量：一律看空
        cond = adv20 < v
        val = -ts_rank(abs(delta(c, 7)), 60) * sign(delta(c, 7))
        return clean(val.where(cond, other=-1.0))
    def A8():  p = ts_sum(o, 5) * ts_sum(rets, 5); return -rank(p - delay(p, 10))
    def A9():  # 五日内连涨续涨、连跌反手做多的状态机
        d1 = delta(c, 1)
        picked = np.where(ts_min(d1, 5) > 0, d1,
                          np.where(ts_max(d1, 5) > 0, d1, -d1))
        return clean(pd.DataFrame(picked, index=c.index, columns=c.columns))
    def A12(): return sign(delta(v, 1)) * (-delta(c, 1))
    def A13(): return -rank(covariance(rank(c), rank(v), 5))
    def A14(): return -rank(delta(rets, 3)) * correlation(o, v, 10)
    def A16(): return -rank(covariance(rank(h), rank(v), 5))
    def A17(): return (-rank(ts_rank(c, 10)) * rank(delta(delta(c, 1), 1))
                       * rank(ts_rank(v / adv20, 5)))
    def A18(): return -rank(sign(delta(c, 1)) + sign(delta(c, 2)) + sign(delta(c, 3)))
    def A19(): return -sign(delta(c, 7) + delta(c, 7))
    def A20(): return (-rank(o - delay(h, 1)) * rank(o - delay(l, 1))
                       * rank(o - delay(c, 1)))
    def A22(): return -(delta(correlation(h, v, 2), 2) * rank(o))
    def A28(): return clean(scale((correlation(adv20, l, 5) + (h - l) ** 0.2)
                                  / correlation(adv20, h, 5)))
    def A33(): return rank(-(1 - o / c))
    def A34(): return rank(1 - rank(std(rets, 2) / std(rets, 5)) + 1 - rank(delta(c, 1)))
    def A35(): return (ts_rank(v, 32) * (1 - ts_rank(c + h - l, 16))
                       * (1 - ts_rank(rets, 32)))
    def A38(): return -rank(ts_rank(c, 10)) * rank(c / o)
    def A40(): return -rank(std(h, 10) ** 2) * correlation(h, v, 10)
    def A41(): return clean((h * l) ** 0.5 - vwap)
    def A42(): return clean(rank(vwap - c) / rank(vwap + c))
    def A43(): return ts_rank(v / adv20, 20) * ts_rank(-delta(c, 7), 8)
    def A44(): return -correlation(h, rank(v), 5)
    def A45(): return (-rank(ts_sum(delay(c, 5), 20) / 20) * correlation(c, v, 2)
                       * rank(correlation(ts_sum(c, 5), ts_sum(c, 20), 2)))
    def A54(): return clean(-((l - c) * o ** 5) / ((l - h) * c ** 5))
    def A101(): return clean((c - o) / (h - l + 0.001))

    builders = {"A2": A2, "A3": A3, "A4": A4, "A6": A6, "A7": A7, "A8": A8, "A9": A9,
                "A12": A12, "A13": A13, "A14": A14, "A16": A16, "A17": A17, "A18": A18,
                "A19": A19, "A20": A20, "A22": A22, "A28": A28, "A33": A33, "A34": A34,
                "A35": A35, "A38": A38, "A40": A40, "A41": A41, "A42": A42, "A43": A43,
                "A44": A44, "A45": A45, "A54": A54, "A101": A101}
    out = {}
    for name, fn in builders.items():
        try:
            out[name] = clean(fn())
        except Exception as e:  # noqa: BLE001 - 单个公式失败不拖垮整体研究
            print(f"  [skip] {name}: {type(e).__name__} {e}")
    return out


# ---------------------------------------------------------------------------
# 验尸实验：训练期选因子 → 测试期检验
# ---------------------------------------------------------------------------

def run_research(start: str = "2019-01-01", split: str = "2023-01-01") -> pd.DataFrame:
    panel = fac.load_wide_panel()
    print(f"宽表面板: {panel['close'].shape[0]} 天 × {panel['close'].shape[1]} 只，计算 WQ 因子...")
    daily_alphas = build_alphas(panel)
    closes = panel["close"]
    month_alphas = {name: f.resample("ME").last() for name, f in daily_alphas.items()}

    ic_series = fac.ics_from_frames(month_alphas, closes, start=start)
    out = RESULTS_DIR / "wq101"
    out.mkdir(parents=True, exist_ok=True)
    ic_series.to_csv(out / "ic_series.csv", encoding="utf-8-sig")

    train = ic_series.loc[:split]
    test = ic_series.loc[split:]
    summary = pd.DataFrame({
        "IC均值_训练": train.mean(),
        "ICIR_训练": train.mean() / train.std(),
        "IC均值_测试": test.mean(),
        "ICIR_测试": test.mean() / test.std(),
        "测试IC>0占比": (test > 0).mean(),
        "ICIR_全期": ic_series.mean() / ic_series.std(),
    }).sort_values("IC均值_训练", ascending=False)
    summary.index.name = "因子"
    summary.to_csv(out / "summary.csv", encoding="utf-8-sig")

    # 训练期最优 3 个因子：测试期分组回测（因子还"能落地"吗）
    top3 = summary.head(3).index.tolist()
    for name in top3:
        q = fac.quantile_backtest(closes, month_alphas[name], start=split)
        last = f"Q{q.shape[1]}"
        q.columns = [f"{c}(因子最高)" if c == "Q1" else (f"{c}(因子最低)" if c == last else c)
                     for c in q.columns]
        fac_q = {c: q[c] for c in q.columns}
        from quant.plotting import plot_lines
        plot_lines(fac_q, title=f"WQ {name} · 测试期({split}起)分组回测 · 月度调仓",
                   save_path=out / f"chart_quantile_{name}.png")

    corr = summary["IC均值_训练"].corr(summary["IC均值_测试"], method="spearman")
    plot_scatter(
        summary["IC均值_训练"], summary["IC均值_测试"],
        xlabel=f"训练期IC均值 ({start}~{split})", ylabel=f"测试期IC均值 ({split}~今)",
        title=f"WQ101 验尸：训练IC vs 测试IC · Spearman={corr:.2f}",
        highlight=(f"训练最优 {top3[0]}",
                   summary.loc[top3[0], "IC均值_训练"], summary.loc[top3[0], "IC均值_测试"]),
        save_path=out / "chart_autopsy.png",
    )
    plot_heatmap(summary[["ICIR_训练", "ICIR_测试"]], title="WQ101 因子 ICIR：训练 vs 测试",
                 save_path=out / "chart_icir.png")

    fmt = {"IC均值_训练": "{:+.4f}", "IC均值_测试": "{:+.4f}", "ICIR_训练": "{:+.2f}",
           "ICIR_测试": "{:+.2f}", "测试IC>0占比": "{:.0%}", "ICIR_全期": "{:+.2f}"}
    table = summary.copy()
    for k, f in fmt.items():
        table[k] = table[k].map(lambda x, f=f: f.format(x) if pd.notna(x) else "-")
    verdict = (
        f"训练/测试 IC 秩相关: {corr:.2f}\n"
        f"训练最优3个: {', '.join(top3)} → 测试期IC均值: "
        + ", ".join(f"{summary.loc[n, 'IC均值_测试']:+.4f}" for n in top3)
        + "\n判定: 训练期IC>0.03的因子数 "
        f"{(summary['IC均值_训练'] > 0.03).sum()}/{len(summary)}，"
        f"其中测试期仍>0.03的 {(summary[(summary['IC均值_训练'] > 0.03)]['IC均值_测试'] > 0.03).sum()} 个"
    )
    (out / "report.txt").write_text(table.to_string() + "\n\n" + verdict, encoding="utf-8")
    print(table.to_string())
    print("\n" + verdict)
    return summary
