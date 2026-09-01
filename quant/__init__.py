"""quant: 自研 A 股量化回测核心包。

模块地图（建议按这个顺序读代码）：
    datasource   数据从哪来（akshare 封装 + 本地缓存）
    preprocess   数据清洗（复权检查、对齐、缓存成 parquet）
    indicators   技术指标（MA/RSI/动量/波动率/BOLL，全是 pandas 向量化）
    engine       回测引擎（核心：信号→次日成交，含 T+1/涨跌停/手续费）
    metrics      绩效指标（年化/回撤/夏普/胜率/换手）
    plotting     画图（净值曲线、回撤图、买卖点）
"""

__version__ = "0.1.0"
