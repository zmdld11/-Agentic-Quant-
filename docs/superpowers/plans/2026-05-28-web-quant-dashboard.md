# Web 量化投研看板 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 QQ 机器人股票系统改为 Web 端量化看板，跑在阿里云 2C2G 服务器上

**Architecture:** FastAPI 同一进程 serve 前端 HTML + API，Baostock 替换 akshare K 线数据源，systemd 守护。博客 (GitHub Pages) 导航栏加外链跳转。

**Tech Stack:** Python/FastAPI + Baostock + akshare(新闻) + DeepSeek + ECharts + 原生 HTML/CSS/JS

---

## 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | `web/app.py` | FastAPI 主程序 (3个API + 静态文件serve) |
| 新增 | `web/static/index.html` | 前端页面 |
| 新增 | `web/static/style.css` | 样式 (CSS变量双主题) |
| 新增 | `web/static/app.js` | 前端逻辑 (ECharts图表 + API调用) |
| 新增 | `web/quant.service` | systemd 开机自启配置 |
| 新增 | `start_web.sh` | 一键启动脚本 |
| 新增 | `DEPLOYMENT.md` | 部署配置与使用说明 |
| 修改 | `src/models/agentic_quant.py` | K线换 Baostock, compile_and_predict 返回 dict, 新增 fetch_kline_range |
| 修改 | `requirements.txt` | 去掉 nonebot2/nonebot-adapter-onebot，加 fastapi/uvicorn/baostock |
| 删除 | `bot.py` | QQ 机器人入口 |
| 删除 | `启动机器人.bat` | Windows 启动 |
| 删除 | `start_bot.sh` | 旧启动脚本 |
| 删除 | `QQ_BOT_README.md` | QQ 文档 |
| 删除 | `markdown/Napcat指令.md` | Napcat 说明 |

---

### Task 1: 清理无用文件

删除 QQ/Napcat 相关的 5 个文件:
- `bot.py`
- `启动机器人.bat`
- `start_bot.sh`
- `QQ_BOT_README.md`
- `markdown/Napcat指令.md`

```bash
git rm bot.py 启动机器人.bat start_bot.sh QQ_BOT_README.md markdown/Napcat指令.md
```

---

### Task 2: 改造 AgenticQuant 引擎

**文件:** `src/models/agentic_quant.py`

#### 2.1: 添加 Baostock 依赖和辅助方法

在文件顶部 import 区域加上 `import baostock as bs`。添加 `_to_baostock_code()` 静态方法：

```python
@staticmethod
def _to_baostock_code(symbol: str) -> str:
    """600519 -> sh.600519, 002594 -> sz.002594"""
    if symbol.startswith('6'):
        return f"sh.{symbol}"
    elif symbol.startswith(('0', '3')):
        return f"sz.{symbol}"
    elif symbol.startswith(('4', '8')):
        return f"bj.{symbol}"
    return f"sz.{symbol}"
```

#### 2.2: 重写 fetch_company_profile()

用 `bs.query_stock_basic()` 替换 `ak.stock_profile_cninfo()`：

```python
def fetch_company_profile(self, symbol: str) -> dict:
    cache_key = f"profile_{symbol}"
    if cached := self._get_cache(cache_key): return cached
    
    print(f"正在获取 [{symbol}] 的公司基本信息与行业属性...")
    try:
        bs.login()
        rs = bs.query_stock_basic(code=self._to_baostock_code(symbol))
        data = rs.get_data()
        bs.logout()
        
        if not data.empty:
            row = data.iloc[0]
            res = {
                "name": row['code_name'],
                "industry": row.get('industry', '未知') if 'industry' in data.columns else '未知',
                "business": row.get('business', '未知') if 'business' in data.columns else '未知',
                "brief": f"{row['code_name']}，上市日期: {row.get('ipoDate', 'N/A')}"
            }
            self._set_cache(cache_key, res)
            return res
    except Exception as e:
        print(f"获取公司资料失败: {e}")
        try: bs.logout()
        except: pass
    return {"name": f"A股代码 {symbol}", "industry": "未知", "business": "未知", "brief": "缺少资料"}
```

#### 2.3: 重写 fetch_quant_status()

