# 🚀 阿里云 (Ubuntu) 云服务器部署指南

由于大语言模型接口和 QQ 机器人需要长期的在线陪伴，将 `AgenticQuant` 部署到轻量级云服务器（如阿里云 2C2G Ubuntu 镜像）是最佳选择。

本指南将带你从零开始，在 Ubuntu 系统上部署本项目。

## 第一步：连接服务器与基础环境更新

使用 SSH 登录到你的阿里云服务器后台后，首先更新系统并安装 Python 虚拟环境相关的系统支撑包：

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip git screen -y
```

## 第二步：拉取项目代码

使用 Git 将你在 GitHub 上的代码克隆到云服务器上：

```bash
# 注意：请将下面的链接替换为你自己真实的 GitHub 仓库地址
git clone https://github.com/您的用户名/-Agentic-Quant-.git
cd -Agentic-Quant-
```

## 第三步：部署隔离的 Python 虚拟环境与依赖

在 Linux 服务器上强烈建议使用 `.venv` 虚拟环境，以避免污染系统环境。

```bash
# 1. 创建虚拟环境
python3 -m venv .venv

# 2. 激活虚拟环境
source .venv/bin/activate

# 3. 根据项目的清单文件一键安装依赖
pip install -r requirements.txt
```

## 第四步：配置大模型 API 密钥

在本地开发时，我们将 `.env` 文件保护了起来（写在了 `.gitignore` 中），所以 GitHub 上下载的代码**是不带 `.env` 的**。你需要在服务器上手工创建一个：

```bash
# 生成 .env 文件并写入你的 API 密钥（将 sk-xxx 替换为你真实的秘钥）
echo 'DEEPSEEK_API_KEY="sk-你的真实API秘钥写在这里"' > .env
```

## 第五步：配合 NapCatQQ 使用

本项目的 `bot.py` 是逻辑中枢（通过 WS 连接 8080 端口），你同样需要在服务器上挂一个 **NapCatQQ**（建议使用 Docker 版本或 CLI 无头版本）来登录你的 QQ 号，并设置反向 WebSocket 连接至 `ws://127.0.0.1:8080`。

## 第六步：启动机器人（后台持久运行）

如果你直接执行 `bash start_bot.sh`，当你关掉 SSH 登录窗口时，机器人也会随之断开。
为了让它 **7x24小时永不眠**，我们使用刚才安装的 `screen` 工具：

```bash
# 1. 创建一个叫 quant_bot 的后台窗口
screen -S quant_bot

# 2. 在这个窗口里启动机器人
bash start_bot.sh

# 3. 【重点】如何全身而退？
# 此时机器人已经跑起来了，请依次按下键盘上的快捷键：
# 按住 Ctrl 不要松手，然后按 A，接着按 D。
# 这样你就会退回到原本的命令行，而机器人会在后台继续运行！
```

**日常维护指令**：
- 想看机器人运行日志？输入 `screen -r quant_bot` 切回画面。
- 想要再次退出后台且不关闭？照旧按 `Ctrl+A` 然后按 `D`。
- 如果改了代码想更新服务器代码？进入目录执行 `git pull`，然后重启机器人即可。