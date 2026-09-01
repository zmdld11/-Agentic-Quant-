"""模拟盘信号器：把回测里验证过的规则用到"今天"。

这是项目从"研究历史"走向"面对未来"的第一步——不涉及任何真实下单，
只是每个交易日收盘后回答：按 S4 规则，我现在应该持有什么、多少仓位。

用法：
    python main.py signal            # 用本地缓存数据
    python main.py signal --refresh  # 先刷新5只ETF数据（收盘后用）

注意时序（和回测完全一致）：S4 是"月末收盘出信号 → 次月首个交易日
开盘执行"的月频策略。月中的大涨大跌不改变持仓——信号器显示的是
"最近一个月末"做出的决定，以及下次调仓的时点。
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pandas as pd

from quant.datasource import UNIVERSE
from strategies.s2_momentum import build_panel
from strategies.s4_rotation_plus import generate_weights

LOG_FILE = Path(__file__).resolve().parent.parent / "research" / "paper_s4_log.csv"
LOG_HEADER = ["信号日", "数据截至", "持仓", "当时动量", "年化波动", "记录时间"]


def s4_signal(refresh: bool = False, target_vol: float = 0.15) -> None:
    panel = build_panel(refresh=refresh)
    weights = generate_weights(panel, target_vol=target_vol)

    closes = pd.DataFrame({s: df["close"] for s, df in panel.items()})
    mom = closes / closes.shift(21) - 1
    vols = closes.pct_change().rolling(60).std() * np.sqrt(252)

    last = weights.index[-1]
    # 信号是在最近一个月末做出的（月中不换仓）
    month_ends = closes.index.to_series().groupby(closes.index.to_period("M")).max()
    signal_day = month_ends[month_ends <= last].iloc[-1]

    w = weights.loc[last]
    held = w[w > 0.001]
    rank = mom.loc[signal_day].sort_values(ascending=False)

    print(f"数据截至 {last.date()}；持仓决定日（最近月末）{signal_day.date()}")
    print(f"全池动量排名（{signal_day.date()} 收盘，21日）：")
    for s, m in rank.items():
        mark = "  ← 持有" if s in held.index else ""
        print(f"  {UNIVERSE[s]['name']:<8} 动量 {m:+7.2%}   年化波动 {vols.loc[last, s]:6.1%}"
              f"   目标仓位 {w[s]:6.1%}{mark}")

    if held.empty:
        decision = "空仓持币（池内无正动量资产）"
    else:
        decision = "；".join(f"{UNIVERSE[s]['name']} {sh:.0%}" for s, sh in held.items())
    print(f"\n当前信号：{decision}")
    print("执行规则：本信号自次月首个交易日开盘生效，持有至下一个月末重估。")

    # 落日志（模拟盘记录，攒几个月就能和真实行情对账）
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    new = not LOG_FILE.exists()
    with LOG_FILE.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if new:
            writer.writerow(LOG_HEADER)
        held_desc = decision if held.empty else decision.replace("；", " | ")
        mom_desc = " | ".join(f"{UNIVERSE[s]['name']} {m:+.1%}" for s, m in rank.items())
        vol_desc = " | ".join(f"{v:.0%}" for v in vols.loc[last, rank.index])
        writer.writerow([signal_day.date(), last.date(), held_desc, mom_desc, vol_desc,
                         pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")])
    print(f"已记录到 {LOG_FILE}")
