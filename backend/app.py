"""
宏观经济AI分析工具 - 优化版后端服务
1. 实时市场信号（Ziwox）
2. 实时汇率（Alpha Vantage + Ziwox补充）
3. 经济日历（Alpha Vantage + 备用API）
4. AI综合分析（laozhang.ai）
"""

import os
import json
import logging
import time
import threading
import random
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
import requests
from alpha_vantage.foreignexchange import ForeignExchange

# 创建Flask应用
app = Flask(__name__)
CORS(app)

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# 配置管理
# ============================================================================
class Config:
    def __init__(self):
        # laozhang.ai 配置 - 修复：使用正确的令牌格式
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "sk-Cm0SeWFJgMvODmsJ0273Ab49E38e4369BfDf4c4793B71cA5")
        self.openai_base_url = "https://api.laozhang.ai/v1"
        
        # Alpha Vantage 配置
        self.alpha_vantage_key = os.getenv("ALPHA_VANTAGE_KEY", "2M66S0EB6ZMHO2ST")
        
        # Ziwox API 配置
        self.ziwox_api_key = os.getenv("ZIWOX_API_KEY", "B65991B99EB498AB")
        self.ziwox_api_url = "https://ziwox.com/terminal/services/API/V1/fulldata.php"
        
        # 模式开关
        self.use_mock = os.getenv("USE_MOCK_DATA", "false").lower() == "true"
        self.enable_ai = os.getenv("ENABLE_AI", "true").lower() == "true"
        
        # 监控的货币对
        self.watch_currency_pairs = [
            'EURUSD', 'GBPUSD', 'USDCHF', 'USDCNH', 
            'USDJPY', 'AUDUSD', 'XAUUSD', 'XAGUSD', 'BTCUSD'
        ]
        
        # Ziwox需要小写参数
        self.ziwox_pairs = [pair.lower() for pair in self.watch_currency_pairs]
        
        # Alpha Vantage特殊品种映射
        self.av_special_pairs = {
            'XAUUSD': ('XAU', 'USD'),
            'XAGUSD': ('XAG', 'USD'),
            'BTCUSD': ('BTC', 'USD')
        }
        
        # 重点关注的国家
        self.watch_countries = ['US', 'EU', 'CN', 'JP', 'GB', 'AU', 'CA', 'CH']
        
        # 货币与国家映射
        self.currency_to_country = {
            'USD': 'US', 'EUR': 'EU', 'CNY': 'CN', 'CNH': 'CN',
            'JPY': 'JP', 'GBP': 'GB', 'AUD': 'AU', 
            'CAD': 'CA', 'CHF': 'CH', 'XAU': 'GLOBAL', 
            'XAG': 'GLOBAL', 'BTC': 'CRYPTO'
        }
        
        # 经济日历备用API
        self.fx_calendar_api = "https://www.fxempire.com/api/v1/en/macro/economic-calendar/events"

config = Config()

