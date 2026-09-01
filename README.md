# Market Quantification · A股量化学习项目

个人量化学习项目：用真实 A 股数据 + 自研回测引擎，从零搞懂量化交易的完整流程。
**定位是研究学习，不接实盘下单。**

## 量化是什么（30 秒版）

量化交易 = 把「买什么、什么时候买卖、买卖多少」从"凭感觉"变成**明确的数学规则**，
然后用历史数据回测验证：**如果过去几年我严格按这个规则交易，会赚还是亏、最深亏多少**。

整条流水线，也就是本项目的目录结构：

```
获取数据(datasource) → 清洗(preprocess) → 算指标(indicators)
       → 产生信号(strategies) → 模拟历史交易(engine) → 打分(metrics) → 画图看证据(plotting)
```

对写过程序的人一句话：**量化 = 数据处理 + 一个严格遵守时序的模拟器 + 统计检验**。
没有难算法，难在两点：金融常识，以及不自欺（见下面"小词典"）。

## 快速开始

```bash
# 项目根目录下（Windows Git Bash），.venv 已配好
.venv/Scripts/python.exe main.py data      # 1. 下载标的池日线数据（免费，无需注册）
.venv/Scripts/python.exe main.py s1        # 2. 策略1：双均线（510300 + 茅台）
.venv/Scripts/python.exe main.py s2        # 3. 策略2：ETF动量轮动（vs 沪深300 持有）
.venv/Scripts/python.exe main.py s3        # 4. 策略3：均值回归（券商ETF + 300ETF）
.venv/Scripts/python.exe main.py s4        # 5. 策略4：轮动+波动率目标仓位（风险预算）
.venv/Scripts/python.exe main.py s6        # 6. 策略6：网格交易（震荡市收割机）
.venv/Scripts/python.exe main.py scan      # 7. 实验：参数扫描热图（看参数面形状）
.venv/Scripts/python.exe main.py overfit   # 8. 实验：训练/测试分割过拟合检验（必看）
.venv/Scripts/python.exe main.py showcase  # 9. "训练最优参数"在测试集的净值 vs 默认参数
.venv/Scripts/python.exe main.py wf        # 10. 实验：Walk-Forward 滚动样本外验证
.venv/Scripts/python.exe main.py factors --download  # 11. 策略5：横截面因子选股（首次需下载成分股数据）
.venv/Scripts/python.exe main.py signal    # 12. 模拟盘信号器：S4 当前持仓建议（收盘后加 --refresh）
.venv/Scripts/python.exe main.py summary   # 13. 全策略同窗总览（图+表）
.venv/Scripts/python.exe main.py wq101     # 14. 研究：WorldQuant 101因子 A股验尸
.venv/Scripts/python.exe main.py news --collect --digest  # 15. LLM情绪管线（需配置 LLM_API_KEY 打分）
# 结果都在 results/ 下：图 + 交易流水 + 报告；实验结论在 research/
```

## 目录结构

```
data/raw/          akshare 原始数据缓存（parquet）     data/processed/  （预留）
quant/             核心包，建议按此顺序读：
  datasource.py     数据从哪来（akshare 封装，接口坏了只修这里）
  preprocess.py     清洗：剔除停牌、算日收益率
  indicators.py     技术指标：MA/EMA/RSI/动量/波动率/BOLL
  engine.py         单标的回测引擎：T+1、涨跌停、一手100股、佣金/印花税/滑点、防前视偏差
  portfolio.py      多标的组合引擎：目标权重调仓（轮动类策略用）
  metrics.py        绩效：年化/波动/夏普/最大回撤/卡玛/回合胜率
  plotting.py       净值曲线、回撤面积、参数热图、多线对比
  scan.py           参数扫描 + 训练/测试分割过拟合实验
  walkforward.py    滚动样本外验证（walk-forward）
  factors.py        横截面因子研究：IC 检验、分组回测、TopN 组合
  live.py           模拟盘信号器：S4 规则输出当前持仓建议并记日志
  summary.py        全策略同窗总览（对比图+表）
  alphas.py         WorldQuant 101 算子库与 28 个公式因子（A股验尸研究）
  news.py           LLM 情绪管线：财联社电报 → 打分 → 市场情绪温度计
strategies/        每个策略一个文件：
  s1_ma_cross.py    双均线（趋势入门；已被 walk-forward 证伪，留作教材）
  s2_momentum.py    ETF 动量轮动（跨资产配置）
  s3_mean_revert.py 布林带均值回归（超卖反弹）
  s4_rotation_plus.py 轮动+波动率目标仓位（风险预算；全项目冠军）
  s5_factor.py      横截面多因子选股（IC/分组/TopN）
  s6_grid.py        网格交易（波动收割机，含专用模拟器）
strategies/        每个策略一个文件：s1_ma_cross（双均线）...
research/          实验记录：每个策略每次实验的结论（像做题笔记）
results/           回测输出（图/csv/报告），git 忽略
main.py            命令行入口
```

## 小词典（按重要性排序，新手最容易死在前三条）

