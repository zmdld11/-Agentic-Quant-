<div align="center">
  <h1>🚀 Agentic Quant · 量化研究与投研看板</h1>
  <p><b>回测引擎 + 策略库 + 模拟盘 + LLM 研报 + Web 驾驶舱，一体化</b></p>
  <p>
    <img src="https://img.shields.io/badge/Python-3.11+-blue.svg" alt="Python">
    <img src="https://img.shields.io/badge/LLM-DeepSeek-blue.svg" alt="DeepSeek">
    <img src="https://img.shields.io/badge/Data-Baostock·akshare-green.svg" alt="Data">
    <img src="https://img.shields.io/badge/Frontend-ECharts-red.svg" alt="ECharts">
    <img src="https://img.shields.io/badge/Backtest-自研引擎-orange.svg" alt="Backtest">
    <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
  </p>
</div>

两大板块（2026-09 合并，量化管线 6 次提交经 git subtree 并入，`git log` 可溯全史）：

1. **量化研究管线**：A 股数据管道 + 自研回测引擎（T+1/涨跌停/佣金成本/防前视偏差）+
   6 个策略 + 三道验证闸门（参数扫描/过拟合/walk-forward）+ WQ101 因子研究 +
   LLM 情绪温度计 + **模拟盘账户**（S4 波动率目标轮动的长期真实跟踪）
2. **Agentic Quant 看板**：FastAPI + ECharts——单股 AI 深度推演（DeepSeek）、
   双股同步率、官媒报道，以及新增的 **🚀 驾驶舱**（模拟盘净值曲线 + 情绪温度计一屏尽览）

> 定位：研究与模拟，不接实盘。

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # 填入 DeepSeek key（LLM_API_KEY 或 DEEPSEEK_API_KEY）

# CLI —— 量化管线
python main.py data                # 下载标的池日线（免费）
python main.py paper --refresh     # 模拟盘：补账+结算+对账单（日常主命令）
python main.py news --collect --digest  # 情绪温度计
python main.py agent               # 交互式单股 AI 推演
python main.py signal --refresh    # 每月底看下月持仓建议
python main.py summary             # 全策略同窗总览
# 策略: s1/s2/s3/s4/s6/factors/wq101  验证实验: scan/overfit/showcase/wf

# Web 看板
bash start_web.sh                  # uvicorn web.app:app --port 8000
```

## 密钥配置（不进 git）

`.env`（根目录，已 gitignore）：

```
LLM_API_KEY=sk-xxx                 # 或写 DEEPSEEK_API_KEY（自动兼容映射）
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

情绪管线与 `agent` 推演共用这把 key；看板引擎默认 `deepseek-v4-flash`（可用
`AGENTIC_MODEL` 环境变量覆盖）。换任何 OpenAI 兼容服务商零改动。

## 日常使用手册

| 频率 | 命令/动作 | 做什么 |
|---|---|---|
| 每交易日收盘后 | `main.py news --collect --digest` | 电报→DeepSeek打分→市场情绪温度计 |
| 每天/随时 | `main.py paper --refresh` | 模拟盘补账+结算（幂等，忘跑自动追账） |
| 每月底收盘后 | `main.py signal --refresh` | 预览下月 S4 持仓建议 |
| 随时 | 看板 🚀驾驶舱 | 净值/超额/持仓/温度计 |

**长线模拟原理**：`paper` 维护虚拟账户（100 万起步），月末信号→次月首日开盘自动
调仓。账本已补齐 2016 年以来 120 次调仓（**+174.9% vs 沪深300 +56.5%**，与回测
+134.7% 的差 ≈ 交易成本 4%/年，口径自洽）；从现在起每日结算即纯前瞻记录——
回测结论由真实行情逐一兑现或证伪。

## 目录结构

```
quant/          量化核心包：datasource(数据,hfq复权)/preprocess/indicators/
                engine(单标的引擎)/portfolio(组合引擎)/metrics/plotting/
                scan·walkforward(验证闸门)/factors·alphas(因子研究)/
                news(情绪管线)/live·paper(信号器+模拟盘)/config(.env加载)
strategies/     s1双均线(证伪留档)/s2轮动/s3均值回归/s4波动率目标(冠军)/s5因子/s6网格
research/       15 份实验记录——项目的"做题笔记"，方法论全在这里
web/            FastAPI + ECharts 看板（单股推演/双股同步/官媒/🚀驾驶舱）
src/models/     AgenticQuant 引擎（数据抓取+指标+LLM研报生成）
quant-pipeline/ subtree 并入的历史参考（原管线 README/文档存档）
data/ results/  本地数据与回测产物（gitignored）
markdown/ docs/ 原看板项目的部署与开发文档（未跟踪）
```

## 量化管线成果速览（详见 research/）

