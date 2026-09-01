# 实验：A 股版 Lopez-Lira 情绪管线（首日开档）

- 日期：2026-09-01
- 命令：`python main.py news --collect`（每日）/ `--digest`（看温度计）/ `--selftest`
- 方法论：Lopez-Lira & Tang (JFE, 8500+引用)——LLM 给新闻打 [-1,1] 分，
  分数对股价方向有预测力。我们把它搬到 A 股：财联社电报 → GLM 打分 → 市场情绪温度计

## 数据源的血泪史（都进了 README 踩坑记录）

1. 东财个股新闻（akshare stock_news_em）：双重死因——(a) 其内部清洗正则含
   `\u3000`，pandas3+pyarrow 的 RE2 引擎直接崩溃；(b) 绕过清洗直接复刻其端点后，
   发现服务端已改版：任何关键词只返回用户区（passportWeb），新闻区彻底缺失。
   cookie/referer/searchScope/sort 各种变体都试过，判定为服务端变更，弃用。
2. akshare 的 `stock_news_main_cx` / `index_news_sentiment_scope` 都是无参快照
   （名字像个股/历史，实际不是），不可用。
3. **财联社电报（stock_info_global_cls）验证可用**：全市场级滚动快讯，每轮约 20 条。
   → 研究问题从"个股新闻→个股收益"调整为"市场电报→沪深300方向"。

## 管线设计（quant/news.py）

```
财联社电报(~20条/轮) → 增量缓存(去重) → NewsScorer 批量打分(20条/次LLM调用)
    → 情绪面板 data/processed/sentiment_panel.parquet（每日一行：温度计）
    → digest: 最看多/最看空快讯 + 近10日温度计走势
```

- LLM 接口：OpenAI 兼容协议，环境变量 `LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`
  （默认智谱 glm-4-flash 端点），换任何兼容服务商零改动
- 成本护栏：每轮 LLM 调用上限（默认 5 次 ≈ 100 条快讯 ≈ 几分钱）
- 降级路径：无 key 时采集照常、打分跳过；解析器自测 4/4 通过；
  mock 服务端端到端测试通过（打分入库→面板写入→温度计渲染）
- 打分 prompt 是 Lopez-Lira 式"相关性加权情绪"（无关新闻→0，实质利好/利空→±0.3~1）

## 诚实约束（重申）

电报无历史存档，**今天无法回测情绪因子**——管线价值在"从今天开始攒"：
每天跑一次 `news --collect`（有 key 后自动打分），面板积累 1-2 个月后可以做：
- 温度计 vs 沪深300 次日/5日收益的 IC 检验（用现成 factors.ics_from_frames 框架）
- 情绪极值（>0.5 / <-0.5）作为 S4 轮动的叠加过滤条件

## 首日状态

- 电报缓存 20 条（2026-09-01），面板开档第 1 天
- 等待用户提供 LLM_API_KEY 后，第一条真实温度计即可产出

## 启用方法（给未来自己的备忘）

```bash
export LLM_API_KEY="你的key"          # 智谱开放平台或任意 OpenAI 兼容端点
export LLM_BASE_URL="https://open.bigmodel.cn/api/paas/v4"  # 默认值
export LLM_MODEL="glm-4-flash"        # 默认值
.venv/Scripts/python.exe main.py news --collect --digest
```
