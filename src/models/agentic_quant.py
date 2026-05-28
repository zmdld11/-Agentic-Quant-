import akshare as ak
import baostock as bs
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from openai import OpenAI
import time

class AgenticQuant:
    '''单日推演智能体 (LLM Agentic Quant)
    可以接受任意A股代码，自动获取该公司主营业务、量价特征、个股新闻以及全球宏观快讯。
    加入内存级缓存机制，防恶意刷单导致IP被封。
    '''
    def __init__(self, api_key="your_api_key_here", base_url="https://api.deepseek.com/v1", model_name="deepseek-chat"):
        self.api_key = api_key
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name
        # 内存级缓存，防止IP被封：数据有效存活期1小时 (3600秒)
        self.cache = {}
        self.cache_ttl = 3600

    @staticmethod
    def _to_baostock_code(symbol: str) -> str:
        """600519 -> sh.600519, 002594 -> sz.002594"""
        if symbol.startswith('6'):
            return f"sh.{symbol}"
        elif symbol.startswith(('0', '3')):
            return f"sz.{symbol}"
        elif symbol.startswith(('4', '8')):
            return f"bj.{symbol}"
        return f"sz.{symbol}"

    def _get_cache(self, key):
        if key in self.cache:
            data, timestamp = self.cache[key]
            if time.time() - timestamp < self.cache_ttl:
                return data
        return None

    def _set_cache(self, key, data):
        self.cache[key] = (data, time.time())

    def fetch_company_profile(self, symbol: str) -> dict:
        cache_key = f"profile_{symbol}"
        if cached := self._get_cache(cache_key): return cached

        print(f"正在获取 [{symbol}] 的公司基本信息与行业属性...")
        try:
            bs.login()
            rs = bs.query_stock_basic(code=self._to_baostock_code(symbol))
            data = rs.get_data()
            bs.logout()

            if not data.empty:
                row = data.iloc[0]
                res = {
                    "name": row['code_name'],
                    "industry": row.get('industry', '未知') if 'industry' in data.columns else '未知',
                    "business": row.get('business', '未知') if 'business' in data.columns else '未知',
                    "brief": f"{row['code_name']}，上市日期: {row.get('ipoDate', 'N/A')}"
                }
                self._set_cache(cache_key, res)
                return res
        except Exception as e:
            print(f"获取公司资料失败: {e}")
            try: bs.logout()
            except: pass
        return {"name": f"A股代码 {symbol}", "industry": "未知", "business": "未知", "brief": "缺少资料"}

    def fetch_quant_status(self, symbol: str) -> dict:
        cache_key = f"quant_{symbol}"
        if cached := self._get_cache(cache_key): return cached

        print(f"正在获取 [{symbol}] 最新的K线数据并计算多维量化特征...")
        try:
            bs.login()
            code = self._to_baostock_code(symbol)
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=200)).strftime('%Y-%m-%d')

            rs = bs.query_history_k_data_plus(
                code, "date,open,high,low,close,volume,amount",
                start_date=start_date, end_date=end_date,
                frequency="d", adjustflag="2"
            )
            df_raw = rs.get_data()
            bs.logout()

            if df_raw.empty:
                raise ValueError("Baostock 返回空数据")

            df = pd.DataFrame()
            df['日期'] = df_raw['date']
            df['收盘'] = df_raw['close'].astype(float)
            df['成交量'] = df_raw['volume'].astype(float)
            df['涨跌幅'] = df['收盘'].pct_change() * 100

            df['MA20'] = df['收盘'].rolling(20).mean()
            df['MA20_Bias'] = (df['收盘'] - df['MA20']) / df['MA20']
            df['Vol_5d'] = df['涨跌幅'].rolling(5).std()

            ema12 = df['收盘'].ewm(span=12, adjust=False).mean()
            ema26 = df['收盘'].ewm(span=26, adjust=False).mean()
            df['MACD'] = ema12 - ema26

            delta = df['收盘'].diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.ewm(com=14-1, min_periods=14).mean()
            avg_loss = loss.ewm(com=14-1, min_periods=14).mean()
            rs_val = avg_gain / avg_loss
            df['RSI_14'] = 100 - (100 / (1 + rs_val))

            df['Volume_MA5'] = df['成交量'].rolling(5).mean()
            df['Volume_Ratio'] = df['成交量'] / df['Volume_MA5']

            latest = df.dropna().iloc[-1]
            result = {
                "date": str(latest['日期']),
                "close": float(latest['收盘']),
                "pct_change": float(latest['涨跌幅']),
                "ma20_bias": float(latest['MA20_Bias']),
                "volatility": float(latest['Vol_5d']),
                "macd": float(latest['MACD']),
                "rsi_14": float(latest['RSI_14']),
                "volume_ratio": float(latest['Volume_Ratio'])
            }
            self._set_cache(cache_key, result)
            return result
        except Exception as e:
            print(f"获取行情失败: {e}")
            try: bs.logout()
            except: pass
            return None

    def fetch_kline_range(self, symbol: str, days: int = 60) -> list:
        cache_key = f"kline_{symbol}_{days}"
        if cached := self._get_cache(cache_key): return cached

        try:
            bs.login()
            code = self._to_baostock_code(symbol)
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=days + 30)).strftime('%Y-%m-%d')

            rs = bs.query_history_k_data_plus(
                code, "date,open,high,low,close,volume",
                start_date=start_date, end_date=end_date,
                frequency="d", adjustflag="2"
            )
            df_raw = rs.get_data()
            bs.logout()

            if df_raw.empty:
                return []

            kline = []
            for _, row in df_raw.tail(days).iterrows():
                kline.append({
                    "date": row['date'],
                    "open": float(row['open']),
                    "high": float(row['high']),
                    "low": float(row['low']),
                    "close": float(row['close']),
                    "volume": float(row['volume'])
                })
            self._set_cache(cache_key, kline)
            return kline
        except Exception as e:
            print(f"获取K线数据失败: {e}")
            try: bs.logout()
            except: pass
            return []

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

    def fetch_retail_sentiment(self, symbol: str) -> list:
        cache_key = f"sentiment_{symbol}"
        if cached := self._get_cache(cache_key): return cached
        
        print(f"正在获取 [{symbol}] 的近期散户微观情绪与小道消息...")
        import requests
        import re
        from datetime import datetime, timedelta
        
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            res = requests.get(f'https://guba.eastmoney.com/list,{symbol}.html', headers=headers, timeout=5)
            res.encoding = 'utf-8'
            
            posts = re.findall(r'<div class="title"><a[^>]*>(.*?)</a></div></td>.*?<div class="update">(\d{2}-\d{2}) \d{2}:\d{2}</div>', res.text)
            
            valid_posts = []
            now = datetime.now()
            current_year = now.year
            
            for title, date_str in posts:
                try:
                    post_date = datetime.strptime(f"{current_year}-{date_str}", "%Y-%m-%d")
                    if post_date > now + timedelta(days=1):
                        post_date = datetime.strptime(f"{current_year-1}-{date_str}", "%Y-%m-%d")
                        
                    if (now - post_date).days <= 7:
                        clean_title = re.sub(r'<[^>]+>', '', title).strip()
                        if clean_title and clean_title not in valid_posts:
                            valid_posts.append(clean_title)
                except:
                    continue
                    
            res_list = valid_posts[:10]
            if not res_list:
                res_list = ["近7天该股票吧暂无活跃讨论或小道消息"]
                
            self._set_cache(cache_key, res_list)
            return res_list
        except Exception as e:
            print(f"获取论坛情绪失败: {e}")
            return ["获取论坛情绪失败"]


    def compile_and_predict(self, symbol: str) -> dict:
        profile = self.fetch_company_profile(symbol)
        quant = self.fetch_quant_status(symbol)

        if quant is None:
            return {"error": "无法获取该股票量价数据，停止推演。"}

        macro_news, stock_news = self.fetch_news(symbol)
        retail_sentiment = self.fetch_retail_sentiment(symbol)
        kline_data = self.fetch_kline_range(symbol, days=60)

        prompt = f'''你是一位深谙政治经济学与行为金融学的顶尖A股量化游资操盘手。
你需要结合资产当前的多维技术面状态、公司的基本业务性质、以及今日的宏观/个股新闻，对该股票进行全面的"排雷"和明天的"推演"。

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

【散户微观情绪与小道消息（近7日）】：
{chr(10).join(['- ' + str(n) for n in retail_sentiment])}

【你的分析任务】：
请用专业投研的风格写一段分析报告：
1. 宏观政策映射：结合该公司的【主营业务性质】，分析今日的宏观新闻是否会间接（或直接）影响该行业的政策预期或流动性。
2. 多维共振与资金情绪解读：结合个股专属新闻和今日盘面的多个技术指标（量比、均线、RSI、MACD等），指出当前的涨跌是由什么驱动的，大资金是在进场抢筹还是在拉高出货，有没有隐藏的筹码雷区（获利盘踩踏或恐慌杀跌）。
3. 散户心理与暗线跟踪：结合最新的【散户微观情绪与小道消息】，指出市场是否存在未被新闻披露的"小作文"驱动，或者是否存在"买预期卖现实"的踩踏风险。
4. 明日博弈预判：综合给出你对明日该股票走势的最终短期推断结论（看涨 / 看跌 / 震荡），并用一句话给出操作建议。'''

        print("\n\n================ AI 思考的大脑数据输入 ==================")
        print(prompt)
        print("=========================================================\n")

        print("正在请求大模型，利用该股票的性质、量价、环境综合推演，请等待...")
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "你是一个结合A股打板和大宽客数据投研的顶尖量化分析师。风格要犀利、利用数据说话、简明干练。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
            )
            report = response.choices[0].message.content
            print("\n==================== AI 投研推演报告 ====================")
            print(report)
            print("===============================================================\n")
        except Exception as e:
            report = f"调用大模型报错: {e}"
            print(report)

        return {
            "symbol": symbol,
            "name": profile.get('name', ''),
            "industry": profile.get('industry', ''),
            "business": profile.get('business', ''),
            "quote": quant,
            "kline_data": kline_data,
            "macro_news": macro_news,
            "stock_news": stock_news,
            "retail_sentiment": retail_sentiment,
            "report": report
        }

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv("DEEPSEEK_API_KEY")
    agent = AgenticQuant(api_key=api_key)

    result = agent.compile_and_predict(symbol="002594")
    if "error" not in result:
        print(result["report"])