- **策略排行**（2017-08 起同窗）：S4 波动率目标轮动 年化 9.8%/夏普 0.63/回撤 -24.9% 夺冠；
  S2 轮动 9.6%；S6 网格(中证500) 8.1%；沪深300 持有 2.5%；S1 双均线 0.3%（被证伪弃用）
- **反直觉实证清单**：训练集选参≈抛硬币（秩相关0.06）；A股月频动量反向；高胜率≠赚钱
  （S3 胜率70%收益平庸）；top2 分散变差；WQ101 公开因子衰减（4过线→0存活）；
  波动率目标是唯一接近免费午餐的改进
- **方法论**：IC 门槛 → 训练/测试分割 → walk-forward 三道闸门，过不了就弃

## 架构（看板）

```
浏览器 ──▶ FastAPI (同一进程 serve 前端 + API)
              ├─ /              → HTML 看板
              ├─ POST /api/analyze · /api/report → AI 推演
              ├─ GET /api/kline /api/sync /api/news
              ├─ GET /api/paper /api/sentiment   → 🚀驾驶舱数据
              └─ GET /api/health
                      │
        AgenticQuant Engine (src/models/)        quant/ 数据产物
        ├─ Baostock → K线                        ├─ paper_account.json
        ├─ akshare  → 新闻/股吧情绪               └─ sentiment_panel.parquet
        └─ DeepSeek → LLM 推理
```

## 服务器部署（阿里云 2C2G）

**Web 看板**：systemd 服务沿用（`web/quant.service`，`uvicorn web.app:app --port 8000`）。
升级：`git pull && pip install -r requirements.txt && sudo systemctl restart quant`
（新增 matplotlib/pyarrow 约 200MB 磁盘，内存影响极小）。

**每日自动任务（已内置，无需配置）**：主进程启动时自动开启定时器——
周一至五 18:10 采集电报+情绪打分、18:30 模拟盘补账结算（Asia/Shanghai），
每次任务以独立子进程执行，日志在 `logs/scheduler.log`，驾驶舱页面可看运行状态。
**服务器 git pull 后下一次任务自动用新代码（子进程设计，Web 无需重启）**。

可用 `.env` 覆盖计划/开关：`NEWS_TIME=18:10`、`PAPER_TIME=18:30`、`DISABLE_SCHEDULER=1`。

crontab 方式（备选，适合不想常驻 Web 服务的场景）：

```cron
30 17 * * 1-5  cd /path/to/repo && .venv/bin/python main.py news --collect >> logs/news.log 2>&1
45 17 * * 1-5  cd /path/to/repo && .venv/bin/python main.py paper --refresh >> logs/paper.log 2>&1
```

注意：`apt install fonts-noto-cjk`（图表中文）；`.env` 手动拷贝；首次先跑 `main.py data`
建数据缓存（或从本地 rsync `data/`）。

## 数据源

| 数据类型 | 来源 | 说明 |
|---------|------|------|
| K线/成分股 | Baostock | 免费免注册，后复权(hfq) |
| ETF/指数行情 | akshare(东财/新浪) | 指数走新浪源（东财限流） |
| 财联社电报 | akshare | LLM 情绪打分的语料 |
| 公司档案/股吧情绪 | akshare/东财 | 看板单股推演用 |
| LLM | DeepSeek | 研报生成 + 情绪打分 |

## 踩坑记录（持续追加，全量见 research/）

- **akshare 请求层无 timeout**（2026-09-07 实锤）：财联社接口异常时裸连接挂死 +
  指数退避重试10次 ≈ 17 分钟"假死"。已在 datasource 给全进程 requests.get 补默认
  30s 超时 + news 拉取加 90s 线程看门狗
- **baostock 的 ETF 只有 2026 年以后的数据**（股票却是全历史）→ ETF 兜底必须
  "合并缓存补尾部"而非替换，否则会把回测长历史冲掉（实测踩过又恢复）
- 东财 ETF 接口限流时自动切 baostock 兜底（锚点对齐防价格台阶）——无人值守的关键
- 东财个股新闻接口服务端变更（2026-09 只返回用户区）→ 情绪管线走财联社电报
- akshare 老正则 × pandas3/pyarrow 崩溃（`\u3000` RE2 不识别）；argparse help 里 `%` 写 `%%`
- 批量 300 只成分股：东财限流 → baostock 三进程并行（~1.2s/只）
- Windows 注册表代理未运行 → 代码层 NO_PROXY=*
- 回测必须后复权：东财 qfq 长历史高分红个股产生负价（茅台 2015=-117 元）
- akshare 版本要对齐 ≥1.18.81（1.18.48 的财联社实现裸请求无签名，必挂）

## 免责声明

本项目仅供学术研究与量化技术探讨。AI 推演与策略输出**不构成任何投资建议**。
股市有风险，投资需谨慎。

## 协议

[MIT License](LICENSE)