# ============================================================================
# 模拟数据生成器（备用方案）
# ============================================================================
class MockDataGenerator:
    """模拟宏观经济事件数据生成器"""
    
    def __init__(self):
        # 模拟今日宏观经济事件
        today_str = datetime.now().strftime("%Y-%m-%d")
        self.sample_events = [
            {
                "id": 1,
                "date": today_str,
                "time": "14:30",
                "country": "US",
                "name": "Consumer Price Index (CPI) MoM",
                "forecast": "0.3%",
                "previous": "0.4%",
                "importance": "high",
                "currency": "USD",
                "actual": "0.4%",
                "description": "Monthly change in consumer prices"
            },
            {
                "id": 2,
                "date": today_str,
                "time": "15:00",
                "country": "EU",
                "name": "ZEW Economic Sentiment Index",
                "forecast": "-20.5",
                "previous": "-22.0",
                "importance": "medium",
                "currency": "EUR",
                "actual": "-19.8",
                "description": "Economic sentiment indicator for Europe"
            },
            {
                "id": 3,
                "date": today_str,
                "time": "21:00",
                "country": "US",
                "name": "FOMC Interest Rate Decision",
                "forecast": "5.5%",
                "previous": "5.5%",
                "importance": "high",
                "currency": "USD",
                "actual": "5.5%",
                "description": "Federal Reserve interest rate decision"
            },
            {
                "id": 4,
                "date": today_str,
                "time": "07:50",
                "country": "JP",
                "name": "GDP Growth Rate YoY",
                "forecast": "1.2%",
                "previous": "1.0%",
                "importance": "medium",
                "currency": "JPY",
                "actual": "1.1%",
                "description": "Japan's annual GDP growth rate"
            },
            {
                "id": 5,
                "date": today_str,
                "time": "10:00",
                "country": "CN",
                "name": "Trade Balance",
                "forecast": "75.0B",
                "previous": "72.9B",
                "importance": "medium",
                "currency": "CNY",
                "actual": "77.2B",
                "description": "China's trade balance"
            }
        ]
        
        # 模拟AI分析
        self.sample_analysis = """【AI宏观分析报告】

📅 宏观主线：今日市场焦点集中在美国CPI数据和美联储利率决议上，通胀数据将直接影响市场对美联储政策路径的预期。

📊 市场预期：
- 美国CPI预计环比增长0.3%，若实际数据高于预期可能强化鹰派预期
- 美联储料维持利率不变，但关注鲍威尔新闻发布会措辞变化

💱 货币对展望：
1. EUR/USD (1.1637)：技术面偏空，关注1.1600支撑，上方阻力1.1700
2. USD/JPY (156.73)：受美日利差支撑，关注157.00阻力
3. XAUUSD：受美元走势压制，短期震荡于4180-4220区间
4. BTCUSD：加密货币独立波动，关注93000支撑

⚠️ 风险提示：
1. CPI数据意外高于预期可能引发美元急涨
2. 美联储意外鹰派可能加剧市场波动
3. 贵金属对实际利率变化敏感

🎯 交易策略：
1. 数据公布前保持观望，避免过度暴露
2. 若CPI低于预期，考虑EUR/USD多单，止损1.1580
3. 贵金属等待CPI数据指引，突破4200后顺势操作"""

    def generate_events(self):
        """生成模拟宏观经济事件"""
        logger.info("使用模拟宏观经济事件数据")
        return self.sample_events
    
    def generate_analysis(self):
        """生成模拟AI分析"""
        return self.sample_analysis

mock_gen = MockDataGenerator()

# ============================================================================
# 数据存储
# ============================================================================
class DataStore:
    def __init__(self):
        self.market_signals = []      # Ziwox市场信号
        self.forex_rates = {}         # Alpha Vantage汇率
        self.economic_events = []     # 经济日历事件
        self.daily_analysis = ""      # 每日综合分析
        self.last_updated = None
    
    def update_all(self, signals, rates, events, analysis):
        self.market_signals = signals
        self.forex_rates = rates
        self.economic_events = events
        self.daily_analysis = analysis
        self.last_updated = datetime.now()

store = DataStore()

# ============================================================================
# 模块1：实时市场信号获取（Ziwox）
# ============================================================================
def fetch_market_signals_ziwox():
    """从Ziwox获取市场交易信号数据"""
    if not config.ziwox_api_key:
        logger.error("Ziwox API密钥为空")
        return []
    
    all_signals = []
    
    for pair in config.ziwox_pairs:
        try:
            params = {
                'expn': 'ziwoxuser',
                'apikey': config.ziwox_api_key,
                'apitype': 'json',
                'pair': pair
            }
            
            logger.info(f"正在从Ziwox获取 {pair.upper()} 的市场信号...")
            response = requests.get(
                config.ziwox_api_url,
                params=params,
                headers={'User-Agent': 'MacroEconomicAI/1.0'},
                timeout=10
            )
            
            if response.status_code == 200:
                data_list = response.json()
                
                if isinstance(data_list, list) and len(data_list) > 0:
                    raw_data = data_list[0]
                    
                    # 尝试解析last_price
                    last_price = raw_data.get('Last Price', 'N/A')
                    try:
                        if last_price and last_price != 'N/A':
                            price_float = float(last_price)
                        else:
                            price_float = 0
                    except:
                        price_float = 0
                    
                    signal = {
                        'pair': pair.upper(),
                        'last_price': price_float,
                        'fundamental_bias': raw_data.get('Fundamental Bias', 'Neutral'),
                        'fundamental_power': raw_data.get('Fundamental Power', '--'),
                        'ai_bullish_forecast': raw_data.get('AI Bullish Forecast', '50'),
                        'ai_bearish_forecast': raw_data.get('AI Bearish Forecast', '50'),
                        'd1_trend': raw_data.get('D1 Trend', 'NEUTRAL'),
                        'd1_rsi': raw_data.get('D1 RSI', '50'),
                        'retail_long_ratio': raw_data.get('Retail Long Ratio', '50%'),
                        'retail_short_ratio': raw_data.get('Retail Short Ratio', '50%'),
                        'support_levels': raw_data.get('supports', '').split()[:3],
                        'resistance_levels': raw_data.get('resistance', '').split()[:3],
                        'pivot_points': raw_data.get('pivot', '').split()[:1],
                        'risk_sentiment': raw_data.get('Risk Sentiment', 'Neutral'),
                        'source': 'Ziwox',
                        'fetched_at': datetime.now().isoformat()
                    }
                    all_signals.append(signal)
                    logger.info(f"  成功解析 {pair.upper()} 的市场信号")
                    
            else:
                logger.warning(f"  请求 {pair.upper()} 数据失败，状态码: {response.status_code}")
            
            time.sleep(0.5)
                
        except Exception as e:
            logger.error(f"  获取 {pair} 数据时出错: {e}")
    
    logger.info(f"Ziwox市场信号获取完成，共得到 {len(all_signals)} 个货币对数据")
    return all_signals

