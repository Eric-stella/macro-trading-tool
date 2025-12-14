"""
宏观经济AI分析工具 - Forex Factory日历版
1. 实时市场信号 (Ziwox)
2. 实时汇率 (Alpha Vantage + Ziwox补充)
3. 财经日历 (Forex Factory JSON API + 模拟备用)
4. AI综合分析 (laozhang.ai)
"""

import os
import json
import logging
import time
import threading
import random
import re
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
import requests
from alpha_vantage.foreignexchange import ForeignExchange

# 创建Flask应用
app = Flask(__name__)
CORS(app)

# 设置日志 - 更详细的格式便于调试
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================================================
# 配置管理
# ============================================================================
class Config:
    def __init__(self):
        # laozhang.ai 配置 (关键：确保密钥正确，不带多余空格)
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

        # Forex Factory JSON API URL
        self.forex_factory_url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

config = Config()

# ============================================================================
# 数据存储
# ============================================================================
class DataStore:
    def __init__(self):
        self.market_signals = []      # Ziwox市场信号
        self.forex_rates = {}         # Alpha Vantage汇率
        self.economic_events = []     # 财经日历事件
        self.daily_analysis = ""      # 每日AI综合分析
        self.last_updated = None
        self.is_updating = False
        self.last_update_error = None

    def update_all(self, signals, rates, events, analysis):
        self.market_signals = signals
        self.forex_rates = rates
        self.economic_events = events
        self.daily_analysis = analysis
        self.last_updated = datetime.now()
        self.is_updating = False
        self.last_update_error = None

    def set_updating(self, updating, error=None):
        self.is_updating = updating
        if error:
            self.last_update_error = error
        elif not updating:
            self.last_update_error = None

store = DataStore()

