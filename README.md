<div align="center">
  <h1>📊 Agentic Quant</h1>
  <p><b>基于大语言模型与政治经济学的 A 股量化投研看板</b></p>
  <p>
    <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python">
    <img src="https://img.shields.io/badge/LLM-DeepSeek-blue.svg" alt="DeepSeek">
    <img src="https://img.shields.io/badge/Data-Baostock-green.svg" alt="Baostock">
    <img src="https://img.shields.io/badge/Frontend-ECharts-red.svg" alt="ECharts">
    <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
  </p>
</div>

## 项目简介

打通 **"个股基本面 + K线量价 + 宏观/个股新闻 + 散户情绪 + LLM 深度推演"** 的全链路量化投研系统。让 AI 像研究员一样，帮你做 A 股单日盯盘与推演报告。

**Web 看板**：输入 6 位 A 股代码，自动抓取数据、计算技术指标、调用 DeepSeek 生成次日走势研判。支持 K 线图、MACD/RSI/成交量副图、白/暗双主题。

## 架构

```
浏览器 ──▶ FastAPI (同一进程 serve 前端 + API)
              ├─ /              → HTML 看板页面
              ├─ POST /api/analyze  → AI 量化分析
              ├─ GET  /api/kline    → K线数据
              └─ GET  /api/health   → 健康检查
                      │
              AgenticQuant Engine
              ├─ Baostock → K线/基本面
              ├─ akshare  → 新闻/散户情绪
              └─ DeepSeek → LLM 推理
```

## 快速开始

### 1. 环境要求

- Python 3.10+
- Linux / macOS / Windows

### 2. 安装

```bash
git clone https://github.com/zmdld11/-Agentic-Quant-.git
cd ./-Agentic-Quant-
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入你的 DeepSeek API Key
```

### 4. 启动

```bash
bash start_web.sh
# Windows: .venv\Scripts\python -m uvicorn web.app:app --host 0.0.0.0 --port 8000
```

浏览器打开 `http://127.0.0.1:8000`，输入 A 股代码即可分析。

## 数据源

| 数据类型 | 来源 | 说明 |
|---------|------|------|
| K线 (OHLCV) | Baostock | 免费免注册，全A股1990至今 |
| 公司档案 | akshare | 巨潮资讯 |
| 宏观新闻 | akshare | 新浪全球快讯 |
| 个股新闻 | akshare | 东方财富 |
| 散户情绪 | 东方财富股吧 | 近7天热帖 |

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | FastAPI + uvicorn |
| 数据 | Baostock + akshare + pandas |
| AI | DeepSeek (OpenAI SDK) |
| 前端 | ECharts K线图 + 原生 JS/CSS |
| 部署 | systemd + Nginx（可选） |

## 扩展

- **换大模型**：修改 `AgenticQuant` 初始化参数 `base_url`，兼容所有 OpenAI 格式接口
- **加新因子**：在 `fetch_quant_status()` 中补充北向资金、龙虎榜等指标
- **后台监控**：后续可在 FastAPI 上加 APScheduler 实现自选股定时预警

## 免责声明

本项目仅供学术研究与量化技术探讨。AI 推演结果**不构成任何投资建议**。股市有风险，投资需谨慎。

## 协议

[MIT License](LICENSE)
