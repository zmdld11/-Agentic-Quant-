"""画图：净值曲线 + 回撤图 + 买卖点标注。

图是给自己看的证据：曲线是否平滑、回撤发生在哪几年、买卖点是否合理，
比一行"年化 15%"能暴露的问题多得多。
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 无界面环境也能保存图片
import matplotlib.pyplot as plt
import pandas as pd

# Windows 自带中文字体，解决 matplotlib 中文乱码
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False


def plot_backtest(
    equity: pd.Series,
    benchmark: pd.Series | None = None,
    benchmark_label: str = "基准(买入持有)",
    trades: pd.DataFrame | None = None,
    title: str = "",
    save_path: str | Path | None = None,
) -> None:
    """两层面板：上=策略净值 vs 基准 + 买卖点；下=回撤面积。"""
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(12, 8), sharex=True, gridspec_kw={"height_ratios": [3, 1]},
    )

    nav = equity / equity.iloc[0]
    ax1.plot(nav.index, nav.values, label="策略净值", lw=1.4, color="tab:blue")

    if benchmark is not None:
        bench = benchmark.reindex(equity.index).ffill().dropna()
        if len(bench):
            bench = bench / bench.iloc[0]
            ax1.plot(bench.index, bench.values, label=benchmark_label,
                     lw=1.0, alpha=0.75, color="tab:gray")

    if trades is not None and len(trades):
        for action, marker, color, y_off in [("BUY", "^", "tab:red", 0.02), ("SELL", "v", "tab:green", -0.02)]:
            sub = trades[trades["action"] == action]
            if len(sub):
                pts = nav.reindex(sub["date"]).dropna()
                ax1.scatter(pts.index, pts.values * (1 + y_off), marker=marker,
                            color=color, s=46, zorder=5, label=f"{action} {len(sub)}次")

    ax1.set_title(title or "回测净值曲线", fontsize=13)
    ax1.set_ylabel("净值（起点=1）")
    ax1.legend(loc="upper left")
    ax1.grid(alpha=0.3)

    dd = equity / equity.cummax() - 1
    ax2.fill_between(dd.index, dd.values, 0, color="tab:red", alpha=0.45)
    ax2.set_ylabel("回撤")
    ax2.set_xlabel("")
    ax2.grid(alpha=0.3)
    fig.tight_layout()

    if save_path is not None:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150)
        print(f"图已保存: {save_path}")
    plt.close(fig)
