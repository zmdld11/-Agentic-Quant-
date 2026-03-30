@echo off
chcp 65001 > nul
title Agentic Quant QQ机器人
color 0B

echo =======================================================
echo          🚀 正在启动 Agentic Quant 量化机器人
echo =======================================================
echo.
echo [提示] 启动后请保持此窗口打开，关闭窗口即为关闭机器人。
echo [提示] 如果没连上，请检查 NapCatQQ 是否已经登录并运行。
echo.

:: 切换到该脚本所在的当前目录
cd /d "%~dp0"

:: 激活虚拟环境
call ".\.venv\Scripts\activate.bat"

:: 启动机器人程序
python bot.py

:: 运行结束或崩溃时不要直接闪退，保留窗口方便查看报错
pause
