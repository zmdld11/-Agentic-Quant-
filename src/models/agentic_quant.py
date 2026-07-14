import akshare as ak
import baostock as bs
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from openai import OpenAI
import time
import threading

class AgenticQuant:
    '''单日推演智能体 (LLM Agentic Quant)
    可以接受任意A股代码，自动获取该公司主营业务、量价特征、个股新闻以及全球宏观快讯。
    加入内存级缓存机制，防恶意刷单导致IP被封。
    '''
    def __init__(self, api_key="your_api_key_here", base_url="https://api.deepseek.com", model_name="deepseek-v4-flash"):
        self.api_key = api_key
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name
        # 内存级缓存，防止IP被封：数据有效存活期1小时 (3600秒)
        self.cache = {}
        self.cache_ttl = 3600
        self._report_cache = {}
        self._news_cache = None
        self._news_cache_time = 0
        self._news_lock = threading.Lock()
        self._start_news_updater()

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
            df_info = ak.stock_profile_cninfo(symbol)
            if not df_info.empty:
                res = {
                    "name": df_info['公司名称'].values[0],
                    "industry": df_info['所属行业'].values[0],
                    "business": df_info['主营业务'].values[0],
                    "brief": df_info['机构简介'].values[0]
                }
                self._set_cache(cache_key, res)
                return res
        except Exception as e:
            print(f"获取公司资料失败: {e}")
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

            # 过滤掉空值行（部分股票存在空字符串）
            df_raw = df_raw[df_raw['close'] != ''].copy()
            if df_raw.empty:
                raise ValueError("Baostock 数据全部为空")

            df = pd.DataFrame()
            df['日期'] = df_raw['date']
            df['收盘'] = df_raw['close'].astype(float)
            df['成交量'] = df_raw['volume'].replace('', '0').astype(float)
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

            # 过滤空值行
            df_raw = df_raw[df_raw['close'] != '']

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

        data_summary = {
            "name": profile.get('name', ''),
            "industry": profile.get('industry', ''),
            "business": profile.get('business', ''),
            "close": quant.get('close'),
            "pct_change": quant.get('pct_change'),
            "volume_ratio": quant.get('volume_ratio'),
            "rsi": quant.get('rsi_14'),
            "macd": quant.get('macd'),
            "ma20_bias": quant.get('ma20_bias'),
            "macro_news": macro_news,
            "stock_news": stock_news,
            "retail_sentiment": retail_sentiment,
        }

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
            "data_summary": data_summary,
            "report": None
        }

    def get_report(self, symbol: str, data_summary: dict) -> str:
        import time as time_module

        # Check cache (30 min TTL)
        cached = self._report_cache.get(symbol)
        if cached:
            report_text, ts = cached
            if time_module.time() - ts < 1800:
                print(f"[缓存命中] {symbol} 的分析报告（30分钟内有效）")
                return report_text

        print(f"正在请求大模型，利用该股票的性质、量价、环境综合推演 {symbol}...")

        profile_name = data_summary.get('name', '')
        industry = data_summary.get('industry', '')
        business = data_summary.get('business', '')
        close = data_summary.get('close', 'N/A')
        pct_change = data_summary.get('pct_change', 'N/A')
        volume_ratio = data_summary.get('volume_ratio', 'N/A')
        rsi = data_summary.get('rsi', 'N/A')
        macd = data_summary.get('macd', 'N/A')
        ma20_bias = data_summary.get('ma20_bias', 'N/A')
        macro_news = data_summary.get('macro_news', [])
        stock_news = data_summary.get('stock_news', [])
        retail_sentiment = data_summary.get('retail_sentiment', [])

        prompt = f'''你是一位深谙政治经济学与行为金融学的顶尖A股量化游资操盘手。
你需要结合资产当前的多维技术面状态、公司的基本业务性质、以及今日的宏观/个股新闻，对该股票进行全面的"排雷"和明天的"推演"。

【研究标的档案】：
- 股票代码：{symbol} ({profile_name})
- 所属行业：{industry}
- 主营业务：{business}

【当天盘面核心量价特征】：
- 现价：{close} 元(今日涨跌幅 {pct_change}%)
- 资金量能异动(量比)：{volume_ratio} （今日成交量是近5日均量的倍数，>1.5为明显放量，<0.8为极度缩量）
- 均线偏离度(MA20_Bias)：{ma20_bias} （正为超买获利盘多，负为超卖套牢盘多）
- 动量强弱指标(RSI_14)：{rsi} （>70警惕超买回调，<30注意超卖反弹）
- 均线趋势发散度(MACD)：{macd} （正为多头排列，负为空头排列）

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

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "你是一个结合A股打板和大宽客数据投研的顶尖量化分析师。风格要犀利、利用数据说话、简明干练。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                timeout=60,
            )
            report = response.choices[0].message.content
            print("\n==================== AI 投研推演报告 ====================")
            print(report)
            print("===============================================================\n")
        except Exception as e:
            report = f"调用大模型报错: {e}"
            print(report)

        self._report_cache[symbol] = (report, time_module.time())
        return report

    def calc_stock_sync(self, symbol_a: str, symbol_b: str) -> dict:
        """计算两只股票的涨跌同步率（Pearson 相关系数 + 走势叠加）"""
        try:
            bs.login()
            code_a = self._to_baostock_code(symbol_a)
            code_b = self._to_baostock_code(symbol_b)
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=300)).strftime('%Y-%m-%d')

            rs_a = bs.query_history_k_data_plus(code_a, "date,close", start_date=start_date, end_date=end_date, frequency="d", adjustflag="2")
            rs_b = bs.query_history_k_data_plus(code_b, "date,close", start_date=start_date, end_date=end_date, frequency="d", adjustflag="2")
            df_a = rs_a.get_data()
            df_b = rs_b.get_data()
            bs.logout()

            if df_a.empty or df_b.empty:
                return {"error": "数据获取失败"}

            df_a = df_a.rename(columns={'close': 'close_a'})[['date', 'close_a']]
            df_b = df_b.rename(columns={'close': 'close_b'})[['date', 'close_b']]
            merged = pd.merge(df_a, df_b, on='date', how='inner')
            merged['close_a'] = merged['close_a'].astype(float)
            merged['close_b'] = merged['close_b'].astype(float)

            if len(merged) < 20:
                return {"error": "共同交易日不足20天"}

            corr = merged['close_a'].corr(merged['close_b'])

            # Normalized overlay
            merged['norm_a'] = merged['close_a'] / merged['close_a'].iloc[0] * 100
            merged['norm_b'] = merged['close_b'] / merged['close_b'].iloc[0] * 100

            # Scatter data
            scatter = [{"x": round(float(merged['close_a'].iloc[i]), 2), "y": round(float(merged['close_b'].iloc[i]), 2)} for i in range(len(merged))]

            # Overlay data
            overlay = []
            for _, row in merged.iterrows():
                overlay.append({"date": row['date'], "norm_a": round(float(row['norm_a']), 2), "norm_b": round(float(row['norm_b']), 2)})

            abs_corr = abs(corr)
            if abs_corr > 0.8: level = "高度同步"
            elif abs_corr > 0.5: level = "中度同步"
            elif abs_corr > 0.3: level = "弱同步"
            else: level = "几乎不同步"

            return {
                "symbol_a": symbol_a, "symbol_b": symbol_b,
                "pearson": round(float(corr), 4),
                "sync_level": level,
                "common_days": int(len(merged)),
                "overlay": overlay,
                "scatter": scatter
            }
        except Exception as e:
            try: bs.logout()
            except: pass
            return {"error": str(e)}

    def fetch_official_news(self, date_str: str = None) -> dict:
        """获取指定日期的官方媒体新闻报道"""
        if date_str is None:
            date_str = datetime.now().strftime('%Y-%m-%d')

        cache_key = f"official_news_{date_str}"
        if cached := self._get_cache(cache_key):
            return cached

        print(f"正在获取 [{date_str}] 官方媒体报道...")
        result = {"date": date_str, "macro": [], "stock_specific": []}

        try:
            macro = ak.stock_info_global_em()
            if not macro.empty:
                for _, row in macro.head(20).iterrows():
                    result["macro"].append({"title": str(row['标题']), "time": str(row.get('发布时间', ''))})
        except Exception as e:
            print(f"宏观新闻获取失败: {e}")

        try:
            sina = ak.stock_info_global_sina()
            if not sina.empty:
                for _, row in sina.head(20).iterrows():
                    title = str(row.get('title', row.get('内容', '')))
                    if title and title != 'nan':
                        result["stock_specific"].append({"title": title, "time": date_str})
        except Exception as e:
            print(f"新浪快讯获取失败: {e}")

        # Deduplicate
        seen = set()
        for cat in ["macro", "stock_specific"]:
            unique = []
            for item in result[cat]:
                if item['title'] not in seen:
                    seen.add(item['title'])
                    unique.append(item)
            result[cat] = unique

        self._set_cache(cache_key, result)
        return result

    def _start_news_updater(self):
        """启动后台线程，每6小时自动刷新官方新闻"""
        def updater():
            while True:
                print("[新闻后台更新] 正在刷新官方新闻缓存...")
                try:
                    self._news_cache = self.fetch_official_news()
                    self._news_cache_time = time.time()
                    print("[新闻后台更新] 完成")
                except Exception as e:
                    print(f"[新闻后台更新] 失败: {e}")
                time.sleep(6 * 3600)

        thread = threading.Thread(target=updater, daemon=True)
        thread.start()

    def get_cached_news(self, date_str: str = None) -> dict:
        """返回缓存的官方新闻，若日期不匹配则实时获取"""
        if date_str is None:
            date_str = datetime.now().strftime('%Y-%m-%d')

        if self._news_cache is not None:
            cache_date = self._news_cache.get('date', '')
            if cache_date == date_str:
                print(f"[新闻缓存命中] date={date_str}")
                return self._news_cache

        print(f"[新闻缓存未命中] 实时获取 date={date_str}")
        result = self.fetch_official_news(date_str)
        self._news_cache = result
        self._news_cache_time = time.time()
        return result

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv("DEEPSEEK_API_KEY")
    agent = AgenticQuant(api_key=api_key)

    result = agent.compile_and_predict(symbol="002594")
    if "error" not in result:
        print(result["report"])