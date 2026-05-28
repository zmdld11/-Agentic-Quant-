# Agentic Quant Web 量化投研看板 部署与使用指南

## 系统架构

```
浏览器 ──▶ http://<服务器IP>:8000 ──▶ FastAPI (uvicorn)
                                      ├─ /              → 前端看板页面
                                      ├─ /api/analyze   → AI 量化分析
                                      ├─ /api/kline/:code → K线数据
                                      └─ /api/health     → 健康检查
                                              │
                                      AgenticQuant Engine
                                      ├─ Baostock → K线/基本面
                                      ├─ akshare  → 新闻/情绪
                                      └─ DeepSeek → LLM 推理
```

## 环境要求

- Ubuntu 20.04+ (或其他 Linux 发行版)
- Python 3.10+
- 2C2G 内存（绰绰有余）

## 部署步骤

### 1. 克隆代码

```bash
git clone https://github.com/zmdld11/-Agentic-Quant-.git
cd ./-Agentic-Quant-
```

### 2. 创建虚拟环境并安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 配置 API Key

```bash
echo 'DEEPSEEK_API_KEY="sk-你的秘钥"' > .env
```

### 4. 放行端口（阿里云）

登录阿里云控制台 → ECS → 安全组 → 入方向 → 添加规则：
- 端口：`8000`
- 授权对象：`0.0.0.0/0`

### 5. 测试运行

```bash
bash start_web.sh
```

然后浏览器访问 `http://<你的服务器公网IP>:8000`，能看到看板页面即为成功。

### 6. 设为系统服务（开机自启、崩溃重启）

```bash
# 修改服务文件中的路径（如果不同）
sudo cp web/quant.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable quant
sudo systemctl start quant
```

常用命令：
```bash
sudo systemctl status quant    # 查看运行状态
sudo systemctl restart quant   # 重启服务
sudo journalctl -u quant -f    # 实时查看日志
```

### 7. 更新代码

```bash
cd ./-Agentic-Quant-
git pull
sudo systemctl restart quant
```

## 博客集成（Quartz 4）

在 Quartz 4 项目的 `quartz.config.ts` 或导航配置中添加外链：

```typescript
// 在 header.menuLinks 中添加
{ title: "📊 量化", href: "http://<你的服务器IP>:8000", external: true }
```

## 使用方式

1. 打开看板页面
2. 输入 6 位 A 股代码（如 600519）
3. 点击"分析"或按回车
4. 等待约 10-30 秒（数据抓取 + LLM 推理）
5. 查看 K 线图和 AI 投研报告

## 主题切换

看板支持亮色/暗色双模式：
- 默认跟随系统主题
- 点击右上角按钮手动切换
- 选择会记住（localStorage）

## 数据源说明

| 数据类型 | 来源 | 说明 |
|---------|------|------|
| K线(OHLCV) | Baostock | 免费免注册，全A股1990至今 |
| 公司档案 | Baostock | 股票基本信息、行业 |
| 宏观新闻 | akshare (新浪) | 全球政经快讯 |
| 个股新闻 | akshare (东方财富) | 个股公告异动 |
| 散户情绪 | 东方财富股吧 | 近7天热帖标题 |

## 故障排查

| 问题 | 可能原因 | 解决 |
|------|---------|------|
| 页面打不开 | 8000端口未放行 | 检查阿里云安全组 |
| 分析失败 | API Key 无效 | 检查 .env 文件 |
| K线图空白 | Baostock 数据源异常 | 查看 `journalctl -u quant` 日志 |
| 新闻为空 | akshare 被限制 | 等待几小时后重试（频率低不会被封） |

## 免责声明

本项目仅供学术研究与量化技术探讨使用。AI 推演结果**不构成任何投资建议**。A股有风险，投资需谨慎。
