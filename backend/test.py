import requests

def verify_itick_api():
    """
    验证iTick API密钥并获取贵金属数据样例
    """
    api_token = "551a84b79ae24790b847766fac8d5fe18b5821fc2051484c9a8e72e8afa6a794"
    
    # 测试XAUUSD（黄金）和 XAGUSD（白银）
    symbols = [
        {"name": "黄金(XAUUSD)", "code": "XAUUSD"},
        {"name": "白银(XAGUSD)", "code": "XAGUSD"}
    ]
    
    for symbol in symbols:
        url = f"https://api.itick.org/forex/tick?region=gb&code={symbol['code']}"
        headers = {
            "accept": "application/json",
            "token": api_token
        }
        
        print(f"正在请求 {symbol['name']} 数据...")
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                print(f"✓ 成功! 响应样例: {data}")
            else:
                print(f"✗ 失败! 状态码: {response.status_code}, 响应: {response.text[:100]}")
        except Exception as e:
            print(f"✗ 请求异常: {e}")
        print("-" * 50)

if __name__ == "__main__":
    verify_itick_api()