# ============================================================================
# 模块2：实时汇率获取（Alpha Vantage + Ziwox补充）
# ============================================================================
def fetch_forex_rates_alpha_vantage(ziwox_signals):
    """从Alpha Vantage获取实时汇率，失败时从Ziwox信号补充"""
    rates = {}
    
    # 首先从Ziwox信号中提取价格作为备用
    ziwox_price_map = {}
    for signal in ziwox_signals:
        pair = signal.get('pair')
        price = signal.get('last_price')
        if pair and price and price > 0:
            ziwox_price_map[pair] = price
    
    # 如果需要使用Alpha Vantage且密钥有效
    if config.alpha_vantage_key and not config.use_mock:
        try:
            logger.info(f"尝试从Alpha Vantage获取 {len(config.watch_currency_pairs)} 个品种汇率...")
            fx = ForeignExchange(key=config.alpha_vantage_key)
            
            # 有限制的获取：只获取主要货币对，避免频率限制
            limited_pairs = config.watch_currency_pairs[:5]  # 只获取前5个
            
            for i, pair in enumerate(limited_pairs):
                try:
                    # 添加随机延迟避免频率限制
                    if i > 0:
                        time.sleep(random.uniform(1, 3))
                    
                    if pair in config.av_special_pairs:
                        from_cur, to_cur = config.av_special_pairs[pair]
                    else:
                        from_cur = pair[:3]
                        to_cur = pair[3:]
                    
                    data, _ = fx.get_currency_exchange_rate(
                        from_currency=from_cur,
                        to_currency=to_cur
                    )
                    
                    if data and '5. Exchange Rate' in data:
                        rates[pair] = {
                            'rate': float(data['5. Exchange Rate']),
                            'bid': data.get('8. Bid Price', data['5. Exchange Rate']),
                            'ask': data.get('9. Ask Price', data['5. Exchange Rate']),
                            'last_refreshed': data.get('6. Last Refreshed', datetime.now().isoformat()),
                            'source': 'Alpha Vantage'
                        }
                        logger.info(f"    ✓ Alpha Vantage 成功获取 {pair}: {rates[pair]['rate']}")
                    else:
                        raise ValueError(f"No rate returned for {pair}")
                        
                except Exception as e:
                    logger.warning(f"    Alpha Vantage 获取 {pair} 失败: {str(e)[:100]}")
                    # 尝试从Ziwox补充
                    if pair in ziwox_price_map:
                        rates[pair] = {
                            'rate': ziwox_price_map[pair],
                            'bid': ziwox_price_map[pair] * 0.999,
                            'ask': ziwox_price_map[pair] * 1.001,
                            'last_refreshed': datetime.now().isoformat(),
                            'source': 'Ziwox (补充)'
                        }
                        logger.info(f"    ↳ 已从Ziwox补充 {pair}: {rates[pair]['rate']}")
                        
        except Exception as e:
            logger.error(f"Alpha Vantage API整体调用失败: {e}")
    
    # 对于所有未获取到的货币对，尝试从Ziwox补充
    for pair in config.watch_currency_pairs:
        if pair not in rates and pair in ziwox_price_map:
            rates[pair] = {
                'rate': ziwox_price_map[pair],
                'bid': ziwox_price_map[pair] * 0.999,
                'ask': ziwox_price_map[pair] * 1.001,
                'last_refreshed': datetime.now().isoformat(),
                'source': 'Ziwox'
            }
            logger.info(f"    ↳ 使用Ziwox价格 {pair}: {rates[pair]['rate']}")
    
    logger.info(f"汇率获取完成，共得到 {len(rates)} 个品种数据")
    return rates

