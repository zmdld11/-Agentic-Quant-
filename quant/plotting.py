"""画图：净值曲线 + 回撤图 + 买卖点标注。

图是给自己看的证据：曲线是否平滑、回撤发生在哪几年、买卖点是否合理，
比一行"年化 15%"能暴露的问题多得多。
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 无界面环境也能保存图片
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# 中文字体：Windows 用雅黑；Linux 服务器回退到 Noto/文泉驿（无中文字体会画方框）
plt.rcParams["font.sans-serif"] = [
    "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "WenQuanYi Micro Hei"]
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


def plot_lines(
    series_dict: dict[str, pd.Series],
    title: str = "",
    ylabel: str = "净值（起点=1）",
    save_path: str | Path | None = None,
) -> None:
    """多条净值线画在一张图（因子分组、多策略对比等）。"""
    fig, ax = plt.subplots(figsize=(11, 6))
    for name, s in series_dict.items():
        if s is None or s.dropna().empty:
            continue
        nav = s / s.dropna().iloc[0]
        ax.plot(nav.index, nav.values, label=name, lw=1.3)
    ax.set_title(title, fontsize=12)
    ax.set_ylabel(ylabel)
    ax.legend(loc="upper left")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    if save_path is not None:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150)
        print(f"图已保存: {save_path}")
    plt.close(fig)


def plot_heatmap(
    values: pd.DataFrame,
    title: str = "",
    fmt: str = "{:.2f}",
    save_path: str | Path | None = None,
) -> None:
    """参数扫描热图：values 的行/列是两个参数，单元格是指标值。

    用红-黄-绿色阶（红=差，绿=好），负值用 TwoSlopeNorm 以 0 为中心。
    """
    from matplotlib.colors import TwoSlopeNorm

    arr = values.values.astype(float)
    vmin, vmax = np.nanmin(arr), np.nanmax(arr)
    norm = TwoSlopeNorm(vmin=min(vmin, 0), vcenter=0, vmax=max(vmax, 0)) if vmin < 0 < vmax else None

    fig, ax = plt.subplots(figsize=(8, 4.8))
    im = ax.imshow(arr, cmap="RdYlGn", aspect="auto", norm=norm)
    ax.set_xticks(range(len(values.columns)), [str(c) for c in values.columns])
    ax.set_yticks(range(len(values.index)), [str(i) for i in values.index])
    ax.set_xlabel("长期均线天数")
    ax.set_ylabel("短期均线天数")
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            v = arr[i, j]
            if not pd.isna(v):
                ax.text(j, i, fmt.format(v), ha="center", va="center", fontsize=9)
    ax.set_title(title, fontsize=12)
    fig.colorbar(im, ax=ax, shrink=0.9)
    fig.tight_layout()
    if save_path is not None:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150)
        print(f"图已保存: {save_path}")
    plt.close(fig)


def plot_scatter(
    x: pd.Series,
    y: pd.Series,
    xlabel: str = "",
    ylabel: str = "",
    title: str = "",
    highlight: tuple[str, float, float] | None = None,
    save_path: str | Path | None = None,
) -> None:
    """散点图（如训练集指标 vs 测试集指标）。

    highlight: (标签, x, y) —— 额外放大标注一个关键点。
    """
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(x, y, s=60, alpha=0.75, color="tab:blue", edgecolor="white")
    ax.axhline(0, color="gray", lw=0.8, alpha=0.6)
    ax.axvline(0, color="gray", lw=0.8, alpha=0.6)
    if highlight is not None:
        label, hx, hy = highlight
        ax.scatter([hx], [hy], s=200, marker="*", color="tab:red", zorder=5)
        ax.annotate(label, (hx, hy), xytext=(8, 8), textcoords="offset points",
                    fontsize=11, color="tab:red")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=12)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    if save_path is not None:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150)
        print(f"图已保存: {save_path}")
    plt.close(fig)
