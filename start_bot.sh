#!/bin/bash
# 启动机器人 - Linux 版

# 检查当前目录下是否有虚拟环境，没有则提醒
if [ ! -d ".venv" ]; then
    echo "未检测到 .venv 虚拟环境，请先执行: python3 -m venv .venv"
    echo "然后执行: source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

echo "正在启动 Agentic Quant 机器人..."
# 使用后台运行机制或前台运行（推荐结合 screen / tmux / systemd 使用后台）
./.venv/bin/python3 bot.py
