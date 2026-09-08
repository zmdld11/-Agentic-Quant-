import sys
import os
import traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

from src.models.agentic_quant import AgenticQuant

load_dotenv()

app = FastAPI(title="Agentic Quant")

api_key = os.getenv("DEEPSEEK_API_KEY")
quant_engine = AgenticQuant(api_key=api_key) if api_key else None


@app.on_event("startup")
async def start_background_jobs():
    """启动主进程内置定时器（周一至五自动跑 news/paper，见 quant/scheduler.py）。"""
    from quant.config import load_env
    load_env()
    from quant import scheduler
    scheduler.start_scheduler()


@app.get("/api/scheduler")
async def scheduler_status():
    from quant import scheduler
    return scheduler.status()


class AnalyzeRequest(BaseModel):
    symbol: str


class ReportRequest(BaseModel):
    symbol: str
    data_summary: dict


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "cache_size": len(quant_engine.cache) if quant_engine else 0,
        "engine_ready": quant_engine is not None
    }


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    if not quant_engine:
        raise HTTPException(status_code=503, detail="引擎未初始化，请检查 DEEPSEEK_API_KEY")
    symbol = req.symbol.strip()
    if not symbol.isdigit() or len(symbol) != 6:
        raise HTTPException(status_code=400, detail="请输入6位数字A股代码")
    try:
        result = quant_engine.compile_and_predict(symbol)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@app.post("/api/report")
async def get_report(req: ReportRequest):
    if not quant_engine:
        raise HTTPException(status_code=503, detail="引擎未初始化，请检查 DEEPSEEK_API_KEY")
    symbol = req.symbol.strip()
    if not symbol.isdigit() or len(symbol) != 6:
        raise HTTPException(status_code=400, detail="请输入6位数字A股代码")
    try:
        report_text = quant_engine.get_report(symbol, req.data_summary)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    return {"symbol": symbol, "report": report_text}


@app.get("/api/kline/{code}")
async def get_kline(code: str, period: str = "3m"):
    if not quant_engine:
        raise HTTPException(status_code=503, detail="引擎未初始化")
    days_map = {"1m": 22, "3m": 60, "6m": 120, "1y": 250}
    display_bars = days_map.get(period, 60)
    # Always fetch 250 bars so MACD/RSI have enough history to calculate
    kline = quant_engine.fetch_kline_range(code, days=250)
    return {"symbol": code, "kline_data": kline, "count": len(kline), "display_bars": display_bars}


class SyncRequest(BaseModel):
    symbol_a: str
    symbol_b: str

@app.post("/api/sync")
async def sync_stocks(req: SyncRequest):
    if not quant_engine:
        raise HTTPException(status_code=503, detail="引擎未初始化")
    a = req.symbol_a.strip()
    b = req.symbol_b.strip()
    for s in [a, b]:
        if not s.isdigit() or len(s) != 6:
            raise HTTPException(status_code=400, detail=f"无效代码: {s}")
    try:
        result = quant_engine.calc_stock_sync(a, b)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result

@app.get("/api/news")
async def get_news(date: str = None):
    if not quant_engine:
        raise HTTPException(status_code=503, detail="引擎未初始化")
    try:
        result = quant_engine.get_cached_news(date)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    return result


# ── 驾驶舱：量化管线的数据产物（模拟盘账户 + AI基金 + LLM情绪面板）──────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAPER_STATE = os.path.join(ROOT, "data", "processed", "paper_account.json")
FUND_STATE = os.path.join(ROOT, "data", "processed", "fund_alpha.json")
SENTIMENT_PANEL = os.path.join(ROOT, "data", "processed", "sentiment_panel.parquet")
TELEGRAPH = os.path.join(ROOT, "data", "raw", "news", "cls_telegraph.parquet")