# ============================================================================
# 模块1：实时市场信号获取 (Ziwox) - 保持不变
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
                timeout=15
            )

            if response.status_code == 200:
                data_list = response.json()

                if isinstance(data_list, list) and len(data_list) > 0:
                    raw_data = data_list[0]

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
# 模块2：实时汇率获取 (Alpha Vantage + Ziwox补充) - 保持不变
# ============================================================================
def fetch_forex_rates_alpha_vantage(ziwox_signals):
    """从Alpha Vantage获取实时汇率，失败时从Ziwox信号补充"""
    rates = {}

    ziwox_price_map = {}
    for signal in ziwox_signals:
        pair = signal.get('pair')
        price = signal.get('last_price')
        if pair and price and price > 0:
            ziwox_price_map[pair] = price

    if config.alpha_vantage_key and not config.use_mock:
        try:
            logger.info(f"尝试从Alpha Vantage获取汇率（限制前5个主要品种）...")
            fx = ForeignExchange(key=config.alpha_vantage_key)

            limited_pairs = config.watch_currency_pairs[:5]

            for i, pair in enumerate(limited_pairs):
                try:
                    if i > 0:
                        delay = random.uniform(12, 15)
                        logger.info(f"  等待 {delay:.1f} 秒以避免API限制...")
                        time.sleep(delay)

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
# 模块3：财经日历获取 (Forex Factory JSON API)
# ============================================================================
def fetch_calendar_forex_factory():
    """
    从Forex Factory JSON API获取本周经济日历数据
    注意：该API限制为5分钟内最多2次请求
    """
    try:
        logger.info("正在从Forex Factory JSON API获取经济日历...")
        url = config.forex_factory_url
        
        # 添加版本参数和时间戳避免缓存
        params = {
            'version': '2e51c1d85c12835c82322cd58bd05d7b',
            '_': int(time.time() * 1000)  # 时间戳避免缓存
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Referer': 'https://www.forexfactory.com/'
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            
            # 验证数据格式
            if isinstance(data, list) and len(data) > 0:
                events = parse_forex_factory_events(data)
                logger.info(f"成功从Forex Factory解析 {len(events)} 个事件")
                return events
            else:
                logger.warning("Forex Factory API返回的数据格式不符或为空列表")
                logger.debug(f"返回数据: {data}")
        else:
            logger.error(f"Forex Factory API请求失败，状态码: {response.status_code}")
            logger.debug(f"响应内容: {response.text[:500]}")
            
    except requests.exceptions.Timeout:
        logger.error("请求Forex Factory API超时")
    except requests.exceptions.ConnectionError:
        logger.error("无法连接到Forex Factory API")
    except json.JSONDecodeError as e:
        logger.error(f"Forex Factory API返回的不是有效JSON: {e}")
        logger.debug(f"响应内容: {response.text[:500] if 'response' in locals() else '无响应'}")
    except Exception as e:
        logger.error(f"获取Forex Factory日历时出错: {str(e)}", exc_info=True)
    
    # 如果失败，回退到模拟数据
    logger.warning("Forex Factory API获取失败，回退到模拟数据")
    return get_simulated_calendar()

def parse_forex_factory_events(raw_events):
    """
    解析Forex Factory返回的原始事件列表
    注意：该API不包含"actual"字段，我们使用"N/A"代替
    """
    events = []
    today = datetime.now().date()
    
    for i, item in enumerate(raw_events):
        # 确保item是字典
        if not isinstance(item, dict):
            continue
        
        try:
            # 提取日期和时间
            date_str = item.get("date", "")
            time_str = item.get("time", "00:00")
            
            # 处理日期 - 只显示今天及之后的事件
            try:
                event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                if event_date < today:
                    continue  # 跳过过去的事件
            except (ValueError, TypeError):
                # 如果日期解析失败，默认使用今天
                date_str = today.strftime("%Y-%m-%d")
            
            # 格式化时间
            time_str = format_time_forex_factory(time_str)
            
            # 重要性映射（Forex Factory使用"impact"字段）
            impact = item.get("impact", "Low")
            importance = map_importance(impact)
            
            # 提取国家/货币信息
            country = item.get("country", "")
            currency = item.get("currency", "")
            
            # 如果没有currency，尝试从country映射
            if not currency and country:
                currency = get_currency_from_country_forex_factory(country)
            
            # 事件名称
            title = item.get("title", item.get("event", "经济事件"))
            
            # 预测值和前值
            forecast = item.get("forecast", "")
            previous = item.get("previous", "")
            
            # 构建事件对象
            event = {
                "id": i + 1,
                "date": date_str,
                "time": time_str,
                "country": get_country_code_forex_factory(country),
                "name": title[:80],
                "forecast": str(forecast)[:30] if forecast not in ["", None] else "N/A",
                "previous": str(previous)[:30] if previous not in ["", None] else "N/A",
                "importance": importance,
                "currency": currency[:3] if currency else "USD",
                "actual": "N/A",  # Forex Factory API不提供实际值
                "description": f"{title} - {item.get('description', '')}"[:150],
                "source": "Forex Factory JSON API"
            }
            
            events.append(event)
            
        except Exception as e:
            logger.warning(f"解析Forex Factory事件 {i} 时出错: {e}")
            continue
    
    # 按日期和时间排序
    events.sort(key=lambda x: (x["date"], x["time"]))
    
    # 限制返回数量
    return events[:50]

def format_time_forex_factory(time_str):
    """格式化Forex Factory时间字符串"""
    if not time_str:
        return "00:00"
    
    time_str = str(time_str).strip()
    
    # 如果已经是HH:MM格式
    if re.match(r'^\d{1,2}:\d{2}$', time_str):
        return time_str
    
    # 如果是HHMM格式（如0930）
    if re.match(r'^\d{3,4}$', time_str):
        if len(time_str) == 3:
            return f"0{time_str[0]}:{time_str[1:]}"
        elif len(time_str) == 4:
            return f"{time_str[:2]}:{time_str[2:]}"
    
    # 尝试提取时间部分
    time_match = re.search(r'(\d{1,2}):?(\d{2})', time_str)
    if time_match:
        hour = time_match.group(1).zfill(2)
        minute = time_match.group(2)
        return f"{hour}:{minute}"
    
    return "00:00"

def map_importance(impact):
    """映射Forex Factory的重要性级别"""
    if not impact:
        return "low"
    
    impact = str(impact).lower()
    
    if impact in ["high", "3", "red"]:
        return "high"
    elif impact in ["medium", "2", "orange", "yellow"]:
        return "medium"
    else:
        return "low"

def get_country_code_forex_factory(country_str):
    """根据Forex Factory的国家字符串获取国家代码"""
    if not country_str:
        return "GL"
    
    country_str = str(country_str).upper()
    
    # Forex Factory通常使用货币代码作为国家标识
    # 尝试从货币代码推断国家
    currency_to_country = {
        "USD": "US", "EUR": "EU", "GBP": "GB", "JPY": "JP",
        "AUD": "AU", "CAD": "CA", "CHF": "CH", "CNY": "CN",
        "NZD": "NZ", "RUB": "RU", "BRL": "BR", "INR": "IN",
        "KRW": "KR", "MXN": "MX", "ZAR": "ZA", "SEK": "SE",
        "NOK": "NO", "DKK": "DK", "TRY": "TR", "PLN": "PL"
    }
    
    if country_str in currency_to_country:
        return currency_to_country[country_str]
    
    # 直接使用前2个字符作为国家代码
    return country_str[:2] if len(country_str) >= 2 else "GL"

def get_currency_from_country_forex_factory(country_str):
    """根据Forex Factory的国家字符串获取货币代码"""
    if not country_str:
        return "USD"
    
    country_str = str(country_str).upper()
    
    # 如果已经是货币代码，直接返回
    if len(country_str) == 3 and country_str.isalpha():
        return country_str
    
    # 国家代码到货币代码的映射
    country_to_currency = {
        "US": "USD", "EU": "EUR", "GB": "GBP", "JP": "JPY",
        "AU": "AUD", "CA": "CAD", "CH": "CHF", "CN": "CNY",
        "NZ": "NZD", "RU": "RUB", "BR": "BRL", "IN": "INR",
        "KR": "KRW", "MX": "MXN", "ZA": "ZAR", "SE": "SEK",
        "NO": "NOK", "DK": "DKK", "TR": "TRY", "PL": "PLN"
    }
    
    country_code = get_country_code_forex_factory(country_str)
    return country_to_currency.get(country_code, "USD")

def get_simulated_calendar():
    """模拟数据生成 - 增强版"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    hour = datetime.now().hour
    
    # 基础事件模板
    base_events = [
        {
            "time": "21:00",
            "country": "US",
            "name": "美联储利率决议",
            "forecast": "5.5%",
            "previous": "5.5%",
            "actual": "待公布" if hour < 21 else "5.5%",
            "importance": "high",
            "currency": "USD"
        },
        {
            "time": "09:30",
            "country": "CN",
            "name": "中国CPI年率",
            "forecast": "0.2%",
            "previous": "0.1%",
            "actual": "0.3%" if hour >= 9 else "待公布",
            "importance": "medium",
            "currency": "CNY"
        },
        {
            "time": "15:00",
            "country": "GB",
            "name": "英国GDP月率",
            "forecast": "0.1%",
            "previous": "0.0%",
            "actual": "待公布" if hour < 15 else "0.2%",
            "importance": "medium",
            "currency": "GBP"
        },
        {
            "time": "20:30",
            "country": "US",
            "name": "美国初请失业金人数",
            "forecast": "210K",
            "previous": "209K",
            "actual": "待公布" if hour < 20 else "211K",
            "importance": "medium",
            "currency": "USD"
        },
        {
            "time": "10:00",
            "country": "EU",
            "name": "欧元区CPI月率",
            "forecast": "0.3%",
            "previous": "0.2%",
            "actual": "待公布" if hour < 10 else "0.4%",
            "importance": "medium",
            "currency": "EUR"
        },
        {
            "time": "07:50",
            "country": "JP",
            "name": "日本贸易帐",
            "forecast": "-0.5T",
            "previous": "-0.6T",
            "actual": "-0.4T" if hour >= 7 else "待公布",
            "importance": "medium",
            "currency": "JPY"
        },
        {
            "time": "21:45",
            "country": "US",
            "name": "美国制造业PMI",
            "forecast": "50.5",
            "previous": "50.0",
            "actual": "待公布" if hour < 21 else "50.3",
            "importance": "medium",
            "currency": "USD"
        },
        {
            "time": "16:30",
            "country": "GB",
            "name": "英国零售销售月率",
            "forecast": "0.3%",
            "previous": "-0.1%",
            "actual": "待公布" if hour < 16 else "0.2%",
            "importance": "medium",
            "currency": "GBP"
        }
    ]
    
    events = []
    for i, event_data in enumerate(base_events):
        event = {
            "id": i + 1,
            "date": today_str,
            "time": event_data["time"],
            "country": event_data["country"],
            "name": event_data["name"],
            "forecast": event_data["forecast"],
            "previous": event_data["previous"],
            "importance": event_data["importance"],
            "currency": event_data["currency"],
            "actual": event_data["actual"],
            "description": event_data["name"],
            "source": "模拟数据"
        }
        events.append(event)
    
    logger.info(f"使用模拟财经日历数据，共 {len(events)} 个事件")
    return events

def fetch_economic_calendar():
    """主函数：获取财经日历，优先使用Forex Factory JSON API"""
    if config.use_mock:
        logger.info("配置为使用模拟数据模式")
        return get_simulated_calendar()
    
    # 优先尝试：Forex Factory JSON API
    events = fetch_calendar_forex_factory()
    if events and len(events) > 0:
        return events
    
    # 备用：模拟数据
    logger.warning("Forex Factory数据抓取失败，使用模拟数据")
    return get_simulated_calendar()

# ============================================================================
# 模块4：AI综合分析生成 (laozhang.ai) - 保持不变
# ============================================================================
def generate_comprehensive_analysis(signals, rates, events):
    """生成综合AI分析：结合市场信号、汇率和宏观事件"""
    if not config.enable_ai:
        logger.info("AI分析功能已被禁用")
        return "【AI分析】AI分析功能当前已禁用。"

    api_key = config.openai_api_key.strip()
    if not api_key or len(api_key) < 30:
        logger.error(f"laozhang.ai API密钥无效或过短。密钥长度: {len(api_key) if api_key else 0}")
        return "【AI分析】错误：API密钥配置无效或过短，请检查环境变量 OPENAI_API_KEY。"

    logger.info(f"开始调用laozhang.ai API，密钥前10位: {api_key[:10]}...")
    try:
        market_summary = []
        for i, signal in enumerate(signals[:6]):
            pair = signal.get('pair', '')
            rate = rates.get(pair, {}).get('rate', 'N/A') if rates else 'N/A'
            trend = signal.get('d1_trend', 'NEUTRAL')
            bias = signal.get('fundamental_bias', 'Neutral')
            market_summary.append(f"{i+1}. {pair}: 汇率{rate} | 趋势{trend} | 偏向{bias}")

        event_summary = []
        important_events = [e for e in events if e.get('importance') in ['high', 'medium']]
        for i, event in enumerate(important_events[:5]):
            event_summary.append(f"{i+1}. {event['time']} {event['country']} {event['name']}: 预测{event['forecast']}, 前值{event['previous']}")

        prompt = f"""你是一位专业的宏观外汇策略分析师。请基于以下实时数据，生成一份简明的今日外汇市场交易分析报告。

【实时市场数据 - 来源Ziwox】
{chr(10).join(market_summary) if market_summary else "暂无市场数据"}

【今日财经日历 - 来源Forex Factory】
{chr(10).join(event_summary) if event_summary else "今日无重要财经事件"}

【分析要求】
请按以下结构组织分析，务必简洁专业，直接服务于日内交易：
1. 市场焦点：今日最重要的1-2个主题
2. 关键货币对分析：EUR/USD, USD/JPY, XAU/USD的今日关键位与方向
3. 风险提示：数据、事件或流动性风险
4. 交易思路：1-2条具体的操作建议（方向、入场区域、止损）

注意：分析请基于以上提供的数据，如数据不全请基于常识推断。字数控制在300-400字。"""

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "MacroEconomicAI/1.0"
        }
        request_body = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "你是一位经验丰富的外汇宏观交易员，擅长结合技术面与基本面给出清晰、直接、可执行的交易分析。回答时避免冗长，突出重点。"},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 600,
            "temperature": 0.4
        }

        logger.info(f"正在请求laozhang.ai API，URL: {config.openai_base_url}")
        response = requests.post(
            f"{config.openai_base_url}/chat/completions",
            headers=headers,
            json=request_body,
            timeout=45
        )

        logger.info(f"laozhang.ai API响应状态码: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            if 'choices' in result and len(result['choices']) > 0:
                ai_content = result['choices'][0]['message']['content']
                logger.info(f"AI分析生成成功，内容长度: {len(ai_content)} 字符")
                return ai_content
            else:
                logger.error(f"laozhang.ai返回格式异常，完整响应: {result}")
                return "【AI分析】错误：API返回格式异常，无法解析分析内容。"
        else:
            error_detail = response.text[:500]
            logger.error(f"laozhang.ai API请求失败！状态码: {response.status_code}, 错误详情: {error_detail}")
            return f"【AI分析】错误：API请求失败 (状态码 {response.status_code})。请检查密钥和网络。"

    except requests.exceptions.Timeout:
        logger.error("laozhang.ai API请求超时")
        return "【AI分析】错误：API请求超时，请稍后重试。"
    except requests.exceptions.ConnectionError:
        logger.error("laozhang.ai API连接错误")
        return "【AI分析】错误：无法连接到AI服务。"
    except Exception as e:
        logger.error(f"生成AI分析时发生未知异常: {str(e)}", exc_info=True)
        return f"【AI分析】错误：生成过程中发生异常 - {str(e)[:100]}"

# ============================================================================
# 核心数据更新函数 - 保持不变
# ============================================================================
def execute_data_update():
    """执行数据更新的核心逻辑"""
    try:
        logger.info("="*60)
        logger.info(f"开始执行数据更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # 1. 获取市场信号数据
        logger.info("阶段1/4: 获取市场信号...")
        signals = fetch_market_signals_ziwox()

        # 2. 获取实时汇率数据
        logger.info("阶段2/4: 获取实时汇率...")
        rates = fetch_forex_rates_alpha_vantage(signals)

        # 3. 获取财经日历数据 (Forex Factory)
        logger.info("阶段3/4: 获取财经日历...")
        events = fetch_economic_calendar()

        # 4. 生成AI综合分析
        logger.info("阶段4/4: 生成AI分析...")
        analysis = generate_comprehensive_analysis(signals, rates, events)

        # 5. 存储数据
        store.update_all(signals, rates, events, analysis)

        logger.info(f"数据更新成功完成:")
        logger.info(f"  - 市场信号: {len(signals)} 个")
        logger.info(f"  - 汇率数据: {len(rates)} 个")
        logger.info(f"  - 财经日历: {len(events)} 个 (来源: {events[0]['source'] if events else '无'})")
        logger.info(f"  - AI分析: 已生成，长度 {len(analysis)} 字符")
        logger.info("="*60)
        return True

    except Exception as e:
        logger.error(f"数据更新失败: {str(e)}", exc_info=True)
        store.set_updating(False, str(e))
        return False

# ============================================================================
# 后台更新线程函数 - 保持不变
# ============================================================================
def background_data_update():
    """在后台线程中执行数据更新"""
    if store.is_updating:
        logger.warning("已有更新任务正在运行，跳过此次请求。")
        return
    store.set_updating(True, None)
    try:
        success = execute_data_update()
        if not success:
            store.set_updating(False, "后台更新执行失败")
    except Exception as e:
        logger.error(f"后台更新线程异常: {e}")
        store.set_updating(False, str(e))

# ============================================================================
# 定时任务调度 - 保持不变
# ============================================================================
scheduler = BackgroundScheduler()

def scheduled_data_update():
    """定时任务包装函数"""
    if store.is_updating:
        logger.info("系统正在手动更新中，跳过此次定时任务。")
        return
    logger.info("定时任务触发数据更新...")
    success = execute_data_update()
    if not success:
        logger.error("定时任务更新失败")

scheduler.add_job(scheduled_data_update, 'interval', minutes=120)
scheduler.add_job(scheduled_data_update, 'cron', hour=8, minute=0)
scheduler.add_job(scheduled_data_update, 'cron', hour=16, minute=0)
scheduler.start()

# ============================================================================
# Flask路由 - 更新版本信息和数据源说明
# ============================================================================
@app.route('/')
def index():
    return jsonify({
        "status": "running",
        "service": "宏观经济AI分析工具 - Forex Factory日历版",
        "version": "2.6",
        "data_sources": {
            "market_signals": "Ziwox",
            "forex_rates": "Alpha Vantage + Ziwox补充",
            "economic_calendar": "Forex Factory JSON API",
            "ai_analysis": "laozhang.ai"
        },
        "update_status": {
            "is_updating": store.is_updating,
            "last_updated": store.last_updated.isoformat() if store.last_updated else None,
            "last_error": store.last_update_error
        },
        "endpoints": {
            "status": "/api/status",
            "events": "/api/events/today",
            "market_signals": "/api/market/signals",
            "forex_rates": "/api/forex/rates",
            "analysis": "/api/analysis/daily",
            "refresh": "/api/refresh",
            "overview": "/api/overview"
        },
        "notes": "Forex Factory API有频率限制(5分钟内最多2次请求)，请勿频繁刷新"
    })

@app.route('/api/status')
def get_api_status():
    return jsonify({
        "status": "healthy",
        "ai_enabled": config.enable_ai,
        "update_status": {
            "is_updating": store.is_updating,
            "last_updated": store.last_updated.isoformat() if store.last_updated else None,
            "last_error": store.last_update_error,
            "data_counts": {
                "market_signals": len(store.market_signals),
                "forex_rates": len(store.forex_rates),
                "economic_events": len(store.economic_events)
            }
        }
    })

@app.route('/api/refresh', methods=['GET', 'POST'])
def refresh_data():
    try:
        logger.info(f"收到手动刷新请求，方法: {request.method}")
        if store.is_updating:
            return jsonify({
                "status": "processing",
                "message": "系统正在更新数据中，请稍后再试",
                "timestamp": datetime.now().isoformat(),
                "last_updated": store.last_updated.isoformat() if store.last_updated else None
            })
        update_thread = threading.Thread(target=background_data_update)
        update_thread.daemon = True
        update_thread.start()
        logger.info("已启动后台更新线程，立即返回响应给客户端")
        return jsonify({
            "status": "success",
            "message": "数据刷新任务已在后台启动",
            "timestamp": datetime.now().isoformat(),
            "note": "请等待后访问 /api/analysis/daily 查看最新AI分析"
        })
    except Exception as e:
        logger.error(f"刷新请求处理出错: {e}")
        return jsonify({
            "status": "error",
            "message": f"刷新请求处理失败: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/api/events/today')
def get_today_events():
    events = store.economic_events
    if not events and not store.is_updating:
        success = execute_data_update()
        events = store.economic_events if success else []
    source = events[0]['source'] if events else "无数据"
    return jsonify({
        "status": "success",
        "data": events,
        "count": len(events),
        "source": source,
        "important_events": len([e for e in events if e.get('importance') in ['high', 'medium']])
    })

@app.route('/api/market/signals')
def get_market_signals():
    signals = store.market_signals
    return jsonify({
        "status": "success",
        "data": signals,
        "count": len(signals),
        "source": "Ziwox"
    })

@app.route('/api/forex/rates')
def get_forex_rates():
    rates = store.forex_rates
    sources = {}
    for pair, data in rates.items():
        source = data.get('source', 'Unknown')
        sources[source] = sources.get(source, 0) + 1
    return jsonify({
        "status": "success",
        "data": rates,
        "count": len(rates),
        "sources": sources
    })

@app.route('/api/analysis/daily')
def get_daily_analysis():
    analysis = store.daily_analysis
    logger.info(f"API /analysis/daily 被访问，返回分析长度: {len(analysis) if analysis else 0}")
    return jsonify({
        "status": "success",
        "analysis": analysis,
        "generated_at": datetime.now().isoformat(),
        "ai_provider": "laozhang.ai",
        "data_sources_used": 3
    })

@app.route('/api/overview')
def get_overview():
    return jsonify({
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "market_signals_count": len(store.market_signals),
        "forex_rates_count": len(store.forex_rates),
        "economic_events_count": len(store.economic_events),
        "has_ai_analysis": bool(store.daily_analysis and len(store.daily_analysis) > 10)
    })

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "error": "Not Found",
        "message": "请求的资源不存在",
        "available_routes": ["/", "/api/status", "/api/events/today", "/api/market/signals",
                           "/api/forex/rates", "/api/analysis/daily", "/api/overview", "/api/refresh"]
    }), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({
        "error": "Method Not Allowed",
        "message": "请求方法不允许",
        "allowed_methods": ['GET', 'POST']
    }), 405

# ============================================================================
# 启动应用
# ============================================================================
if __name__ == '__main__':
    logger.info("="*60)
    logger.info("启动宏观经济AI分析工具 (Forex Factory日历版)")
    logger.info(f"监控品种: {config.watch_currency_pairs}")
    logger.info(f"财经日历源: Forex Factory JSON API")
    logger.info(f"AI分析服务: laozhang.ai (已启用: {config.enable_ai})")
    logger.info(f"模拟模式: {config.use_mock}")
    logger.info("注意: Forex Factory API有频率限制，请勿频繁请求")
    logger.info("="*60)

    # 首次启动时获取数据
    try:
        logger.info("首次启动，正在获取初始数据...")
        success = execute_data_update()
        if success:
            logger.info("初始数据获取成功")
            if store.daily_analysis:
                logger.info(f"初始AI分析已生成，长度: {len(store.daily_analysis)} 字符")
        else:
            logger.warning("初始数据获取失败，但服务已启动")
    except Exception as e:
        logger.error(f"初始数据获取异常: {e}")

    port = int(os.getenv('PORT', 5000))
    app.run(
        host='0.0.0.0',
        port=port,
        debug=False,
        threaded=True
    )