import os
from dotenv import load_dotenv
from src.models.agentic_quant import AgenticQuant

load_dotenv()

def main():
    print("=========================================")
    print("  🤖 AI 智能量化投研系统 (Agentic Quant) ")
    print("=========================================")

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("❌ 错误：未找到有效的 API Key！请新建 .env 文件加入 DEEPSEEK_API_KEY")
        return

    try:
        agent = AgenticQuant(api_key=api_key)
    except Exception as e:
        print(f"初始化系统失败: {e}")
        return

    while True:
        symbol = input("\n👉 请输入您想查阅推演的A股代码 (例如: 002594) ，或输入 'q' 退出: ").strip()

        if symbol.lower() == 'q':
            print("系统已退出。")
            break

        if not symbol.isdigit() or len(symbol) != 6:
            print("输入格式有误，请输入6位数字A股代码！")
            continue

        print(f"\n[系统已接收指令] 开始深度扫描并推演: {symbol}")
        agent.compile_and_predict(symbol=symbol)

        print("\n" + "-"*40)

if __name__ == "__main__":
    main()
