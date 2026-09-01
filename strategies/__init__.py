"""策略包：每个策略一个文件，文件名 = 策略名。

约定：每个策略模块提供
    generate_target(bars, **params) -> pd.Series   # 纯函数：行情 → 目标仓位
    run(symbol=..., **params) -> dict              # 完整跑一次回测并存结果
这样回测引擎不依赖任何具体策略，策略也不依赖引擎内部实现。
"""