用 `bs.query_history_k_data_plus()` 替换 `ak.stock_zh_a_hist()` 和备用的腾讯源。后端指标计算逻辑(pandas)完全不变。

```python
def fetch_quant_status(self, symbol: str) -> dict:
    cache_key = f"quant_{symbol}"
    if cached := self._get_cache(cache_key): return cached
    
    print(f"正在获取 [{symbol}] 最新的K线数据并计算多维量化特征...")
    try:
        bs.login()
        code = self._to_baostock_code(symbol)
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=200)).strftime('%Y-%m-%d')
        
        rs = bs.query_history_k_data_plus(
            code, "date,open,high,low,close,volume,amount",
            start_date=start_date, end_date=end_date,
            frequency="d", adjustflag="2"
        )
        df_raw = rs.get_data()
        bs.logout()
        
        if df_raw.empty:
            raise ValueError("Baostock 返回空数据")
        
        df = pd.DataFrame()
        df['日期'] = df_raw['date']
        df['收盘'] = df_raw['close'].astype(float)
        df['成交量'] = df_raw['volume'].astype(float)
        df['涨跌幅'] = df['收盘'].pct_change() * 100

        # 以下指标计算保持原代码完全不变
        df['MA20'] = df['收盘'].rolling(20).mean()
        df['MA20_Bias'] = (df['收盘'] - df['MA20']) / df['MA20']
        df['Vol_5d'] = df['涨跌幅'].rolling(5).std()
        
        ema12 = df['收盘'].ewm(span=12, adjust=False).mean()
        ema26 = df['收盘'].ewm(span=26, adjust=False).mean()
        df['MACD'] = ema12 - ema26
        
        delta = df['收盘'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(com=14-1, min_periods=14).mean()
        avg_loss = loss.ewm(com=14-1, min_periods=14).mean()
        rs_val = avg_gain / avg_loss
        df['RSI_14'] = 100 - (100 / (1 + rs_val))
        
        df['Volume_MA5'] = df['成交量'].rolling(5).mean()
        df['Volume_Ratio'] = df['成交量'] / df['Volume_MA5']
        
        latest = df.dropna().iloc[-1]
        result = {
            "date": str(latest['日期']),
            "close": float(latest['收盘']),
            "pct_change": float(latest['涨跌幅']),
            "ma20_bias": float(latest['MA20_Bias']),
            "volatility": float(latest['Vol_5d']),
            "macd": float(latest['MACD']),
            "rsi_14": float(latest['RSI_14']),
            "volume_ratio": float(latest['Volume_Ratio'])
        }
        self._set_cache(cache_key, result)
        return result
    except Exception as e:
        print(f"获取行情失败: {e}")
        try: bs.logout()
        except: pass
        return None
```

#### 2.4: 新增 fetch_kline_range()

前端 ECharts 画图需要的 OHLCV 数组：

```python
def fetch_kline_range(self, symbol: str, days: int = 60) -> list:
    cache_key = f"kline_{symbol}_{days}"
    if cached := self._get_cache(cache_key): return cached
    
    try:
        bs.login()
        code = self._to_baostock_code(symbol)
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days + 30)).strftime('%Y-%m-%d')
        
        rs = bs.query_history_k_data_plus(
            code, "date,open,high,low,close,volume",
            start_date=start_date, end_date=end_date,
            frequency="d", adjustflag="2"
        )
        df_raw = rs.get_data()
        bs.logout()
        
        if df_raw.empty:
            return []
        
        kline = []
        for _, row in df_raw.tail(days).iterrows():
            kline.append({
                "date": row['date'],
                "open": float(row['open']),
                "high": float(row['high']),
                "low": float(row['low']),
                "close": float(row['close']),
                "volume": float(row['volume'])
            })
        self._set_cache(cache_key, kline)
        return kline
    except Exception as e:
        print(f"获取K线数据失败: {e}")
        try: bs.logout()
        except: pass
        return []
```

#### 2.5: 修改 compile_and_predict() 返回值

将 `return report` (字符串) 改为 `return dict`，包含完整数据：

函数签名不变 `compile_and_predict(self, symbol: str) -> dict`。

