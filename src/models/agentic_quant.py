import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from openai import OpenAI
import time

class AgenticQuant:
    '''单日推演智能体 (LLM Agentic Quant)
    可以接受任意A股代码，自动获取该公司主营业务、量价特征、个股新闻以及全球宏观快讯。
    '''
    def __init__(self, api_key="your_api_key_here", base_url="https://api.deepseek.com/v1", model_name="deepseek-chat"):
        self.api_key = api_key
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name

    def fetch_company_profile(self, symbol: str) -> dict:
        print(f"正在获取 [{symbol}] 的公司基本信息与行业属性...")
        try:
            df_info = ak.stock_profile_cninfo(symbol)
            if not df_info.empty:
                return {
                    "name": df_info['公司名称'].values[0],
                    "industry": df_info['所属行业'].values[0],
                    "business": df_info['主营业务'].values[0],
                    "brief": df_info['机构简介'].values[0]
                }
        except Exception as e:
            print(f"获取公司资料失败: {e}")
        return {"name": f"A股代码 {symbol}", "industry": "未知", "business": "未知", "brief": "缺少资料"}

    def fetch_quant_status(self, symbol: str) -> dict:
        print(f"正在获取 [{symbol}] 最新的K线数据并计算多维量化特征...")
        try:
            # 获取日线级别前复权数据
            df = ak.stock_zh_a_hist(symbol=symbol, period="daily", adjust="qfq")
            
            # 【指标1：均线偏离与波动率】
            df['MA20'] = df['收盘'].rolling(20).mean()
            df['MA20_Bias'] = (df['收盘'] - df['MA20']) / df['MA20']
            df['Vol_5d'] = df['涨跌幅'].rolling(5).std()
            
            # 【指标2：MACD 趋势指标】
            ema12 = df['收盘'].ewm(span=12, adjust=False).mean()
            ema26 = df['收盘'].ewm(span=26, adjust=False).mean()
            df['MACD'] = ema12 - ema26
            
            # 【指标3：RSI (14) 强弱超买超卖指标】
            delta = df['收盘'].diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.ewm(com=14-1, min_periods=14).mean()
            avg_loss = loss.ewm(com=14-1, min_periods=14).mean()
            rs = avg_gain / avg_loss
            df['RSI_14'] = 100 - (100 / (1 + rs))
            
            # 【指标4：量能异动 (今日成交量 / 5日均量)】
            df['Volume_MA5'] = df['成交量'].rolling(5).mean()
            df['Volume_Ratio'] = df['成交量'] / df['Volume_MA5']
            
            # 取最近一天有效数据
            latest = df.dropna().iloc[-1]
            return {
                "date": latest['日期'],
                "close": latest['收盘'],
                "pct_change": latest['涨跌幅'],
                "ma20_bias": latest['MA20_Bias'],
                "volatility": latest['Vol_5d'],
                "macd": latest['MACD'],
                "rsi_14": latest['RSI_14'],
                "volume_ratio": latest['Volume_Ratio']
            }
        except Exception as e:
            print(f"获取行情失败: {e}")
            return None

    def fetch_news(self, symbol: str) -> tuple:
        print("正在获取 [全球宏观政经快讯]...")
        macro_news_list = []
        try:
            df_macro = ak.stock_info_global_sina()
            macro_news_list = df_macro['内容'].head(8).tolist()
        except:
            macro_news_list = ["获取宏观新闻失败"]

        print(f"正在获取 [{symbol}] 相关个股新闻与资金异动...")
        stock_news_list = []
        try:
            df_stock = ak.stock_news_em(symbol=symbol)
            if not df_stock.empty:
                stock_news_list = df_stock['新闻标题'].head(5).tolist()
        except:
            pass
        if not stock_news_list:
            stock_news_list = ["今日暂无重大个股异动或新闻"]
            
        return macro_news_list, stock_news_list

    def compile_and_predict(self, symbol: str):
        profile = self.fetch_company_profile(symbol)
        quant = self.fetch_quant_status(symbol)
        macro_news, stock_news = self.fetch_news(symbol)
        
        if quant is None:
            print("无法获取该股票量价数据，停止推演。")
            return

        prompt = f'''你是一位深谙政治经济学与行为金融学的顶尖A股量化游资操盘手。
你需要结合资产当前的多维技术面状态、公司的基本业务性质、以及今日的宏观/个股新闻，对该股票进行全面的“排雷”和明天的“推演”。

【研究标的档案】：
- 股票代码：{symbol} ({profile['name']})
- 所属行业：{profile['industry']}
- 主营业务：{profile['business']}

【当天盘面核心量价特征（截至 {quant['date']}）】：
- 现价：{quant['close']} 元(今日涨跌幅 {quant['pct_change']}%)
- 资金量能异动(量比)：{quant['volume_ratio']:.2f} （今日成交量是近5日均量的倍数，>1.5为明显放量，<0.8为极度缩量）
- 均线偏离度(MA20_Bias)：{quant['ma20_bias']:.4f} （正为超买获利盘多，负为超卖套牢盘多）
- 动量强弱指标(RSI_14)：{quant['rsi_14']:.2f} （>70警惕超买回调，<30注意超卖反弹）
- 均线趋势发散度(MACD)：{quant['macd']:.3f} （正为多头排列，负为空头排列）
- 市场情绪波动率(5日标准差)：{quant['volatility']:.4f}

【今日全市场宏观事件快讯】：
{chr(10).join(['- ' + str(n) for n in macro_news])}

【今日该股专属异动与新闻】：
{chr(10).join(['- ' + str(n) for n in stock_news])}

【你的分析任务】：
请用专业投研的风格写一段分析报告：
1. 宏观政策映射：结合该公司的【主营业务性质】，分析今日的宏观新闻是否会间接（或直接）影响该行业的政策预期或流动性。
2. 多维共振与资金情绪解读：结合个股专属新闻和今日盘面的多个技术指标（量比、均线、RSI、MACD等），指出当前的涨跌是由什么驱动的，大资金是在进场抢筹还是在拉高出货，有没有隐藏的筹码雷区（获利盘踩踏或恐慌杀跌）。
3. 明日博弈预判：综合给出你对明日该股票走势的最终短期推断结论（看涨 / 看跌 / 震荡），并用一句话给出操作建议。'''

        print("\n\n================ AI 思考的大脑数据输入 ==================")
        print(prompt)
        print("=========================================================\n")

        print("🚀 正在请求大模型，利用该股票的性质、量价、环境综合推演，请等待...")
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "你是一个结合A股打板和大宽客数据投研的顶尖量化分析师。风格要犀利、利用数据说话、简明干练。请注意：你的输出将直接发送到QQ，请务必使用纯文本格式，绝对不要使用任何 Markdown 语法（如加粗的**、标题的#等），请使用普通的换行和数字编号来进行排版。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
            )
            report = response.choices[0].message.content
            print("\n==================== 📈 AI 投研推演报告 📈 ====================")
            print(report)
            print("===============================================================\n")
            return report
        except Exception as e:
            err_msg = f"调用大模型报错: {e}"
            print(err_msg)
            return err_msg

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.getenv("DEEPSEEK_API_KEY")
    agent = AgenticQuant(api_key=api_key)
    
    agent.compile_and_predict(symbol="002594")