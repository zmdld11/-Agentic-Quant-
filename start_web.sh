#!/bin/bash
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "虚拟环境不存在，请先运行: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

source .venv/bin/activate
echo "启动 Agentic Quant Web 看板..."
uvicorn web.app:app --host 0.0.0.0 --port 8000 --workers 1
