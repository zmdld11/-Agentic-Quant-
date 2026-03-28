<div align="center">
  <h1>🤖 Agentic Quant</h1>
  <p><b>基于大语言模型与政治经济学的A股单日量化投研系统</b></p>
  <p>
    <img src="https://img.shields.io/badge/Python-3.13-blue.svg" alt="Python Version">
    <img src="https://img.shields.io/badge/LLM-DeepSeek-deepblue.svg" alt="LLM Backing">
    <img src="https://img.shields.io/badge/Data-AkShare-green.svg" alt="AkShare">
    <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
  </p>
</div>

<br/>

## 📖 项目简介

这是一个极具前沿思维的 **“大语言模型量化智能体 (LLM Agentic Quant)”**。

传统量化模型仅依赖 K线和技术指标进行硬卷，但在政策驱动和消息面变幻莫测的A股市场中常常失灵。本项目打通了 **“个股基本面档案 + 实时量价异动 + 宏观/个股新闻自动爬取 + LLM 深度政经逻辑推演”** 的全链路，让 AI 像顶尖私募研究员一样，帮你做A股单日盯盘与推演报告。

## ✨ 核心特性

- **数据获取引擎 (`akshare`)**：实时抓取任何输入A股的当天收盘价、技术指标偏离度、公司主营业务。
- **动态新闻爬虫**：实时截获当天全球重大宏观政治事件 + 目标个股专属重大公告，作为资金面和政策面的基本底座。
- **大语言模型思考大脑**：融合上述数字/文本，通过一套专业的“政治经济学”量化 Prompt，自动交由 DeepSeek / 通义千问等模型产生次日的走势推断与避雷警告。

## 🛠️ 环境依赖

本项目基于本地 Python 3.13 环境搭建。

### 1. 克隆项目
```bash
git clone https://github.com/yourusername/Market-Quantification.git
cd Market-Quantification
```

### 2. 创建并激活虚拟环境 (Windows)
```powershell
python -m venv venv
.\venv\Scripts\activate
```

### 3. 安装依赖包
```bash
pip install -r requirements.txt
```

### 4. 配置环境变量
在项目根目录创建一个 `.env` 文件，并填入你的大模型 API 密钥（默认支持 DeepSeek OpenAI SDK 格式）：
```env
DEEPSEEK_API_KEY="sk-your-api-key-here"
```

## 🚀 如何使用

我们已经将复杂的内部爬虫与推演全部封装在了主程序中！

**执行以下命令启动交互式分析引擎：**

```bash
python main.py
```

执行后，按照控制台提示：
1. **输入你想分析的任意 6 位A股代码**（例如茅台：`600519`，或 比亚迪：`002594`）。
2. 系统会自动发爬虫去收集它的公司档案、今日最新K线状态以及有关它今天的所有新闻。
3. 随后，大模型会生成一篇**犀利的次日投研推演报告**，判断它的涨跌逻辑和政治经济风险。

## 🧩 扩展与二次开发

- **更换大模型**：项目默认采用性价比最高的 DeepSeek-Chat，如果想更换厂商，直接修改 `src/models/agentic_quant.py` 初始化函数中的 `base_url` 即可。
- **增加新因子**：我们预留了丰富的数据源抓取空间。你可以往 `AgenticQuant` 类中随时补充“北向资金”、“龙虎榜机构净买入”或“美联储加息预期”等更高级的特征供 LLM 推理。

## ⚠️ 免责声明

本项目仅供学术研究与量化技术探讨使用。AI 推演结果**不构成任何投资建议**。A股有风险，入市需谨慎。

## 📄 协议

本项目基于 [MIT License](LICENSE) 开源。
