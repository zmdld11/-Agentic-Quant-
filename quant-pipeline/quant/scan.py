"""参数扫描与样本外验证：量化最重要的一课 —— 过拟合。

两个实验：
1. scan   参数扫描：同一策略换一组参数，在同一数据上表现差多少。
          目的不是找"最好参数"，而是看参数面的【形状】：
          平台（相邻参数也都不差）= 策略可能真有效；
          尖峰（只有个别参数组合赚钱）= 大概率是把历史噪声当成了规律。
2. overfit 训练/测试分割：在训练集(2015-2021)上选最优参数，
          再到测试集(2022-2026)上验证 —— 模拟真实世界：
          "你只能用过去的数据选参数，却要用它面对未来"。
          训练集排名和测试集排名的相关性，就是参数可信度的度量。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from quant import metrics as met
from quant.datasource import UNIVERSE
from quant.plotting import plot_backtest, plot_heatmap, plot_scatter
from strategies import s1_ma_cross as s1

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"

GRID_SHORT = (3, 5, 10, 20)
GRID_LONG = (20, 40, 60, 120, 250)
TRAIN_START = "2015-01-01"
TRAIN_END = "2021-12-31"
TEST_START = "2022-01-01"
WARMUP = "2021-06-01"  # 测试段回溯半年给均线热身，绩效只从 TEST_START 起算


def param_grid() -> list[tuple[int, int]]:
    return [(s, l) for s in GRID_SHORT for l in GRID_LONG if l > s + 5]


def backtest_period(
    symbol: str, short: int, long: int,
    run_start: str, measure_start: str | None = None, end: str | None = None,
) -> dict:
    """跑回测，绩效只在 [measure_start, end] 区间上计算（信号有热身期）。"""
    res = s1.backtest(symbol, short, long, run_start, end)
    if measure_start is not None:
        eq = res["equity"]["equity"].loc[measure_start:]
        tr = res["trades"]
        if tr is not None and len(tr):
            tr = tr[tr["date"] >= pd.Timestamp(measure_start)]
        else:
            tr = None
        res["stats"] = met.compute(eq, tr)
    return res


def run_grid(symbol: str, run_start: str, measure_start: str | None,
             end: str | None = None) -> pd.DataFrame:
    rows = []
    for short, long in param_grid():
        st = backtest_period(symbol, short, long, run_start, measure_start, end)["stats"]
        rows.append({
            "short": short, "long": long,
            "总收益率": st["总收益率"], "年化收益率": st["年化收益率"],
            "最大回撤": st["最大回撤"], "夏普比率": st["夏普比率"],
        })
    return pd.DataFrame(rows)


def cmd_scan(symbol: str = "510300", refresh: bool = False) -> pd.DataFrame:
    """实验1：全区间参数扫描 + 热图。"""
    meta = UNIVERSE[symbol]
    df = run_grid(symbol, TRAIN_START, None)
    out = RESULTS_DIR / "param_scan" / symbol
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "param_results.csv", index=False, encoding="utf-8-sig")

    for col, fmt in [("夏普比率", "{:.2f}"), ("年化收益率", "{:+.1%}")]:
        pv = df.pivot(index="short", columns="long", values=col)
        plot_heatmap(pv, title=f"S1 参数扫描 · {col} · {meta['name']}({symbol}) 2015-2026",
                     fmt=fmt, save_path=out / f"heatmap_{col}.png")

    best = df.loc[df["夏普比率"].idxmax()]
    worst = df.loc[df["夏普比率"].idxmin()]
    print(f"[参数扫描] {meta['name']}({symbol}) 2015-2026，共 {len(df)} 组参数")
    print(df.to_string(index=False,
                       formatters={"总收益率": "{:+.1%}".format, "年化收益率": "{:+.1%}".format,
                                   "最大回撤": "{:+.1%}".format, "夏普比率": "{:.2f}".format}))
    print(f"\n夏普最优: MA{int(best['short'])}/{int(best['long'])} → 夏普 {best['夏普比率']:.2f}, "
          f"年化 {best['年化收益率']:+.1%}, 回撤 {best['最大回撤']:+.1%}")
    print(f"夏普最差: MA{int(worst['short'])}/{int(worst['long'])} → 夏普 {worst['夏普比率']:.2f}, "
          f"年化 {worst['年化收益率']:+.1%}, 回撤 {worst['最大回撤']:+.1%}")
    print(f"夏普中位数: {df['夏普比率'].median():.2f}  （最优-最差差距越悬殊、峰越尖，越要警惕过拟合）")
    return df


def cmd_overfit(symbol: str = "510300", refresh: bool = False) -> pd.DataFrame:
    """实验2：训练集选参数 → 测试集验证。"""
    meta = UNIVERSE[symbol]
    train = run_grid(symbol, TRAIN_START, None, TRAIN_END)
    test = run_grid(symbol, WARMUP, TEST_START)

    df = train.merge(test, on=["short", "long"], suffixes=("_训练", "_测试"))
    out = RESULTS_DIR / "param_scan" / symbol
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "overfit_results.csv", index=False, encoding="utf-8-sig")

    best_i = df["夏普比率_训练"].idxmax()
    best = df.loc[best_i]
    corr = df["夏普比率_训练"].corr(df["夏普比率_测试"], method="spearman")
    # 训练集最优参数在测试集的排名（百分位，0=测试集最差，1=最好）
    pct = (df["夏普比率_测试"] < df.loc[best_i, "夏普比率_测试"]).mean()

    plot_scatter(
        df["夏普比率_训练"], df["夏普比率_测试"],
        xlabel="训练集夏普 (2015-2021)", ylabel="测试集夏普 (2022-2026)",
        title=f"过拟合检验：训练 vs 测试 · {meta['name']}({symbol})  Spearman相关={corr:.2f}",
        highlight=(f"训练最优 MA{int(best['short'])}/{int(best['long'])}",
                   best["夏普比率_训练"], best["夏普比率_测试"]),
        save_path=out / "overfit_scatter.png",
    )

    print(f"[过拟合实验] {meta['name']}({symbol})：训练集 2015-2021 选参数，测试集 2022-2026 验证")
    print(df.sort_values("夏普比率_训练", ascending=False).to_string(
        index=False, formatters={c: "{:+.2f}".format for c in df.columns if "夏普" in c}))
    print(f"\n训练集最优参数 MA{int(best['short'])}/{int(best['long'])}:")
    print(f"  训练集夏普 {best['夏普比率_训练']:+.2f}  →  测试集夏普 {best['夏普比率_测试']:+.2f}"
          f"（测试集排名百分位 {pct:.0%}，中位数 {df['夏普比率_测试'].median():.2f}，"
          f"测试集最好 {df['夏普比率_测试'].max():.2f}）")
    print(f"训练/测试夏普的 Spearman 秩相关: {corr:.2f}")
    print("解读：相关越接近 0，说明'训练集选参'对未来越没有预测力 —— 参数不可信；")
    print("      训练最优参数若在测试集表现平庸，就是过拟合的现场证据。")
    return df


def cmd_showcase(symbol: str = "510300") -> None:
    """把训练集最优参数和'朴素默认'参数的完整净值曲线画在一起对比。"""
    df = pd.read_csv(RESULTS_DIR / "param_scan" / symbol / "overfit_results.csv")
    best = df.loc[df["夏普比率_训练"].idxmax()]
    short, long = int(best["short"]), int(best["long"])

    eq_best = backtest_period(symbol, short, long, WARMUP, TEST_START)
    eq_default = backtest_period(symbol, 5, 60, WARMUP, TEST_START)
    out = RESULTS_DIR / "param_scan" / symbol

    from quant.engine import BacktestEngine
    from quant.preprocess import load_bars
    bars = load_bars(symbol, UNIVERSE[symbol]["kind"], WARMUP, None)
    bh, _ = s1.make_engine(symbol).run_buy_hold(bars, limit_pct=UNIVERSE[symbol]["limit_pct"])
    bh_eq = bh["equity"].loc[TEST_START:]

    plot_backtest(
        eq_best["equity"]["equity"].loc[TEST_START:], benchmark=bh_eq,
        trades=eq_best["trades"],
        title=f"测试集(2022-2026)净值：训练集最优参数 MA{short}/{long}",
        save_path=out / "testset_best.png",
    )
    plot_backtest(
        eq_default["equity"]["equity"].loc[TEST_START:], benchmark=bh_eq,
        trades=eq_default["trades"],
        title="测试集(2022-2026)净值：朴素默认参数 MA5/60",
        save_path=out / "testset_default.png",
    )
    print(f"训练集最优 MA{short}/{long} 测试集: 夏普 {eq_best['stats']['夏普比率']:.2f}, "
          f"年化 {eq_best['stats']['年化收益率']:+.1%}, 回撤 {eq_best['stats']['最大回撤']:+.1%}")
    print(f"默认 MA5/60          测试集: 夏普 {eq_default['stats']['夏普比率']:.2f}, "
          f"年化 {eq_default['stats']['年化收益率']:+.1%}, 回撤 {eq_default['stats']['最大回撤']:+.1%}")
