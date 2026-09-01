"""quant: 自研 A 股量化回测核心包。

模块地图（建议按这个顺序读代码）：
    datasource   数据从哪来（akshare 封装 + 本地缓存）
    preprocess   数据清洗（复权检查、对齐、缓存成 parquet）
    indicators   技术指标（MA/RSI/动量/波动率/BOLL，全是 pandas 向量化）
    engine       单标的回测引擎（精确到股：T+1/涨跌停/手续费）
    portfolio    多标的组合引擎（目标权重调仓，轮动类策略用）
    metrics      绩效指标（年化/回撤/夏普/胜率/换手）
    plotting     画图（净值曲线、回撤、参数热图、散点）
    scan         参数扫描与样本外验证（过拟合实验）
"""

__version__ = "0.1.0"