@app.get("/api/fund")
async def get_fund():
    """AI 一号基金（50万双引擎）对账数据。"""
    import json as _json
    if not os.path.exists(FUND_STATE):
        return {"available": False, "message": "基金未成立：先运行 python main.py fund"}
    with open(FUND_STATE, encoding="utf-8") as f:
        state = _json.load(f)
    initial = 500_000.0
    nav = state["nav_history"][-1]["nav"] if state.get("nav_history") else initial
    last = state["nav_history"][-1] if state.get("nav_history") else {}
    g = state.get("grid", {})
    pos = state.get("rotation", {}).get("position")
    return {
        "available": True,
        "inception": state.get("inception"),
        "nav": nav,
        "total_return": nav / initial - 1,
        "initial": initial,
        "rotation": {"value": last.get("rotation"),
                     "position": (pos["symbol"] if pos else None),
                     "weight": (pos["weight"] if pos else 0)},
        "grid": {"value": last.get("grid"), "shares": g.get("shares", 0),
                 "range": f"{g.get('p_low', 0):.2f}~{g.get('p_high', 0):.2f}",
                 "trades": g.get("trades", 0)},
        "guard_active": state.get("guard_active", False),
        "trades": list(reversed(state.get("trades", [])))[:10],
        "nav_history": state.get("nav_history", []),
    }


@app.get("/api/paper")
async def get_paper():
    """模拟盘对账数据：净值/持仓/调仓记录 + 沪深300基准曲线。"""
    import json as _json
    if not os.path.exists(PAPER_STATE):
        return {"available": False, "message": "模拟盘未开账：先运行 python main.py paper"}
    with open(PAPER_STATE, encoding="utf-8") as f:
        state = _json.load(f)
    initial = 1_000_000.0
    nav = float(state.get("nav", initial))
    # 基准：自开档日的沪深300ETF收盘曲线（读本地缓存，无缓存则省略）
    benchmark = []
    try:
        import pandas as pd
        from quant.preprocess import load_bars
        bars = load_bars("510300", "etf", start=state.get("inception", "2016-01-01"))
        closes = bars["close"] / bars["close"].iloc[0]
        benchmark = [{"date": d.strftime("%Y-%m-%d"), "nav": round(float(v), 4)}
                     for d, v in closes.items()]
    except Exception:
        pass
    pos = state.get("position")
    return {
        "available": True,
        "inception": state.get("inception"),
        "nav": nav,
        "total_return": nav / initial - 1,
        "benchmark_return": (benchmark[-1]["nav"] - 1) if benchmark else None,
        "excess": (nav / initial) - (benchmark[-1]["nav"] if benchmark else 1),
        "position": pos,
        "trades": list(reversed(state.get("trades", [])))[:12],
        "nav_history": state.get("nav_history", []),
        "benchmark": benchmark,
        "note": "净值曲线随每日结算自动生长；回测版本(含成本)见 results/",
    }


@app.get("/api/sentiment")
async def get_sentiment():
    """LLM情绪面板：温度计 + 多空快讯榜 + 近期走势。"""
    if not (os.path.exists(SENTIMENT_PANEL) and os.path.exists(TELEGRAPH)):
        return {"available": False, "message": "情绪面板不存在：先运行 python main.py news --collect"}
    import pandas as pd
    panel = pd.read_parquet(SENTIMENT_PANEL)
    tele = pd.read_parquet(TELEGRAPH)
    scored = tele[tele["score"].notna()]
    if scored.empty:
        return {"available": False, "message": "尚无打分样本：配置 LLM_API_KEY 后运行 news --collect"}
    recent = panel.dropna(subset=["mean_score"]).tail(30)
    def _rows(df):
        return [{"title": str(t)[:60], "score": round(float(s), 2)}
                for t, s in zip(df["title"], df["score"])]
    return {
        "available": True,
        "thermometer": round(float(scored["score"].tail(30).mean()), 3),
        "bull_pct": float((scored["score"] > 0.1).mean()),
        "bear_pct": float((scored["score"] < -0.1).mean()),
        "top_bull": _rows(scored.nlargest(5, "score")),
        "top_bear": _rows(scored.nsmallest(5, "score")),
        "trend": [{"date": str(d)[:10], "score": round(float(v), 3)}
                  for d, v in zip(recent["date"], recent["mean_score"])],
        "n_scored": int(len(scored)),
    }

@app.get("/")
async def index():
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    return FileResponse(os.path.join(static_dir, "index.html"))


static_dir = os.path.join(os.path.dirname(__file__), "static")

@app.get("/favicon.ico")
async def favicon_ico():
    return FileResponse(os.path.join(static_dir, "favicon.svg"), media_type="image/svg+xml")

app.mount("/static", StaticFiles(directory=static_dir), name="static")