# ============================================================================
# 模块3：经济日历获取（备用API + 模拟数据）
# ============================================================================
def fetch_economic_calendar():
    """获取经济日历数据 - 使用备用API"""
    
    # 如果配置使用模拟数据
    if config.use_mock:
        logger.info("使用模拟经济日历数据模式")
        return mock_gen.generate_events()
    
    try:
        logger.info("尝试获取经济日历数据...")
        
        # 方法1：尝试使用公共API
        today = datetime.now().strftime('%Y-%m-%d')
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        
        # 尝试从FXEmpire获取（公共API，无需密钥）
        try:
            url = f"{config.fx_calendar_api}?dateFrom={today}&dateTo={tomorrow}"
            response = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            })
            
            if response.status_code == 200:
                data = response.json()
                if 'events' in data:
                    events_data = data['events'][:10]  # 只取前10个
                    formatted_events = []
                    
                    for i, event in enumerate(events_data):
                        formatted_events.append({
                            "id": i + 1,
                            "date": event.get('date', today),
                            "time": event.get('time', '00:00'),
                            "country": event.get('country', 'Unknown'),
                            "name": event.get('title', 'Unknown Event'),
                            "forecast": event.get('forecast', 'N/A'),
                            "previous": event.get('previous', 'N/A'),
                            "importance": event.get('importance', 'medium'),
                            "currency": event.get('currency', 'USD'),
                            "actual": event.get('actual', 'N/A'),
                            "description": event.get('description', '')
                        })
                    
                    logger.info(f"成功从FXEmpire获取 {len(formatted_events)} 个经济事件")
                    return formatted_events
        except Exception as e:
            logger.warning(f"FXEmpire API失败: {e}")
        
        # 方法2：如果所有API都失败，使用模拟数据
        logger.info("所有API获取失败，使用模拟数据")
        return mock_gen.generate_events()
        
    except Exception as e:
        logger.error(f"获取经济日历时出错: {e}")
        return mock_gen.generate_events()