- **前视偏差（lookahead bias）**：用了"当时不可能知道的信息"做决策。例：用收盘价算信号、
  又假设当天收盘价成交——实盘根本做不到。本引擎结构上强制"t 日收盘出信号，t+1 日开盘成交"。
- **过拟合（overfitting）**：参数调到在历史数据里完美，本质是把历史噪声当规律。
  解药：训练/测试集分割、样本外验证（阶段4实操）。回测收益好 ≠ 未来能赚。
- **最大回撤（max drawdown）**：从峰值最深跌多少。年化 20% 但中途腰斩的策略，
  大多数人根本拿不住。看回测先看回撤，再看收益。
- **夏普比率（Sharpe）**：每承受 1 份波动换来多少超额收益。<1 一般，>2 优秀（对日线策略）。
- **复权（adjusted price）**：分红送股会让价格"跳水"，复权价把历史价格折算成可比口径。
  本项目个股/ETF 用**后复权（hfq）**：它等价于"分红再投资"的真实总回报序列，
  恒为正、适合回测。（前复权 qfq 在长历史+高分红个股上会出现**负价格**，
  例如茅台 2015 年 qfq 价为 -117 元，实测踩过的坑。）
- **T+1**：A 股当天买入的股票当天不能卖。引擎已模拟。
- **涨跌停**：主板/ETF ±10%，创业板/科创板 ±20%。涨停买不进、跌停卖不出，引擎按开盘价近似判断。
- **交易成本**：佣金（万 2.5、最低 5 元）+ 卖出印花税（个股 0.05%，ETF 免）+ 滑点（0.1%）。
  高频信号会被成本吃光——跑一下 s1 就能看到。
- **年化收益率（CAGR）**：把区间收益折算成一年多少，跨周期比较才有意义。
- **样本外验证（out-of-sample）**：用训练集选参数/规则，用没参与过开发的测试集检验。
  本项目实测：双均线参数训练/测试夏普的秩相关只有 0.06 —— 训练集挑参数 ≈ 抛硬币。
- **参数平台 vs 尖峰**：参数扫描后看"参数面"形状——相邻参数都还行（平台）说明规律可能
  真实；只有个别组合突出（尖峰）大概率是拟合了噪声。见 `research/` 参数扫描实验。
- **动量效应 / 均值回归**：金融里被验证最久的两个异象——近期强者倾向继续强（动量），
  短期超卖倾向反弹（回归）。趋势策略吃前者，抄底策略吃后者，两者是镜像对手。
- **接飞刀**：均值回归策略在单边下跌里的死法——每一次"看起来够便宜"都只是半山腰。
- **IC / ICIR**：因子分与未来收益的截面秩相关（Information Coefficient）。
  因子研究的守门员：|IC|>0.03 且 ICIR>0.3 才值得做组合回测（S5 实测三因子全灭）。
- **幸存者偏差**：用"今天的指数名单"回测历史 = 拿未来的赢家炒股。本项目实测：
  当前沪深300等权组合 2019 年起 +253% vs 指数 +43%——差额全是偏差，不是 alpha。
- **波动率目标（vol targeting）**：仓位 = 目标波动 ÷ 已实现波动。利用波动率聚集
  （大波动后往往还有大波动）自动减仓，S4 实测回撤 -39.7%→-24.9%、夏普 +0.1。
- **Walk-Forward**：滚动"用过去N年选参→只交易下一年"，拼出的净值是整套流程的
  真实样本外成绩。S1 双均线实测：每年重选参数 ≈ 不选（年化 -0.6%），被证伪弃用。
- **alpha 衰减**：因子一旦公开就会被交易到消失。WQ101（2015 公开）实测：
  训练期过 IC 门槛的 4 个因子，测试期存活 0 个；但"因子间相对排序"仍有信息
  （训练/测试秩相关 0.50）——水平会死，排序半衰期更长。
- **LLM 情绪因子**：让 LLM 给新闻打分当因子（Lopez-Lira, JFE 验证有预测力）。
  本项目 A 股版管线已建好（`news` 命令），因新闻源无历史存档，采用前瞻采集模式。

## 环境变量（LLM 情绪管线）

```bash
export LLM_API_KEY="你的key"     # 启用打分必填；智谱开放平台或任意 OpenAI 兼容端点
export LLM_BASE_URL="https://open.bigmodel.cn/api/paas/v4"  # 默认智谱
export LLM_MODEL="glm-4-flash"   # 默认便宜够用的闪速版
```
无 key 时 `news --collect` 仍会采集缓存电报，只是跳过打分。

## 学习路线

