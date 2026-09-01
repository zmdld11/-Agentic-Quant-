"""本地配置：从项目根目录的 .env 文件加载环境变量（密钥不进 git）。

.env 格式（KEY=VALUE 每行一条，# 开头为注释）：
    LLM_API_KEY=sk-xxx
    LLM_BASE_URL=https://api.deepseek.com/v1
    LLM_MODEL=deepseek-chat

已存在的环境变量优先（shell 里 export 过的不被 .env 覆盖）。
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load_env() -> None:
    """把 .env 读进环境变量（幂等，文件不存在则静默跳过）。"""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def llm_status() -> str:
    """脱敏的状态描述（用于日志，绝不打印完整 key）。"""
    key = os.environ.get("LLM_API_KEY", "")
    if not key:
        return "未配置 LLM_API_KEY"
    tail = key[-4:] if len(key) >= 8 else "****"
    return (f"LLM 已配置: {os.environ.get('LLM_BASE_URL', '(默认智谱)')} "
            f"model={os.environ.get('LLM_MODEL', '(默认)')} key=****{tail}")
