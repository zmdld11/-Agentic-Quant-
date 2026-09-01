"""命令行入口。

用法（在项目根目录，用 .venv 的 python）：
    python main.py data                # 下载/更新全部标的的日线数据
    python main.py data --refresh      # 强制重新下载（接口修复/数据更新后）
    python main.py s1                  # 跑双均线策略：510300 ETF + 600519 对比
    python main.py s1 --short 10 --long 60          # 换均线参数
    python main.py s1 --symbols 300750              # 换标的（创业板 20% 涨跌停）
"""

from __future__ import annotations

import argparse

from quant.datasource import download_universe
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
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
