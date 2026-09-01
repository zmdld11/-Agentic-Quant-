# 外部调研：论文 / 开源项目 / 模型全景（找非常规的）

- 日期：2026-09-01
- 方法：web 扫掠 LLM-Agent / 因子挖掘 / TSFM / A股生态 四条线，按
  「非常规程度 × 可行性 × 复用本项目设施」筛选，全部给出落地映射

## A. 多智能体 LLM 交易（最不常规、当前最热）

| 项目 | 是什么 | 对我们的用处 |
|---|---|---|
| [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund)（~49.6k★） | 14 个"传奇投资人"Agent（巴菲特/格雷厄姆/索罗斯风格）组成基金投票 | 抄思想：给 S4 月度决策加一个"AI 投资委员会"辩论记录（多观点+ dissent） |
| [TradingAgents](https://github.com/tauricresearch/tradingagents)（Tauric Research） | 模拟交易公司组织架构：分析师/研究员/交易员/风控/基金经理分层协作 | 抄角色分工：研究(出信号)与风控(管仓位)分离——我们的 S2/S4 拆分天然对应 |
| [FinMem](https://github.com/pipiku915/finmem-llm-stocktrading)（ICLR'24, [arXiv:2311.13743](https://arxiv.org/abs/2311.13743)） | 分层记忆+性格设定的单体 LLM 交易 Agent | 抄记忆分层：短期行情/中期持仓史/长期性格(风险偏好)三档上下文 |
| [RD-Agent(Q)](https://github.com/microsoft/RD-Agent)（微软, [arXiv:2505.15155](https://arxiv.org/html/2505.15155v2)） | **LLM 多智能体自动挖因子+调模型的闭环**，宣称 IC 超人类研究员且成本大降 | 最前沿。可玩"人肉简化版"：LLM 当因子研究员产公式 → 我们 factors.py 跑 IC → 结果喂回去迭代 |

批判性参考：TradeTrap 等论文开始研究 LLM 交易 Agent 的可靠性问题——
任何 LLM 产出都要过我们已有的三道闸门（IC → 分割 → walk-forward）。

## B. LLM 情绪因子（论文级非常规，且 A 股数据可得）

- **[Lopez-Lira & Tang, "Can ChatGPT Forecast Stock Price Movements?"](https://arxiv.org/pdf/2304.07619)**（JFE 正式发表，8500+ 引用）：
  ChatGPT 给新闻标题打 good/bad 分，对次日收益方向的预测显著优于随机，
  多空组合收益可观。这是"LLM 当因子"的开山验证。
- **A 股落地可行性（关键确认）**：akshare 有 `stock_news_em`（东财个股新闻，免费）。
  路线：拉成分股新闻 → LLM 逐条打分 → 情绪因子 → 直接塞进现成的
  factors.py IC 框架检验。前置条件：一个 LLM API key（GLM/OpenAI 均可）。
- 中文先例：[股吧+BERT 情绪预测深证成指 (arXiv:2205.06675)](https://arxiv.org/pdf/2205.06675)、
  SnowNLP 股评分析等——说明中文金融情绪信号真实存在。
- **硬约束**：`stock_news_em` 只有近期滚动新闻、无历史存档——历史回测做不了，
  只能"前瞻采集"（现在开始攒面板）+ 即时情绪榜。

## C. 因子挖掘硬核流派

- **[WorldQuant 101 Formulaic Alphas](https://arxiv.org/pdf/1601.00991)**（2015）+
  [Python 实现](https://github.com/yli188/WorldQuant_alpha101_code)：101 个显式公式因子，
  由 rank/correlation/ts 算子组合而成。我们的 factors.py + 300 只成分股面板 +
  IC 闸门已经万事俱备，挑可用日线计算的公式搬家即可开跑。
- [HN 上的著名质疑](https://news.ycombinator.com/item?id=23023255)：101 因子疑似
  "随机生成+样本内幸存"——正好用我们的训练/测试分割验尸，本身就是好实验。
- [qlib](https://github.com/microsoft/qlib)（17.5k★）：Alpha158/360 特征集与 ML 基准。
  **抄特征定义，不搬框架**（自研栈已覆盖其核心研究功能）。
- gplearn 遗传规划挖因子：让公式自己进化，配样本外闸门防"进化出垃圾"。

## D. 时间序列基础模型（TSFM）

- [Chronos](https://github.com/amazon-science/chronos-forecasting)（Amazon）/
  [TimesFM](https://github.com/google-research/timesfm)（Google）：零样本时序预测，pip 即装、CPU 可跑。
- 实证结论（重要）：TSFM 对**股票收益**预测普遍平庸
  （[Re(Visiting) TSFM in Finance](https://www.alphaxiv.org/abs/2511.18578)），
  但对**波动率预测有正结果**（[Goel et al. 2025, TimesFM for realized vol](https://ideas.repec.org/p/arx/papers/2505.11163.html)）。
- **务实落点（备选）**：用 Chronos 预测下月波动率，替换 S4 的 60 日已实现波动率，
  A/B 对比回撤与卡玛。"基础模型×仓位管理"的少见组合。

## E. 基础设施参考（常规，备查）

- [AKQuant](https://github.com/akfamily/akquant)（akshare 作者新作：Rust 核心+Python）——
  未来若需更高性能引擎可评估。
- [vnpy](https://github.com/vnpy/vnpy)：A 股实盘事实标准，真到对接模拟盘/实盘再看。
- [FinRL](https://github.com/AI4Finance-Foundation/FinRL)：DRL 交易生态（DRL 在交易上
  出了名的不稳，当玩具/对照，不当主力）。
- [FinGPT](https://github.com/AI4Finance-Foundation/FinGPT)：开源金融 LLM，
  [HuggingFace](https://huggingface.co/FinGPT) 有现成情绪分类模型可白嫖，
  是"自建 LLM 情绪打分器"的备选（免 API 费用但吃本地算力）。

## 落地优先级（非常规 × 可行 × 复用现有设施）—— 已选定前两项

1. **WQ101 因子搬家**（纯本地、零新依赖、factors.py 直接吃；附带"过拟合验尸"教学点）✅ 已选
2. **A 股版 Lopez-Lira 情绪因子**（需要 LLM API key；stock_news_em → 打分 → IC 检验）✅ 已选
3. Chronos 波动率预测接入 S4（pip 一个包；A/B 对比现成回测框架）
4. 人肉版 RD-Agent(Q)：LLM 研究员迭代产因子公式，闸门把关
