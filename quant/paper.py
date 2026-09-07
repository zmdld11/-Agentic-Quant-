"""模拟盘账户：把 S4 的月末信号变成一本可以长期对账的账本。

与 live.s4_signal（只打印建议）不同，本模块维护一个**虚拟账户**：
- 每个月末信号 → 次月首个交易日开盘按"信号权重"调仓（与回测同一套执行规则）
- 每次运行自动补齐错过的月份（服务器停机/忘跑也能追账，幂等可重复执行）
- 账本状态存 data/processed/paper_account.json（NAV、持仓、交易记录、净值历史）

对账口径：
- 买入按执行日开盘价，市值按最新收盘价估算（与回测 engine 的执行时序一致）
- 不含交易成本（模拟盘按净值口径对账；回测版本含成本，两者差异≈1%/年）
- 基准对照：沪深300ETF 同期买入持有

用法：
    python main.py paper              # 补账 + 按最新收盘结算 + 打印对账单
    python main.py paper --refresh    # 先刷新ETF数据再结算（收盘后用）
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from quant.datasource import UNIVERSE
from strategies.s2_momentum import build_panel
from strategies.s4_rotation_plus import generate_weights

STATE_FILE = Path(__file__).resolve().parent.parent / "data" / "processed" / "paper_account.json"
INITIAL_CAPITAL = 1_000_000.0


def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"nav": INITIAL_CAPITAL, "cash": INITIAL_CAPITAL, "position": None,
            "last_signal": None, "trades": [], "nav_history": [],
            "inception": None}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1,
                                     default=str), encoding="utf-8")


def run(refresh: bool = False) -> dict:
    """补齐错过的月度调仓 + 按最新收盘结算。幂等，可每天跑。"""
    panel = build_panel(refresh=refresh)
    weights = generate_weights(panel)
    closes = pd.DataFrame({s: df["close"] for s, df in panel.items()})
    opens = pd.DataFrame({s: df["open"] for s, df in panel.items()})

    # 月末信号日及其目标持仓（symbol, weight），空仓为 (None, 0)
    month_ends = closes.index.to_series().groupby(closes.index.to_period("M")).max().sort_values()
    signals: dict[pd.Timestamp, tuple[str | None, float]] = {}
    for me in month_ends:
        if me not in weights.index:
            continue
        row = weights.loc[me]
        held = row[row > 0.001]
        signals[me] = (held.index[0], float(held.iloc[0])) if len(held) else (None, 0.0)

    state = _load_state()
    if state["inception"] is None:
        state["inception"] = str(month_ends.iloc[0].date())

    # ---- 补账：处理上次记账之后的所有月末信号 ----
    last = pd.Timestamp(state["last_signal"]) if state["last_signal"] else None
    for me, (sym, w) in signals.items():
        if last is not None and me <= last:
            continue
        # 执行日 = 信号日后的下一个交易日
        later = closes.index[closes.index > me]
        if len(later) == 0:
            break   # 信号已出但未到执行日（月末刚过）→ 下次运行再执行
        exec_day = later[0]

        # 平掉旧仓（按执行日开盘估值）
        if state["position"] is not None:
            pos = state["position"]
            growth = opens.at[exec_day, pos["symbol"]] / pos["entry_price"]
            state["cash"] += pos["entry_value"] * growth
            state["position"] = None

        # 开新仓（权重 w，按执行日开盘）
        if sym is not None and w > 0:
            equity = state["cash"]
            state["position"] = {
                "symbol": sym, "weight": round(w, 4),
                "entry_date": str(exec_day.date()),
                "entry_price": float(opens.at[exec_day, sym]),
                "entry_value": equity * w,
            }
            state["cash"] = equity * (1 - w)
        state["trades"].append({
            "signal_date": str(me.date()), "exec_date": str(exec_day.date()),
            "symbol": sym, "name": UNIVERSE.get(sym, {}).get("name", "空仓"),
            "weight": round(w, 4),
        })
        state["last_signal"] = str(me.date())

    # ---- 按最新收盘结算 ----
    mark_day = closes.index[-1]
    pos_value = 0.0
    if state["position"] is not None:
        pos = state["position"]
        pos_value = pos["entry_value"] * closes.at[mark_day, pos["symbol"]] / pos["entry_price"]
    state["nav"] = state["cash"] + pos_value
    hist_row = {"date": str(mark_day.date()), "nav": round(state["nav"], 2)}
    if not state["nav_history"] or state["nav_history"][-1]["date"] != hist_row["date"]:
        state["nav_history"].append(hist_row)
    else:
        state["nav_history"][-1] = hist_row
    _save_state(state)

    # ---- 对账单 ----
    # as-of 查基准起点：数据源兜底/延迟时开档日可能没有精确对齐的交易日
    inc = pd.Timestamp(state["inception"])
    earlier = closes.index[closes.index <= inc]
    bh0 = closes.at[earlier[-1] if len(earlier) else closes.index[0], "510300"]
    bh = closes.at[mark_day, "510300"] / bh0
    pos = state["position"]
    pos_desc = (f"{UNIVERSE[pos['symbol']]['name']}({pos['symbol']}) "
                f"{pos['weight']:.0%}仓，{pos['entry_date']} 开盘建仓"
                if pos else "空仓持币")
    total_ret = state["nav"] / INITIAL_CAPITAL - 1
    excess = (1 + total_ret) - bh
    print(f"===== S4 模拟盘对账单（{state['inception']} 开档） =====")
    print(f"最新结算日: {mark_day.date()}")
    print(f"当前持仓: {pos_desc}")
    print(f"账户净值: {state['nav']:,.0f} / {INITIAL_CAPITAL:,.0f}"
          f"  → 累计 {total_ret:+.2%}")
    print(f"同期沪深300ETF: {bh - 1:+.2%}   超额: {excess:+.2%}")
    print(f"已执行调仓 {len(state['trades'])} 次；净值历史 {len(state['nav_history'])} 天"
          f"（data/processed/paper_account.json）")
    if state["trades"]:
        print("最近3笔:", " | ".join(
            f"{t['exec_date']} {t['name']} {t['weight']:.0%}"
            for t in state["trades"][-3:]))
    return state
