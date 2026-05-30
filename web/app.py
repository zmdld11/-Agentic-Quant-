import sys
import os
import traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from src.models.agentic_quant import AgenticQuant

load_dotenv()

app = FastAPI(title="Agentic Quant")

api_key = os.getenv("DEEPSEEK_API_KEY")
quant_engine = AgenticQuant(api_key=api_key) if api_key else None


class AnalyzeRequest(BaseModel):
    symbol: str


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


@app.get("/api/kline/{code}")
async def get_kline(code: str, period: str = "3m"):
    if not quant_engine:
        raise HTTPException(status_code=503, detail="引擎未初始化")
    days_map = {"1m": 22, "3m": 60, "6m": 120, "1y": 250}
    display_bars = days_map.get(period, 60)
    # Always fetch 250 bars so MACD/RSI have enough history to calculate
    kline = quant_engine.fetch_kline_range(code, days=250)
    return {"symbol": code, "kline_data": kline, "count": len(kline), "display_bars": display_bars}


@app.get("/")
async def index():
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    return FileResponse(os.path.join(static_dir, "index.html"))


static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")
