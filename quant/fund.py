"""AI 一号基金：50 万模拟资金的自动交易组合（模拟盘，不接实盘）。

基金合同摘要（全文见 research/2026-09-07_fund_mandate.md）：
- 初始资金 500,000；每日收盘后自动结算（定时器 18:40 或手动 main.py fund）
- 双引擎配置（季度再平衡回 60/40）：
    轮动引擎 60%：S4 波动率目标轮动（月末信号→次月首日开盘调仓）
    网格引擎 40%：510500 网格（20格，区间=成立前244日高低点，之后不重算）
- 风控预案：基金自峰值回撤超 20% → 网格停止买入（卖出照常）、轮动波动
  目标减半；净值重回前高后自动恢复
- 费率口径与回测一致（佣金万2.5最低5元+滑点0.1%，ETF免印花税）

诚实声明：为什么不"选股"？本项目 S5/WQ101 因子验尸证明公开选股因子
在 A 股无超额（IC 全灭）——本基金的"量化模型"是经过三道闸门验证的
配置与择时规则，而非未经验证的选股幻想。回测年化 ~8-9%（组合），
最大回撤 ~-20%，预期一年后 50 万大概率的区间在 45-58 万之间，
不是暴富机器。
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from quant.datasource import UNIVERSE
from quant.engine import CostModel
from strategies.s2_momentum import build_panel
from strategies.s4_rotation_plus import generate_weights as s4_weights

STATE_FILE = Path(__file__).resolve().parent.parent / "data" / "processed" / "fund_alpha.json"
INITIAL_CAPITAL = 500_000.0
SLEEVE_ROTATION_SHARE = 0.6          # 轮动引擎占比
GRID_SYMBOL = "510500"               # 网格引擎标的
GRID_N = 20                          # 格数
CALIB_DAYS = 244                     # 网格区间校准窗口
DRAWDOWN_GUARD = -0.20               # 回撤预案触发线

COST = CostModel(stamp_tax_rate=0.0)  # 全 ETF，免印花税


def _load() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return None


def _save(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1, default=str),
                          encoding="utf-8")


def _init_state(bars_grid: pd.DataFrame) -> dict:
    """开账：成立日=今天，网格区间=成立前244个交易日的高低点。

    注意本基金与 paper 账本不同：**不回填历史**——今天成立、下一个
    交易日起按规则交易，净值从今天起前瞻记录。
    """
    cal = bars_grid.iloc[-CALIB_DAYS:]
    p_low = float(cal["low"].min())
    p_high = float(cal["high"].max())
    return {
        "inception": str(pd.Timestamp.now().normalize().date()),
        "guard_active": False,
        "rotation": {"cash": INITIAL_CAPITAL * SLEEVE_ROTATION_SHARE,
                     "position": None, "last_signal": None},
        "grid": {"cash": INITIAL_CAPITAL * (1 - SLEEVE_ROTATION_SHARE),
                 "shares": 0, "p_low": p_low, "p_high": p_high, "step": (p_high - p_low) / GRID_N,
                 "unit_cash": INITIAL_CAPITAL * (1 - SLEEVE_ROTATION_SHARE) / (GRID_N + 1),
                 "last_day": None, "trades": 0},
        "trades": [],
        "nav_history": [],
    }


# ── 轮动引擎（S4：月末信号 → 次月首日开盘，与 paper.py 同规则）──────────

def _run_rotation(state: dict, panel: dict[str, pd.DataFrame], weights: pd.DataFrame,
                  opening_prices: pd.DataFrame) -> None:
    rot = state["rotation"]
    closes = pd.DataFrame({s: df["close"] for s, df in panel.items()})
    inception = pd.Timestamp(state["inception"])
    # 成立后的首个可执行交易日（当前有效信号在此建仓；之后的月末信号自然轮动）
    upcoming = closes.index[closes.index > inception]
    if len(upcoming) == 0:
        return
    first_exec = upcoming[0]

    month_ends = closes.index.to_series().groupby(closes.index.to_period("M")).max().sort_values()
    last = pd.Timestamp(rot["last_signal"]) if rot["last_signal"] else None
    for me in month_ends:
        if me not in weights.index:
            continue
        if last is not None and me <= last:
            continue
        later = closes.index[closes.index > me]
        if len(later) == 0:
            break   # 信号已出未到执行日，下次运行再办
        exec_day = max(later[0], first_exec)   # 新基金：首个信号钳制到成立后首日
        row = weights.loc[me]
        held = row[row > 0.001]

        # 波动目标减半预案：基金深回撤期间的新信号用半档目标
        tv = 0.075 if state["guard_active"] else 0.15
        if rot["position"] is not None:
            pos = rot["position"]
            growth = opening_prices.at[exec_day, pos["symbol"]] / pos["entry_price"]
            rot["cash"] += pos["entry_value"] * growth
            rot["position"] = None
        if len(held):
            sym = held.index[0]
            w_full = float(held.iloc[0])
            w = w_full * (tv / 0.15)          # 目标波动减半 → 仓位减半
            rot["position"] = {"symbol": sym, "weight": round(w, 4),
                               "entry_date": str(exec_day.date()),
                               "entry_price": float(opening_prices.at[exec_day, sym]),
                               "entry_value": rot["cash"] * w}
            rot["cash"] *= (1 - w)
        state["trades"].append({
            "date": str(exec_day.date()), "engine": "轮动",
            "action": (held.index[0] if len(held) else "空仓"),
            "weight": round(float(held.iloc[0]) * (tv / 0.15), 4) if len(held) else 0.0})
        rot["last_signal"] = str(me.date())


# ── 网格引擎（与 s6_grid 回测同一套规则：跌穿格线买、涨穿卖、T+1）────────

def _run_grid(state: dict, bars: pd.DataFrame) -> None:
    g = state["grid"]
    n, step, p_low = GRID_N, g["step"], g["p_low"]

    def idx(p: float) -> int:
        return max(0, min(n, int((p - p_low) / step)))

    def lots(price: float, budget: float) -> int:
        return int(min(g["unit_cash"], budget) / (price * 100)) * 100

    start_i = 0
    inception = pd.Timestamp(state["inception"])
    prev_i = None
    for date, bar in bars.iloc[start_i:].iterrows():
        # 跳过成立前 与 已处理过的日子（幂等追账），但推进 prev_i
        if date <= inception or (g["last_day"] and date <= pd.Timestamp(g["last_day"])):
            prev_i = idx(float(bar["close"]))
            continue
        o, h, l, c = (float(bar[k]) for k in ("open", "high", "low", "close"))
        if prev_i is None:
            # 起始建仓：买入"上方格数"份（涨一格有货卖、跌一格有钱补）
            for _ in range(n - idx(c)):
                q = lots(c, g["cash"])
                fee = COST.buy_cost(q * c)
                if q < 100 or q * c + fee > g["cash"]:
                    break
                g["cash"] -= q * c + fee
                g["shares"] += q
                g["trades"] += 1
        else:
            bought_today = False
            # 下跌穿越买入（回撤预案触发时停止加仓）
            if not state["guard_active"]:
                for k in range(prev_i - 1, idx(l) - 1, -1):
                    price = p_low + k * step
                    q = lots(price, g["cash"])
                    fee = COST.buy_cost(q * price)
                    if q < 100 or q * price + fee > g["cash"]:
                        continue
                    g["cash"] -= q * price + fee
                    g["shares"] += q
                    g["trades"] += 1
                    bought_today = True
            # 上涨穿越卖出（当日买入受 T+1 限制）
            if not bought_today:
                for k in range(prev_i + 1, idx(h) + 1):
                    price = p_low + k * step
                    q = max(lots(price, g["unit_cash"]), 100)
                    q = min(q, g["shares"])
                    if q <= 0:
                        continue
                    fee = COST.sell_cost(q * price)
                    g["cash"] += q * price - fee
                    g["shares"] -= q
                    g["trades"] += 1
        prev_i = idx(float(bar["close"]))
        g["last_day"] = str(date.date())
        if state["inception"] is None:
            state["inception"] = str(date.date())


def run(refresh: bool = False) -> dict:
    """每日结算入口（幂等，自动追账）：补齐两引擎交易 + 按最新收盘估值。"""
    panel = build_panel(refresh=refresh)
    closes = pd.DataFrame({s: df["close"] for s, df in panel.items()})
    opens = pd.DataFrame({s: df["open"] for s, df in panel.items()})

    from quant.preprocess import load_bars
    bars_grid = load_bars(GRID_SYMBOL, "etf", start="2025-06-01", refresh=refresh)

    state = _load()
    if state is None:
        state = _init_state(bars_grid)
        _save(state)

    weights = s4_weights(panel)
    _run_rotation(state, panel, weights, opens)
    _run_grid(state, bars_grid)

    # 估值与回撤预案状态机
    mark_day = closes.index[-1]
    grid_close = float(bars_grid["close"].iloc[-1])
    rot = state["rotation"]
    rot_value = rot["cash"]
    if rot["position"] is not None:
        pos = rot["position"]
        rot_value += pos["entry_value"] * closes.at[mark_day, pos["symbol"]] / pos["entry_price"]
    g = state["grid"]
    grid_value = g["cash"] + g["shares"] * grid_close
    nav = rot_value + grid_value

    peak = max([h["nav"] for h in state["nav_history"]], default=INITIAL_CAPITAL)
    new_guard = nav / max(peak, nav, INITIAL_CAPITAL) - 1 <= DRAWDOWN_GUARD
    if new_guard and not state["guard_active"]:
        state["guard_active"] = True
    elif state["guard_active"] and nav >= peak:
        state["guard_active"] = False   # 净值重回前高，预案解除

    hist_row = {"date": str(mark_day.date()), "nav": round(nav, 2),
                "rotation": round(rot_value, 2), "grid": round(grid_value, 2)}
    if state["nav_history"] and state["nav_history"][-1]["date"] == hist_row["date"]:
        state["nav_history"][-1] = hist_row
    else:
        state["nav_history"].append(hist_row)
    _save(state)

    # 对账单（基准 as-of：成立日可能非交易日）
    inc = pd.Timestamp(state.get("inception") or str(mark_day.date()))
    base_days = closes.index[closes.index <= inc]
    bh0 = closes.at[base_days[-1] if len(base_days) else closes.index[0], "510300"]
    bh = closes.at[mark_day, "510300"] / bh0
    pos = rot["position"]
    pos_desc = (f"{UNIVERSE[pos['symbol']]['name']} {pos['weight']:.0%}"
                if pos else "空仓")
    print(f"===== AI 一号基金对账单（{inc.date()} 成立 · 初始 {INITIAL_CAPITAL:,.0f}） =====")
    print(f"结算日: {mark_day.date()}")
    print(f"基金净值: {nav:,.0f}  → 累计 {nav / INITIAL_CAPITAL - 1:+.2%}")
    print(f"  轮动引擎({SLEEVE_ROTATION_SHARE:.0%}): {rot_value:,.0f}  持仓 {pos_desc}")
    print(f"  网格引擎({1 - SLEEVE_ROTATION_SHARE:.0%}): {grid_value:,.0f}  "
          f"持基 {g['shares']:,} 份 / 网格 {g['p_low']:.2f}~{g['p_high']:.2f} / 累计成交 {g['trades']} 笔")
    print(f"同期沪深300ETF: {bh - 1:+.2%}")
    print(f"回撤预案: {'🔴 已触发（网格停买/波动目标减半）' if state['guard_active'] else '🟢 未触发'}")
    if state["trades"]:
        print("最近3笔:", " | ".join(
            f"{t['date']} {t['engine']}→{t['action']}" for t in state["trades"][-3:]))
    return state
