import os
import nonebot
from nonebot.adapters.onebot.v11 import Adapter as ONEBOT_V11Adapter
from dotenv import load_dotenv

# 1. 初始化 NoneBot2 框架
nonebot.init(
    host="127.0.0.1", 
    port=8080, 
    command_start=["", "/", "!", "！"] 
)
driver = nonebot.get_driver()
driver.register_adapter(ONEBOT_V11Adapter)

from nonebot.plugin import on_regex
from nonebot.rule import to_me
from nonebot.adapters.onebot.v11 import Bot, Event
from nonebot.params import RegexGroup
from nonebot.adapters.onebot.v11.message import Message

# 导入量化引擎
from src.models.agentic_quant import AgenticQuant

# 提前加载环境配置
load_dotenv()
api_key = os.getenv("DEEPSEEK_API_KEY")
quant_engine = AgenticQuant(api_key=api_key) if api_key else None

# 使用正则表达式：匹配 "查股票 600519", "分析600519", 或者直接发 "600519"
# 加入 rule=to_me()：私聊不需要@，群聊则必须主动 @机器人 才会触发（防止别人发验证码误触）
stock_matcher = on_regex(r"^(?:查股票\s*|/分析\s*|分析\s*)?(\d{6})$", rule=to_me(), priority=1, block=True)

@stock_matcher.handle()
async def handle_stock(bot: Bot, event: Event, args: tuple = RegexGroup()):
    if not quant_engine:
        await stock_matcher.finish("❌ 系统未配置 DEEPSEEK_API_KEY，机器人无法工作。")

    symbol = args[0]
    
    # 提醒用户正在处理中
    await stock_matcher.send(f"⏳已接收指令！正在抓取 [{symbol}] 数据进行AI深度推演，请稍等阅览最后报告...")
    
    try:
        # Nonebot推荐使用 asyncio.to_thread 运行阻塞任务（如 requests 请求和 OpenAI 回调）
        import asyncio
        report = await asyncio.to_thread(quant_engine.compile_and_predict, symbol)
        
        if report:
            # 推演成功，加上首尾装饰，返回给QQ
            final_msg = f"🤖 Agentic Quant 个股脱水研报\n{'='*20}\n{report}\n{'='*20}\n💡 仅供交流，股市有风险，投资需谨慎。"
            await stock_matcher.send(final_msg)
        else:
            await stock_matcher.send("❌ 获取数据或推演失败，可能该股票停牌或不存在。")
            
    except Exception as e:
        await stock_matcher.send(f"❌ 发生不可预知的错误: {e}")

# ==============================================================================
# 启动机器人
# ==============================================================================
if __name__ == "__main__":
    nonebot.run()