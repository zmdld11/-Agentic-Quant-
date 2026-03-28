from src.models.agentic_quant import AgenticQuant

def main():
    print("=========================================")
    print("  🤖 AI 智能量化投研系统 (Agentic Quant) ")
    print("=========================================")
    
    # 填入您真实的 API KEY
    api_key = "sk-7ae89e952ee9477b9564cd09686769c0"
    
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