关键变化：
- 内部调用 `self.fetch_kline_range(symbol, days=60)` 获取 K 线数据
- System prompt 去掉 QQ 相关指令
- 返回完整 dict: symbol, name, industry, business, quote, kline_data, macro_news, stock_news, retail_sentiment, report
- 异常时返回 `{"error": "错误信息"}`

---

### Task 3: FastAPI 后端

**文件:** `web/app.py`

```python
import sys
import os
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
        raise HTTPException(status_code=503, detail="引擎未初始化")
    symbol = req.symbol.strip()
    if not symbol.isdigit() or len(symbol) != 6:
        raise HTTPException(status_code=400, detail="请输入6位数字A股代码")
    result = quant_engine.compile_and_predict(symbol)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@app.get("/api/kline/{code}")
async def get_kline(code: str, period: str = "3m"):
    if not quant_engine:
        raise HTTPException(status_code=503, detail="引擎未初始化")
    days_map = {"1m": 22, "3m": 60, "6m": 120, "1y": 250}
    days = days_map.get(period, 60)
    kline = quant_engine.fetch_kline_range(code, days=days)
    return {"symbol": code, "kline_data": kline, "count": len(kline)}


@app.get("/")
async def index():
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    return FileResponse(os.path.join(static_dir, "index.html"))


static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")
```

---

### Task 4: 前端页面

#### 4.1 `web/static/index.html`

标准 HTML5 页面结构：header (标题+主题按钮) → 搜索栏 (输入框+分析按钮+时间段切换) → 股票信息条 → 量价指标卡片 → K线主图(450px) → 副图区域(成交量/MACD/RSI, 250px each) → 加载动画 → AI报告区 → 错误提示区 → footer。

引入 ECharts CDN (`echarts@5.5.0`)，引入 `/static/style.css` 和 `/static/app.js`。

#### 4.2 `web/static/style.css`

CSS 变量双主题系统：`:root, [data-theme="light"]` 和 `[data-theme="dark"]` 各定义一套色板。包括背景色、卡片色、文字色、边框色、accent 色、涨跌红绿色。

响应式布局：桌面端三列副图，移动端(<768px) 单列堆叠。圆角卡片风，过渡动画 0.3s。

#### 4.3 `web/static/app.js`

核心函数：
- `toggleTheme()` — 切换 data-theme 属性并持久化到 localStorage
- `initTheme()` — 页面加载时检测系统偏好 / localStorage
- `doAnalyze()` — POST /api/analyze，渲染所有结果
- `fetchKlineOnly(symbol, period)` — GET /api/kline/{code}?period=，只刷新 K 线图
- `renderResult(data)` — 渲染股票信息、指标卡片、K线图、AI报告
- `renderKlineChart(data)` — ECharts candlestick K线图 + MA 均线
- `renderSubCharts(data, dates)` — 成交量(红绿柱)、MACD(DIF/DEA/柱)、RSI(14)(+70/30 参考线)
- `calcMACD(closes)` / `calcRSI(closes, period)` — 前端 JS 指标计算

---

### Task 5: systemd 和启动脚本

#### 5.1 `web/quant.service`

```ini
[Unit]
Description=Agentic Quant Web Dashboard
After=network.target

[Service]
Type=simple
User=admin
WorkingDirectory=/home/admin/Agentic-Quant
ExecStart=/home/admin/Agentic-Quant/.venv/bin/uvicorn web.app:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

#### 5.2 `start_web.sh`

```bash
#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
uvicorn web.app:app --host 0.0.0.0 --port 8000 --workers 1
```

---

### Task 6: 更新 requirements.txt

去掉: `nonebot2`, `nonebot-adapter-onebot`

加上: `fastapi`, `uvicorn`, `baostock`

---

### Task 7: 撰写 DEPLOYMENT.md

内容包括：
1. 环境要求 (Python 3.10+, Ubuntu 20.04+)
2. 初始化: git clone → python -m venv → pip install → 配置 .env
3. 阿里云安全组放行 8000 端口
4. systemd 安装: sudo cp web/quant.service /etc/systemd/system/ → sudo systemctl enable/start quant
5. Quartz 博客导航栏加外链指向 `http://<服务器公网IP>:8000`
6. 常用维护命令 (查看日志、重启、更新代码)
