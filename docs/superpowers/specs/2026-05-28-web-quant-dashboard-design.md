# Web 量化投研看板 架构设计

日期: 2026-05-28

## 目标

将基于 QQ (Napcat/NoneBot2) 的股票量化系统改为 Web 端，跑在阿里云 2C2G 服务器上。博客（Quartz 4）仍挂在 GitHub Pages，导航栏加外链跳转到看板。

## 架构

```
GitHub Pages (yourblog.github.io)          Aliyun ECS (2C2G Ubuntu)
    博客不动，导航栏加外链                         │
    [文章] [标签] [📊量化] [关于]                  ▼
                        │               FastAPI (uvicorn :8000)
                        │               ├─ GET  /          → 前端HTML页面
                        └──跳转──────────▶├─ POST /api/analyze → AI分析
                                         ├─ GET  /api/kline/{code} → K线数据
                                         └─ GET  /api/health     → 健康检查
                                                  │
                                         AgenticQuant Engine
                                         ├─ Baostock → K线/基本面 (主力)
                                         ├─ akshare  → 新闻/情绪 (保留)
                                         └─ DeepSeek API → LLM 推理
```

**关键：** 前端和 API 同源（同一个 FastAPI 进程），无跨域、无 SSL、无域名需求。

## 技术栈

| 层 | 技术 | 原因 |
|---|---|---|
| 前端 | HTML + ECharts + 原生 JS/CSS | 零依赖，ECharts 有专业 K 线支持 |
| 后端 | FastAPI + uvicorn | 轻量异步，替换 NoneBot2 |
| 数据 | Baostock (K线) + akshare (新闻/情绪) | 免费免注册，API 不爬网页 |
| LLM | DeepSeek API (OpenAI SDK) | 不变 |
| 守护 | systemd | 开机自启，崩溃重启，比 screen 稳定 |

## 前端页面布局

```
┌──────────────────────────────────────────┐
│  📊 Agentic Quant  量化投研看板      [🌙/☀]│
├──────────────────────────────────────────┤
│  [输入股票代码...] [🔍 分析]    [1月][3月][6月][1年] │
├──────────────────────────────────────────┤
│  📈 K线主图                                │
│  (ECharts Candlestick + MA5/MA10/MA20)    │
├──────────────┬──────────────┬────────────┤
│  成交量副图    │  MACD 副图    │  RSI 副图   │
├──────────────┴──────────────┴────────────┤
│  🤖 AI 投研推演报告                        │
│  1. 宏观政策映射                           │
│  2. 多维共振与资金情绪                      │
│  3. 散户心理与暗线                         │
│  4. 明日博弈预判                           │
│  ⚠️ 仅供参考，不构成投资建议                │
└──────────────────────────────────────────┘
```

- 白/暗双模式，默认跟随系统，顶部切换按钮
- 响应式布局，移动端适配
- 分析中显示加载动画，报告区流式渐入

## API 设计

### POST /api/analyze
请求: `{"symbol": "600519"}`
响应: symbol, name, industry, business, quote(量价指标), kline_data(OHLCV 60天数组), macro_news[], stock_news[], retail_sentiment[], report(AI报告文本)
一次返回所有数据，前端一次拿到。

### GET /api/kline/{code}?period=3m|6m|1y
只返回 kline_data 数组，切换时间范围时刷图用，不调 LLM。

### GET /api/health
返回 `{"status": "ok", "cache_size": N}`

## 数据源

- **Baostock**: K 线 OHLCV（1990-至今全 A 股）、公司基本信息、行业分类。免费免注册无限量。
- **AKShare**: 保留用于新闻（stock_news_em）和全球宏观（stock_info_global_sina），频率低不会被封。
- **股吧爬虫**: 保留，requests 直爬 HTML，同上低频。

MACD/RSI/MA20/量比等指标沿用现有 pandas 计算代码。

## 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | `web/app.py` | FastAPI 主应用 |
| 新增 | `web/static/index.html` | 前端页面 |
| 新增 | `web/static/style.css` | 样式（含暗黑模式） |
| 新增 | `web/static/app.js` | 前端逻辑 + ECharts |
| 修改 | `src/models/agentic_quant.py` | akshare K线 → Baostock, print → return dict |
| 新增 | `web/quant.service` | systemd 配置文件 |
| 新增 | `start_web.sh` | 启动脚本 |
| 删除 | `bot.py` | QQ 机器人入口 (NoneBot2) |
| 删除 | `启动机器人.bat` | Windows 启动脚本 |
| 删除 | `start_bot.sh` | 旧 linux 启动脚本 |
| 删除 | `QQ_BOT_README.md` | QQ 机器人文档 |
| 删除 | `markdown/Napcat指令.md` | Napcat 说明 |
| 新增 | `DEPLOYMENT.md` | 系统部署与使用指南 |
