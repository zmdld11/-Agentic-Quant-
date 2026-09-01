"""命令行入口。

用法（在项目根目录，用 .venv 的 python）：
    python main.py data                # 下载/更新全部标的的日线数据
    python main.py data --refresh      # 强制重新下载（接口修复/数据更新后）
    python main.py s1                  # 跑双均线策略：510300 ETF + 600519 对比
    python main.py s1 --short 10 --long 60          # 换均线参数
    python main.py s1 --symbols 300750              # 换标的（创业板 20% 涨跌停）
    python main.py scan                # 阶段4·实验1：S1 参数扫描 + 热图
    python main.py overfit             # 阶段4·实验2：训练/测试分割过拟合检验
    python main.py showcase            # 阶段4·实验2续：训练最优参数 vs 默认参数净值对比
"""

from __future__ import annotations

import argparse

from quant.datasource import download_universe
from quant import scan
from strategies import s1_ma_cross


def cmd_data(args: argparse.Namespace) -> None:
    print("下载标的池日线数据（已缓存则秒过）...")
    download_universe(refresh=args.refresh)


def cmd_s1(args: argparse.Namespace) -> None:
    for i, symbol in enumerate(args.symbols):
        if i:
            print("\n")
        s1_ma_cross.run(
            symbol, short=args.short, long=args.long,
            start=args.start, refresh=args.refresh,
        )


def cmd_scan(args: argparse.Namespace) -> None:
    scan.cmd_scan(args.symbol, args.refresh)


def cmd_overfit(args: argparse.Namespace) -> None:
    scan.cmd_overfit(args.symbol, args.refresh)


def cmd_showcase(args: argparse.Namespace) -> None:
    scan.cmd_showcase(args.symbol)


def cmd_s2(args: argparse.Namespace) -> None:
    from strategies import s2_momentum
    s2_momentum.run(lookback=args.lookback, topk=args.topk, refresh=args.refresh)


def cmd_s3(args: argparse.Namespace) -> None:
    from strategies import s3_mean_revert
    for i, symbol in enumerate(args.symbols):
        if i:
            print("\n")
        s3_mean_revert.run(symbol, n=args.n, k=args.k, refresh=args.refresh)


def cmd_s4(args: argparse.Namespace) -> None:
    from strategies import s4_rotation_plus
    s4_rotation_plus.run(lookback=args.lookback, vol_window=args.vol_window,
                         target_vol=args.vol, topk=args.topk, refresh=args.refresh)


def cmd_wf(args: argparse.Namespace) -> None:
    from quant import walkforward
    walkforward.run_walkforward(args.symbol, args.refresh)


def cmd_factors(args: argparse.Namespace) -> None:
    if args.download:
        from quant.datasource import download_stock_universe
        download_stock_universe(refresh=args.refresh)
    from strategies import s5_factor
    s5_factor.run(topn=args.topn, cost=args.cost, refresh=args.refresh)


def cmd_s6(args: argparse.Namespace) -> None:
    from strategies import s6_grid
    for i, symbol in enumerate(args.symbols):
        if i:
            print("\n")
        s6_grid.run(symbol, n_grids=args.grids, refresh=args.refresh)


def cmd_signal(args: argparse.Namespace) -> None:
    from quant.live import s4_signal
    s4_signal(refresh=args.refresh)


def cmd_summary(args: argparse.Namespace) -> None:
    from quant import summary
    summary.run()


def cmd_wq101(args: argparse.Namespace) -> None:
    from quant import alphas
    alphas.run_research(start=args.start, split=args.split)