| 阶段 | 内容 | 状态 |
|---|---|---|
| 0 | 环境 + 数据管道 + 文档 | ✅ |
| 1 | 下载代表性标的 + 沪深300指数（2015 至今，完整牛熊周期） | ✅ |
| 2 | 自研回测引擎 v0.1 + 双均线策略跑通 | ✅ |
| 3 | 绩效指标 + A股规则/成本，直观看到成本的影响 | ✅ |
| 4a | 参数扫描 + 训练/测试分割（过拟合实操，结论：训练集选参≈抛硬币） | ✅ |
| 4b | ETF 动量轮动（组合引擎；年化 10% vs 基准 5%） | ✅ |
| 4c | 布林带均值回归（胜率 62-70% 但收益平庸，砍回撤一半） | ✅ |
| 5a | 波动率目标仓位（S4：夏普 0.51→0.63，回撤 -39.7%→-24.9%） | ✅ |
| 5b | Walk-Forward 滚动样本外（给双均线"验尸"：择时无超额，证伪弃用） | ✅ |
| 5c | 横截面因子选股（IC 全不过门槛；A股月频动量为反向；幸存者偏差活体演示） | ✅ |
| 6a | 网格策略（中证500 年化 8.1% 碾压持有 2.8%；券商标的经历两种经典死法） | ✅ |
| 6b | S4 top1→top2 分散实验（分散无优势：池内资产高相关） | ✅ |
| 6c | 模拟盘信号器（`signal` 命令，2026-09-01 开档：黄金ETF 62%） | ✅ |
| 7a | 外部调研（LLM多智能体/因子挖掘/TSFM 全景 → research 笔记） | ✅ |
| 7b | WQ101 因子搬家+验尸（28因子全算通；训练期过线 4 个→测试期存活 0 个） | ✅ |
| 7c | LLM 情绪管线（电报→打分→温度计；无历史数据只能前瞻采集，面板已开档） | ✅ |
| 8 | 情绪面板攒够后的 IC 检验、Chronos 波动率接入 S4、模拟盘对账 | ⬜ 长期 |

## 数据来源

- **akshare**（主）：免费无 token，爬取东方财富等公开数据。日线接口：
  `stock_zh_a_hist`（个股）/ `fund_etf_hist_em`（ETF）/ `index_zh_a_hist`（指数）。
- **baostock**（备）：akshare 挂了再上，数据质量稳。
- 标的池见 `quant/datasource.py` 的 `UNIVERSE`：4 只 ETF + 茅台/宁德 + 沪深300指数。

## 踩坑记录（持续追加）

- **前复权负价格（本项目踩过的最大的坑）**：东财 qfq 数据对长历史高分红个股会算出
  负价（茅台 2015 年 -117 元），回测直接失真（回撤算出 -109%）。解法：一律用 hfq
  后复权（= 分红再投资总回报），初始资金 100 万适配其价格量级。
- **系统代理导致 ProxyError**：akshare 的数据源都是国内站，若 Windows 配了代理客户端
  而未运行，requests 读注册表代理会连不上。`datasource.py` 里已设 `NO_PROXY=*`。
- **东财接口限流**：`index_zh_a_hist` 内部要分 17 页抓代码表，连发请求易被掐断；
  指数改走新浪源单请求接口。偶发连接重置靠递增重试扛过。
- **批量下载 300 只成分股被限流**：akshare/东财逐只下载约 20 秒/只还会间歇掐连接；
  改用 **baostock**（一次登录连续查询）+ 3 进程分段并行 → ~1.2 秒/只。
  baostock 连接也可能中途失效（表现为整段快速失败），重跑该段即可（已成功的走缓存）。
- **argparse help 里的 `%` 要写成 `%%`**，否则构造 parser 直接抛 badly formed help string。
- **akshare 内部正则 × pandas3/pyarrow 崩溃**：stock_news_em 的清洗代码用
  `\u3000` 正则，pyarrow 的 RE2 引擎不认 `\u` 转义直接抛 ArrowInvalid。
  pandas 3.0 的字符串列默认走 pyarrow，遇到老库的 str.replace 正则要当心。
- **东财个股新闻搜索接口服务端变更**（2026-09）：任何关键词只返回用户区
  （passportWeb）不返回新闻区，cookie/referer/scope 各种变体均无效 → 弃用，
  情绪管线改走财联社电报（stock_info_global_cls，全市场级）。
- **akshare 接口名会骗人**：`stock_news_main_cx`、`index_news_sentiment_scope`
  名字像个股/历史数据，实际都是无参当日快照。用前先看签名。

- **Python 3.14 太新**：已实测 numpy 2.5 / pandas 3.0 / akshare 1.18 / pyarrow 25 全部可用。
  若未来新装依赖失败，备选方案：装 Python 3.12 重建 `.venv`。
- **路径含空格**：项目文件夹名带空格，个别工具（某些 shell 脚本/编译链）会出诡异问题，
  报错时优先怀疑这里。pip/python/matplotlib 实测无碍。
- **akshare 接口随上游网站改版会失效**：所有调用集中在 `quant/datasource.py`，
  报 KeyError / 空数据 → 先看是不是接口列名变了。
- **matplotlib 中文乱码**：已在 `plotting.py` 里设 Microsoft YaHei；换机器跑注意字体是否存在。
- **pandas 3.0**：与 2.x 有行为差异（Copy-on-Write 默认等），本仓库代码按 3.0 写。