# ============================================================================
# 模块4：AI综合分析生成（使用laozhang.ai）
# ============================================================================
def generate_comprehensive_analysis(signals, rates, events):
    """生成综合AI分析：结合市场信号、汇率和宏观事件"""
    
    # 如果AI功能禁用或模拟模式，返回模拟分析
    if not config.enable_ai or config.use_mock:
        return mock_gen.generate_analysis()
    
    # 检查API密钥格式
    api_key = config.openai_api_key
    if not api_key or len(api_key) < 20:
        logger.error("laozhang.ai API密钥无效或过短")
        return mock_gen.generate_analysis()
    
    try:
        # 准备市场概况
        market_summary = []
        for signal in signals[:5]:  # 取前5个主要品种
            pair = signal.get('pair', '')
            rate = rates.get(pair, {}).get('rate', 'N/A') if rates else 'N/A'
            trend = signal.get('d1_trend', 'NEUTRAL')
            bias = signal.get('fundamental_bias', 'Neutral')
            market_summary.append(f"{pair}: {rate} ({trend}, {bias})")
        
        # 准备宏观事件概况
        event_summary = []
        important_events = [e for e in events if e.get('importance') in ['high', 'medium']]
        for event in important_events[:5]:  # 取前5个重要事件
            event_summary.append(f"{event['time']} {event['country']}-{event['name']}: 预测{event['forecast']}, 前值{event['previous']}")
        
        # 构建AI提示词
        prompt = f"""作为资深宏观策略分析师，请基于以下三方面数据提供今日综合分析：

一、市场信号概况（Ziwox）：
{chr(10).join(market_summary)}

二、重要经济事件（今日）：
{chr(10).join(event_summary) if event_summary else "今日无重要经济事件"}

三、监控品种清单：
{', '.join(config.watch_currency_pairs)}

---
请提供一份专业、简洁的每日宏观交易报告，包含：

📅 **宏观主线**：总结今日最重要的经济主题与市场焦点

📊 **市场预期**：基于经济日历事件，分析哪些数据可能超预期/低于预期

💱 **货币对展望**：
- 美元指数：受哪些事件影响，关键位
- EUR/USD：关键驱动因素与技术位
- USD/JPY：关键驱动因素与技术位
- 贵金属（XAUUSD/XAGUSD）：与美元/实际利率关联性
- 加密货币（BTCUSD）：独立驱动因素

⚠️ **风险提示**：今日主要交易风险（数据意外、央行讲话、流动性等）

🎯 **交易策略建议**：1-2条明确的交易思路（品种、方向、关键位）

要求：分析逻辑清晰，有数据支撑，直接服务于今日交易决策。字数控制在400-500字。"""
        
        # 调用laozhang.ai API - 修复认证问题
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # 简化请求体
        request_body = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "你是顶尖的宏观策略分析师，擅长结合宏观经济事件、市场信号和技术分析提供清晰的交易指导。"},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 600,
            "temperature": 0.4
        }
        
        logger.info(f"调用laozhang.ai API, URL: {config.openai_base_url}")
        response = requests.post(
            f"{config.openai_base_url}/chat/completions",
            headers=headers,
            json=request_body,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if 'choices' in result and len(result['choices']) > 0:
                return result['choices'][0]['message']['content']
            else:
                logger.error("laozhang.ai返回格式异常")
                return mock_gen.generate_analysis()
        else:
            logger.error(f"laozhang.ai API错误: {response.status_code}, 响应: {response.text[:200]}")
            return mock_gen.generate_analysis()
            
    except Exception as e:
        logger.error(f"生成综合分析时出错: {e}")
        return mock_gen.generate_analysis()

# ============================================================================
# 定时任务：整合所有数据源
# ============================================================================
scheduler = BackgroundScheduler()

def scheduled_data_update():
    """定时更新所有数据：市场信号 + 汇率 + 经济事件"""
    try:
        logger.info("="*60)
        logger.info(f"开始执行数据更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 1. 获取市场信号数据
        logger.info("获取市场信号数据...")
        signals = fetch_market_signals_ziwox()
        
        # 2. 获取实时汇率数据（使用Ziwox信号作为补充）
        logger.info("获取实时汇率数据...")
        rates = fetch_forex_rates_alpha_vantage(signals)
        
        # 3. 获取经济日历数据
        logger.info("获取经济日历数据...")
        events = fetch_economic_calendar()
        
        # 4. 生成AI综合分析
        logger.info("生成AI综合分析...")
        analysis = generate_comprehensive_analysis(signals, rates, events)
        
        # 5. 存储数据
        store.update_all(signals, rates, events, analysis)
        
        logger.info(f"数据更新完成:")
        logger.info(f"  - 市场信号: {len(signals)} 个")
        logger.info(f"  - 汇率数据: {len(rates)} 个")
        logger.info(f"  - 经济事件: {len(events)} 个")
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"定时任务失败: {e}", exc_info=True)

# 定时任务配置（降低频率避免API限制）
scheduler.add_job(scheduled_data_update, 'interval', minutes=120)  # 每2小时更新
scheduler.add_job(scheduled_data_update, 'cron', hour=8, minute=0)   # 早上8点
scheduler.add_job(scheduled_data_update, 'cron', hour=16, minute=0)  # 下午4点

scheduler.start()

# ============================================================================
# Flask路由
# ============================================================================

@app.route('/')
def index():
    return jsonify({
        "status": "running",
        "service": "宏观经济AI分析工具",
        "version": "2.1 - 修复版",
        "data_sources": ["Ziwox市场信号", "Alpha Vantage汇率 + Ziwox补充", "公共经济日历API"],
        "ai_provider": "laozhang.ai",
        "api_status": {
            "market_signals": "正常",
            "forex_rates": "Alpha Vantage + Ziwox补充",
            "economic_calendar": "公共API + 模拟数据",
            "ai_analysis": "laozhang.ai" + (" (模拟模式)" if config.use_mock else "")
        },
        "last_updated": store.last_updated.isoformat() if store.last_updated else None,
        "endpoints": {
            "status": "/api/status",
            "events": "/api/events/today",
            "market_signals": "/api/market/signals",
            "forex_rates": "/api/forex/rates",
            "analysis": "/api/analysis/daily",
            "refresh": "/api/refresh",
            "overview": "/api/overview"
        }
    })

@app.route('/api/status')
def get_api_status():
    """服务状态检查"""
    return jsonify({
        "status": "healthy",
        "mode": "real-time",
        "ai_enabled": config.enable_ai,
        "ai_provider": "laozhang.ai",
        "use_mock_data": config.use_mock,
        "data_summary": {
            "market_signals": len(store.market_signals),
            "forex_rates": len(store.forex_rates),
            "economic_events": len(store.economic_events)
        },
        "last_updated": store.last_updated.isoformat() if store.last_updated else None,
        "next_update": (datetime.now() + timedelta(minutes=120)).strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/api/events/today')
def get_today_events():
    """获取今日经济日历事件"""
    events = store.economic_events
    if not events:
        scheduled_data_update()
        events = store.economic_events
    
    return jsonify({
        "status": "success",
        "data": events,
        "count": len(events),
        "date": datetime.now().strftime('%Y-%m-%d'),
        "important_events": len([e for e in events if e.get('importance') in ['high', 'medium']]),
        "source": "公共API" if not config.use_mock else "模拟数据"
    })

@app.route('/api/market/signals')
def get_market_signals():
    """获取市场信号数据"""
    signals = store.market_signals
    if not signals:
        scheduled_data_update()
        signals = store.market_signals
    
    return jsonify({
        "status": "success",
        "data": signals,
        "count": len(signals),
        "pairs": config.watch_currency_pairs,
        "source": "Ziwox"
    })

@app.route('/api/forex/rates')
def get_forex_rates():
    """获取实时汇率"""
    rates = store.forex_rates
    
    # 统计数据来源
    sources = {}
    for pair, data in rates.items():
        source = data.get('source', 'Unknown')
        if source in sources:
            sources[source] += 1
        else:
            sources[source] = 1
    
    return jsonify({
        "status": "success",
        "data": rates,
        "count": len(rates),
        "sources": sources
    })

@app.route('/api/analysis/daily')
def get_daily_analysis():
    """获取每日AI综合分析"""
    analysis = store.daily_analysis
    if not analysis:
        scheduled_data_update()
        analysis = store.daily_analysis
    
    return jsonify({
        "status": "success",
        "analysis": analysis,
        "generated_at": datetime.now().isoformat(),
        "ai_provider": "laozhang.ai",
        "is_simulated": config.use_mock or not config.enable_ai
    })

@app.route('/api/overview')
def get_overview():
    """获取综合概览（所有数据）"""
    return jsonify({
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "market_signals": {
            "count": len(store.market_signals),
            "sample": store.market_signals[:3] if store.market_signals else []
        },
        "forex_rates": {
            "count": len(store.forex_rates),
            "sample": {k: store.forex_rates[k] for k in list(store.forex_rates.keys())[:3]} if store.forex_rates else {}
        },
        "economic_events": {
            "count": len(store.economic_events),
            "important": [e for e in store.economic_events if e.get('importance') in ['high', 'medium']][:3]
        },
        "daily_analysis_preview": store.daily_analysis[:200] + "..." if store.daily_analysis and len(store.daily_analysis) > 200 else store.daily_analysis
    })

@app.route('/api/refresh', methods=['POST'])
def refresh_data():
    """手动刷新数据"""
    scheduled_data_update()
    return jsonify({
        "status": "success",
        "message": "数据刷新已触发",
        "timestamp": datetime.now().isoformat(),
        "estimated_completion": (datetime.now() + timedelta(seconds=30)).strftime('%Y-%m-%d %H:%M:%S')
    })

# ============================================================================
# 错误处理
# ============================================================================
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "error": "Not Found",
        "message": "请求的资源不存在",
        "available_routes": [
            "/",
            "/api/status",
            "/api/events/today",
            "/api/market/signals",
            "/api/forex/rates",
            "/api/analysis/daily",
            "/api/overview",
            "/api/refresh"
        ]
    }), 404

# ============================================================================
# 启动应用
# ============================================================================
if __name__ == '__main__':
    logger.info("启动宏观经济AI分析工具 (修复版)...")
    logger.info("="*60)
    logger.info("数据源配置:")
    logger.info(f"  - 市场信号: Ziwox API")
    logger.info(f"  - 实时汇率: Alpha Vantage + Ziwox补充")
    logger.info(f"  - 经济日历: 公共API + 模拟数据")
    logger.info(f"  - AI分析: laozhang.ai")
    logger.info("="*60)
    logger.info(f"监控品种: {config.watch_currency_pairs}")
    logger.info(f"AI功能: {'已启用' if config.enable_ai else '已禁用'}")
    logger.info(f"模拟模式: {'是' if config.use_mock else '否'}")
    
    # 首次启动时获取数据
    try:
        scheduled_data_update()
    except Exception as e:
        logger.error(f"首次数据获取失败: {e}")
    
    # 运行Flask应用
    port = int(os.getenv('PORT', 5000))
    debug_mode = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug_mode,
        use_reloader=False
    )