def cmd_news(args: argparse.Namespace) -> None:
    from quant import news
    if args.selftest:
        news.self_test()
        return
    if args.collect:
        news.collect(max_llm_calls=args.max_calls)
    if args.digest:
        news.digest()
    if not args.collect and not args.digest:
        print("用法: python main.py news --collect / --digest / --selftest")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="A股量化回测 · 学习项目")
    sub = parser.add_subparsers(dest="command", required=True)

    p_data = sub.add_parser("data", help="下载/更新数据")
    p_data.add_argument("--refresh", action="store_true", help="忽略缓存强制重下")
    p_data.set_defaults(func=cmd_data)

    p_s1 = sub.add_parser("s1", help="策略1：双均线交叉")
    p_s1.add_argument("--symbols", nargs="+", default=["510300", "600519"],
                      help="标的代码，默认 510300(沪深300ETF) 600519(贵州茅台)")
    p_s1.add_argument("--short", type=int, default=5, help="短期均线天数，默认5")
    p_s1.add_argument("--long", type=int, default=60, help="长期均线天数，默认60")
    p_s1.add_argument("--start", default="2015-01-01", help="回测起点")
    p_s1.add_argument("--refresh", action="store_true", help="忽略数据缓存强制重下")
    p_s1.set_defaults(func=cmd_s1)

    p_scan = sub.add_parser("scan", help="实验：S1参数扫描（看参数面是否稳健）")
    p_scan.add_argument("--symbol", default="510300")
    p_scan.add_argument("--refresh", action="store_true")
    p_scan.set_defaults(func=cmd_scan)

    p_of = sub.add_parser("overfit", help="实验：训练/测试分割过拟合检验")
    p_of.add_argument("--symbol", default="510300")
    p_of.add_argument("--refresh", action="store_true")
    p_of.set_defaults(func=cmd_overfit)

    p_show = sub.add_parser("showcase", help="实验：训练最优参数 vs 默认参数测试集净值")
    p_show.add_argument("--symbol", default="510300")
    p_show.set_defaults(func=cmd_showcase)

    p_s2 = sub.add_parser("s2", help="策略2：ETF动量轮动（月度）")
    p_s2.add_argument("--lookback", type=int, default=21, help="动量回看交易日数，默认21")
    p_s2.add_argument("--topk", type=int, default=1, help="同时持有最强的几只，默认1")
    p_s2.add_argument("--refresh", action="store_true")
    p_s2.set_defaults(func=cmd_s2)

    p_s3 = sub.add_parser("s3", help="策略3：布林带均值回归")
    p_s3.add_argument("--symbols", nargs="+", default=["512880", "510300"],
                      help="默认 512880(证券ETF) 510300(沪深300ETF)")
    p_s3.add_argument("--n", type=int, default=20, help="均值回归窗口，默认20")
    p_s3.add_argument("--k", type=float, default=2.0, help="入场z阈值，默认2.0")
    p_s3.add_argument("--refresh", action="store_true")
    p_s3.set_defaults(func=cmd_s3)

    p_s4 = sub.add_parser("s4", help="策略4：动量轮动+波动率目标仓位")
    p_s4.add_argument("--lookback", type=int, default=21)
    p_s4.add_argument("--vol-window", type=int, default=60, help="已实现波动率窗口，默认60")
    p_s4.add_argument("--vol", type=float, default=0.15, help="目标年化波动率，默认0.15")
    p_s4.add_argument("--topk", type=int, default=1, help="同时持有最强的几只，默认1")
    p_s4.add_argument("--refresh", action="store_true")
    p_s4.set_defaults(func=cmd_s4)

    p_wf = sub.add_parser("wf", help="实验：Walk-Forward 滚动样本外验证")
    p_wf.add_argument("--symbol", default="510300")
    p_wf.add_argument("--refresh", action="store_true")
    p_wf.set_defaults(func=cmd_wf)

    p_fac = sub.add_parser("factors", help="策略5：横截面多因子选股（IC/分组/TopN组合）")
    p_fac.add_argument("--download", action="store_true", help="先批量下载成分股数据(baostock)")
    p_fac.add_argument("--topn", type=int, default=30)
    p_fac.add_argument("--cost", type=float, default=0.0015, help="单边成本，默认0.15%%")
    p_fac.add_argument("--refresh", action="store_true")
    p_fac.set_defaults(func=cmd_factors)

    p_s6 = sub.add_parser("s6", help="策略6：网格交易（波动收割机）")
    p_s6.add_argument("--symbols", nargs="+", default=["512880", "510500"],
                      help="默认 512880(证券ETF) 510500(中证500ETF)")
    p_s6.add_argument("--grids", type=int, default=20, help="格数，默认20")
    p_s6.add_argument("--refresh", action="store_true")
    p_s6.set_defaults(func=cmd_s6)

    p_sig = sub.add_parser("signal", help="模拟盘信号器：S4 当前持仓建议（收盘后 --refresh）")
    p_sig.add_argument("--refresh", action="store_true", help="先刷新ETF数据")
    p_sig.set_defaults(func=cmd_signal)

    p_sum = sub.add_parser("summary", help="全策略同窗总览（图+表）")
    p_sum.set_defaults(func=cmd_summary)

    p_wq = sub.add_parser("wq101", help="研究：WorldQuant 101因子精选 · 训练/测试IC验尸")
    p_wq.add_argument("--start", default="2019-01-01")
    p_wq.add_argument("--split", default="2023-01-01", help="训练/测试分割点")
    p_wq.set_defaults(func=cmd_wq101)

    p_news = sub.add_parser("news", help="LLM情绪管线：财联社电报→打分→市场情绪面板/温度计")
    p_news.add_argument("--collect", action="store_true", help="采集(+打分,需 LLM_API_KEY)并更新面板")
    p_news.add_argument("--digest", action="store_true", help="输出今日市场情绪温度计")
    p_news.add_argument("--max-calls", type=int, default=5, help="单轮LLM调用上限(成本护栏)")
    p_news.add_argument("--selftest", action="store_true", help="解析器自测(无需API key)")
    p_news.set_defaults(func=cmd_news)
    return parser


def main() -> None:
    from quant.config import load_env
    load_env()   # 从 .env 读取密钥等本地配置（不入库）
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
