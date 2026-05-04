from ib_insync import *

def main():
    # 实例化一个 IB 连接对象
    ib = IB()
    
    print("正在尝试连接到本地 TWS 模拟盘 (端口 7497)...")
    try:
        # 连接本地的 TWS 客户端
        # clientId=1 是你的程序代号，随便填一个整数即可
        ib.connect('127.0.0.1', 7497, clientId=1)
        print("✅ 连接成功！你已经连上了 IBKR 模拟盘！")
        
        # 试着查询一下你的模拟盘账户里有多少钱
        account_summary = ib.accountSummary()
        for item in account_summary:
            if item.tag == 'NetLiquidation':
                print(f"💰 你的模拟盘总资产是: {item.value} {item.currency}")
                break
                
    except Exception as e:
        print(f"❌ 连接失败，请检查 TWS 是否已打开并且配置了允许 API 连接！错误信息: {e}")
        
    finally:
        if ib.isConnected():
            ib.disconnect()

if __name__ == "__main__":
    main()