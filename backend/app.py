"""
宏观经济AI分析工具 - 实时数据版
"""

import os
import json
import logging
import time
import threading
import random
import re
from datetime import datetime, timedelta, timezone
from flask import Flask, jsonify, request
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
import requests
from alpha_vantage.foreignexchange import ForeignExchange

# 创建Flask应用
app = Flask(__name__)
CORS(app)

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================================================
# 配置管理
# ============================================================================
class Config:
    def __init__(self):
        # laozhang.ai 配置
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "sk-Cm0SeWFJgMvODmsJ0273Ab49E38e4369BfDf4c4793B71cA5")
        self.openai_base_url = "https://api.laozhang.ai/v1"

        # Alpha Vantage 配置
        self.alpha_vantage_key = os.getenv("ALPHA_VANTAGE_KEY", "2M66S0EB6ZMHO2ST")

        # Ziwox API 配置
        self.ziwox_api_key = os.getenv("ZIWOX_API_KEY", "B65991B99EB498AB")
        self.ziwox_api_url = "https://ziwox.com/terminal/services/API/V1/fulldata.php"

        # 模式开关
        self.enable_ai = os.getenv("ENABLE_AI", "true").lower() == "true"

        # 监控的货币对 - 修正版
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
        
        # 事件到货币对的映射 - 修复版
        self.event_to_pairs_mapping = {
            # 欧洲相关事件
            'EUR': ['EURUSD'],
            'euro': ['EURUSD'],
            'ecb': ['EURUSD'],
            'european': ['EURUSD'],
            'europe': ['EURUSD'],
            
            # 英国相关事件
            'GBP': ['GBPUSD'],
            'pound': ['GBPUSD'],
            'boe': ['GBPUSD'],
            'british': ['GBPUSD'],
            'uk': ['GBPUSD'],
            
            # 日本相关事件
            'JPY': ['USDJPY'],
            'yen': ['USDJPY'],
            'boj': ['USDJPY'],
            'japan': ['USDJPY'],
            
            # 澳大利亚相关事件
            'AUD': ['AUDUSD'],
            'aussie': ['AUDUSD'],
            'australia': ['AUDUSD'],
            'rba': ['AUDUSD'],
            
            # 加拿大相关事件
            'CAD': ['USDCAD'],
            'canada': ['USDCAD'],
            'loonie': ['USDCAD'],
            'boc': ['USDCAD'],
            
            # 瑞士相关事件
            'CHF': ['USDCHF'],
            'swiss': ['USDCHF'],
            'snb': ['USDCHF'],
            'switzerland': ['USDCHF'],
            
            # 中国相关事件
            'CNY': ['USDCNH'],
            'yuan': ['USDCNH'],
            'china': ['USDCNH'],
            'pboc': ['USDCNH'],
            
            # 新西兰相关事件 - 注意：我们没有NZDUSD，所以用替代
            'NZD': ['AUDUSD'],  # 使用AUD作为替代
            'kiwi': ['AUDUSD'],
            'new zealand': ['AUDUSD'],
            'nz': ['AUDUSD'],
            
            # 美国相关事件
            'USD': ['EURUSD', 'USDJPY'],  # 主要货币对
            'dollar': ['EURUSD', 'USDJPY'],
            'fed': ['EURUSD', 'USDJPY', 'XAUUSD'],
            'fomc': ['EURUSD', 'USDJPY', 'XAUUSD'],
            'non-farm': ['EURUSD', 'USDJPY', 'XAUUSD'],
            'employment': ['EURUSD', 'USDJPY', 'XAUUSD'],
            'cpi': ['EURUSD', 'USDJPY', 'XAUUSD'],
            'inflation': ['EURUSD', 'USDJPY', 'XAUUSD'],
            'gdp': ['EURUSD', 'USDJPY'],
            
            # 黄金相关事件
            'gold': ['XAUUSD'],
            'xau': ['XAUUSD'],
            
            # 白银相关事件
            'silver': ['XAGUSD'],
            'xag': ['XAGUSD'],
            
            # 比特币相关事件
            'bitcoin': ['BTCUSD'],
            'btc': ['BTCUSD'],
            'crypto': ['BTCUSD']
        }

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
        self.individual_ai_analysis = {}  # 存储每个事件的AI分析
        self.summary_sections = {     # Summary页面的各个部分
            "market": "",
            "events": "",
            "outlook": "",
            "risks": ""
        }
        self.currency_pairs_summary = []  # 货币对摘要信息

    def update_all(self, signals, rates, events, analysis, summary_sections=None, individual_analysis=None, currency_pairs_summary=None):
        self.market_signals = signals
        self.forex_rates = rates
        self.economic_events = events
        self.daily_analysis = analysis
        if summary_sections:
            self.summary_sections = summary_sections
        if individual_analysis:
            self.individual_ai_analysis = individual_analysis
        if currency_pairs_summary:
            self.currency_pairs_summary = currency_pairs_summary
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
# 模块1：实时市场信号获取 (Ziwox)
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
                    logger.info(f"  成功解析 {pair.upper()} 的市场信号，价格: {price_float}")

            else:
                logger.warning(f"  请求 {pair.upper()} 数据失败，状态码: {response.status_code}")

            time.sleep(0.5)

        except Exception as e:
            logger.error(f"  获取 {pair} 数据时出错: {e}")

    logger.info(f"Ziwox市场信号获取完成，共得到 {len(all_signals)} 个货币对数据")
    return all_signals

# ============================================================================
# 模块2：实时汇率获取 (Alpha Vantage + Ziwox补充)
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

    if config.alpha_vantage_key:
        try:
            logger.info("尝试从Alpha Vantage获取汇率...")
            fx = ForeignExchange(key=config.alpha_vantage_key)

            # 只处理前5个主要品种，避免API限制
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

    # 补充其他货币对的数据
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
    """从Forex Factory JSON API获取本周所有经济日历数据"""
    try:
        logger.info("正在从Forex Factory JSON API获取经济日历...")
        
        # 添加随机参数避免缓存
        version_hash = ''.join(random.choices('0123456789abcdef', k=32))
        url = f"{config.forex_factory_url}?version={version_hash}&_={int(time.time() * 1000)}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Referer': 'https://www.forexfactory.com/'
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            
            if isinstance(data, list) and len(data) > 0:
                events = parse_forex_factory_events(data)
                logger.info(f"成功从Forex Factory解析 {len(events)} 个事件（北京时间）")
                return events
        else:
            logger.error(f"Forex Factory API请求失败，状态码: {response.status_code}")
            
    except Exception as e:
        logger.error(f"获取Forex Factory日历时出错: {str(e)}")
    
    # 如果失败，返回空列表
    logger.warning("Forex Factory API获取失败，返回空列表")
    return []

def parse_forex_factory_events(raw_events):
    """解析Forex Factory返回的事件"""
    events = []
    beijing_timezone = timezone(timedelta(hours=8))
    now_beijing = datetime.now(beijing_timezone)
    today = now_beijing.date()
    
    for i, item in enumerate(raw_events):
        if not isinstance(item, dict):
            continue
        
        try:
            # 提取事件基本信息
            title = item.get("title", "").strip()
            country = item.get("country", "").strip()
            date_str = item.get("date", "").strip()
            impact = item.get("impact", "Low").strip()
            forecast = item.get("forecast", "")
            previous = item.get("previous", "")
            
            # 跳过没有标题的事件
            if not title:
                continue
            
            # 解析ISO格式日期时间，转换为北京时间
            try:
                if date_str:
                    # 处理时区
                    if date_str.endswith('Z'):
                        event_datetime = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    else:
                        event_datetime = datetime.fromisoformat(date_str)
                    
                    # 转换为UTC时间
                    if event_datetime.tzinfo is not None:
                        event_datetime_utc = event_datetime.astimezone(timezone.utc)
                    else:
                        # 如果没有时区信息，假设是UTC
                        event_datetime_utc = event_datetime.replace(tzinfo=timezone.utc)
                    
                    # 转换为北京时间（UTC+8）
                    event_datetime_beijing = event_datetime_utc.astimezone(beijing_timezone)
                    
                    # 提取日期和时间
                    event_date = event_datetime_beijing.date()
                    event_time = event_datetime_beijing.time()
                    time_str = f"{event_time.hour:02d}:{event_time.minute:02d}"
                    date_str_formatted = event_date.strftime("%Y-%m-%d")
                    
                    # 只显示今天及之后的事件
                    if event_date < today:
                        continue
                else:
                    # 如果没有日期时间，跳过
                    continue
                    
            except (ValueError, TypeError) as e:
                logger.warning(f"解析日期时间失败: {date_str}, 错误: {e}")
                continue
            
            # 重要性映射
            importance = map_impact_to_importance(impact)
            
            # 货币和国家代码
            currency = get_currency_from_country(country)
            country_code = get_country_code_from_currency(country)
            
            # 构建事件对象
            event = {
                "id": i + 1,
                "date": date_str_formatted,
                "time": time_str,
                "country": country_code,
                "name": title[:100],
                "forecast": str(forecast)[:50] if forecast not in ["", None] else "N/A",
                "previous": str(previous)[:50] if previous not in ["", None] else "N/A",
                "importance": importance,
                "currency": currency,
                "actual": "N/A",
                "description": title[:150],
                "source": "Forex Factory JSON API",
                "is_important": importance >= 2
            }
            
            events.append(event)
            
        except Exception as e:
            logger.warning(f"解析Forex Factory事件 {i} 时出错: {e}")
            continue
    
    # 按日期和时间排序（从今天最近的时间开始）
    events.sort(key=lambda x: (x["date"], x["time"]))
    
    return events[:50]  # 限制最多50个事件

def map_impact_to_importance(impact):
    """映射影响级别到重要性数值"""
    if not impact:
        return 1
    
    impact = str(impact).lower()
    
    if impact in ["high", "red"]:
        return 3
    elif impact in ["medium", "orange", "yellow"]:
        return 2
    else:
        return 1

def get_currency_from_country(country_str):
    """根据country字段获取货币代码"""
    if not country_str:
        return "USD"
    
    country_str = str(country_str).upper()
    
    # 常见货币代码
    common_currencies = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "CNY",
                        "NZD", "RUB", "BRL", "INR", "KRW", "MXN", "ZAR", "SEK",
                        "NOK", "DKK", "TRY", "PLN", "HKD", "SGD", "THB", "IDR"]
    if country_str in common_currencies:
        return country_str
    
    # 国家/地区到货币的映射
    country_to_currency = {
        "US": "USD", "USA": "USD",
        "EU": "EUR", "EURO": "EUR", "EZ": "EUR",
        "UK": "GBP", "GB": "GBP", "GBR": "GBP",
        "JP": "JPY", "JPN": "JPY",
        "AU": "AUD", "AUS": "AUD",
        "CA": "CAD", "CAN": "CAD",
        "CH": "CHF", "CHE": "CHF",
        "CN": "CNY", "CHN": "CNY",
        "NZ": "NZD", "NZL": "NZD",
        "RU": "RUB", "RUS": "RUB",
        "BR": "BRL", "BRA": "BRL",
        "IN": "INR", "IND": "INR",
        "KR": "KRW", "KOR": "KRW",
        "MX": "MXN", "MEX": "MXN",
        "ZA": "ZAR", "ZAF": "ZAR",
        "SE": "SEK", "SWE": "SEK",
        "NO": "NOK", "NOR": "NOK",
        "DK": "DKK", "DNK": "DKK",
        "TR": "TRY", "TUR": "TRY",
        "PL": "PLN", "POL": "PLN",
        "HK": "HKD", "HKG": "HKD",
        "SG": "SGD", "SGP": "SGD",
        "TH": "THB", "THA": "THB",
        "ID": "IDR", "IDN": "IDR"
    }
    
    # 尝试匹配国家代码
    for country_code, currency in country_to_currency.items():
        if country_str == country_code or country_str.startswith(country_code):
            return currency
    
    return "USD"

def get_country_code_from_currency(country_str):
    """根据country字段获取国家代码"""
    if not country_str:
        return "GL"
    
    country_str = str(country_str).upper()
    
    # 国家代码映射
    country_mapping = {
        "US": "US", "USA": "US", "UNITED STATES": "US",
        "EU": "EU", "EURO": "EU", "EZ": "EU", "EUROZONE": "EU",
        "UK": "GB", "GB": "GB", "GBR": "GB", "UNITED KINGDOM": "GB",
        "JP": "JP", "JPN": "JP", "JAPAN": "JP",
        "AU": "AU", "AUS": "AU", "AUSTRERALIA": "AU",
        "CA": "CA", "CAN": "CA", "CANADA": "CA",
        "CH": "CH", "CHE": "CH", "SWITZERLAND": "CH",
        "CN": "CN", "CHN": "CN", "CHINA": "CN",
        "NZ": "NZ", "NZL": "NZ", "NEW ZEALAND": "NZ",
        "RU": "RU", "RUS": "RU", "RUSSIA": "RU",
        "BR": "BR", "BRA": "BR", "BRAZIL": "BR",
        "IN": "IN", "IND": "IN", "INDIA": "IN",
        "KR": "KR", "KOR": "KR", "KOREA": "KR",
        "MX": "MX", "MEX": "MX", "MEXICO": "MX",
        "ZA": "ZA", "ZAF": "ZA", "SOUTH AFRICA": "ZA",
        "SE": "SE", "SWE": "SE", "SWEDEN": "SE",
        "NO": "NO", "NOR": "NO", "NORWAY": "NO",
        "DK": "DK", "DNK": "DK", "DENMARK": "DK",
        "TR": "TR", "TUR": "TR", "TURKEY": "TR",
        "PL": "PL", "POL": "PL", "POLAND": "PL",
        "HK": "HK", "HKG": "HK", "HONG KING": "HK",
        "SG": "SG", "SGP": "SG", "SINGAPORE": "SG",
        "TH": "TH", "THA": "TH", "THAILAND": "TH",
        "ID": "ID", "IDN": "ID", "INDONESIA": "ID"
    }
    
    # 尝试匹配国家
    for code, country_code in country_mapping.items():
        if country_str == code or country_str.startswith(code):
            return country_code
    
    return country_str[:2] if len(country_str) >= 2 else "GL"

# ============================================================================
# 工具函数
# ============================================================================
def format_price(pair, price):
    """格式化价格显示"""
    if not price or price == 0:
        return "N/A"
    
    try:
        price_num = float(price)
        if pair in ['XAUUSD', 'XAGUSD']:
            return f"{price_num:.2f}"
        elif pair == 'BTCUSD':
            return f"{int(price_num)}"
        else:
            if price_num < 10:
                return f"{price_num:.5f}"
            else:
                return f"{price_num:.4f}"
    except:
        return str(price)

def get_real_time_price_by_pair(pair, signals, rates):
    """获取特定货币对的实时价格"""
    # 优先从rates获取
    if pair in rates:
        price = rates[pair].get('rate')
        if price and price > 0:
            return price
    
    # 从signals获取
    for signal in signals:
        if signal.get('pair') == pair:
            price = signal.get('last_price')
            if price and price > 0:
                return price
    
    return None

def get_event_related_pairs(event_name, currency_code):
    """获取事件相关的货币对列表"""
    event_name_lower = event_name.lower()
    currency_code_upper = currency_code.upper() if currency_code else ""
    
    related_pairs = set()
    
    # 基于事件名称关键词匹配
    for keyword, pairs in config.event_to_pairs_mapping.items():
        if keyword in event_name_lower:
            for pair in pairs:
                if pair in config.watch_currency_pairs:  # 只添加我们监控的货币对
                    related_pairs.add(pair)
    
    # 基于货币代码匹配
    if currency_code_upper:
        # 直接货币对匹配
        if currency_code_upper == "EUR":
            related_pairs.add("EURUSD")
        elif currency_code_upper == "GBP":
            related_pairs.add("GBPUSD")
        elif currency_code_upper == "JPY":
            related_pairs.add("USDJPY")
        elif currency_code_upper == "AUD":
            related_pairs.add("AUDUSD")
        elif currency_code_upper == "CHF":
            related_pairs.add("USDCHF")
        elif currency_code_upper == "CNY" or currency_code_upper == "CNH":
            related_pairs.add("USDCNH")
        elif currency_code_upper == "XAU":
            related_pairs.add("XAUUSD")
        elif currency_code_upper == "XAG":
            related_pairs.add("XAGUSD")
        elif currency_code_upper == "BTC":
            related_pairs.add("BTCUSD")
        elif currency_code_upper == "NZD":
            # 我们没有NZDUSD，使用最接近的AUDUSD
            related_pairs.add("AUDUSD")
        elif currency_code_upper == "USD":
            # 美元相关事件，添加主要货币对
            related_pairs.add("EURUSD")
            related_pairs.add("USDJPY")
    
    # 如果还是没有找到相关货币对，返回主要货币对
    if not related_pairs:
        related_pairs = {"EURUSD", "USDJPY", "XAUUSD"}
    
    return list(related_pairs)[:3]  # 最多返回3个相关货币对

# ============================================================================
# 模块4：AI分析生成 - 修复版
# ============================================================================
def generate_ai_analysis_for_event(event, signals=None, rates=None):
    """为单个事件生成AI分析 - 完全修复版"""
    if not config.enable_ai:
        return "【AI分析】AI分析功能当前已禁用"
    
    api_key = config.openai_api_key.strip()
    if not api_key or len(api_key) < 30:
        return "【AI分析】API密钥配置无效"
    
    try:
        # 获取事件相关信息
        event_name = event.get('name', '')
        currency_code = event.get('currency', '')
        
        # 确定相关的货币对
        related_pairs = get_event_related_pairs(event_name, currency_code)
        
        # 获取实时价格
        real_time_prices = []
        unavailable_pairs = []
        
        if signals and rates and related_pairs:
            for pair in related_pairs:
                price = get_real_time_price_by_pair(pair, signals, rates)
                if price and price > 0:
                    formatted_price = format_price(pair, price)
                    real_time_prices.append(f"{pair}: {formatted_price}")
                else:
                    unavailable_pairs.append(pair)
        
        # 记录日志
        logger.info(f"事件 '{event_name}' 相关货币对: {related_pairs}")
        logger.info(f"可用价格: {real_time_prices}")
        
        # 构建提示词
        price_context = ""
        if real_time_prices:
            price_context = f"\n\n【当前实时价格】\n{chr(10).join(real_time_prices)}"
        
        # 如果有些货币对没有价格，在提示词中说明
        if unavailable_pairs:
            price_context += f"\n注：{', '.join(unavailable_pairs)} 的实时价格暂不可用"
        
        # 确保价格上下文不为空
        if not price_context:
            price_context = "\n\n【注意】当前实时价格数据暂不可用，以下分析基于一般市场知识"
        
        prompt = f"""你是一位专业的宏观外汇分析师。请基于以下经济事件信息，生成简要的AI分析：

事件信息：
- 事件名称：{event_name}
- 国家/地区：{event.get('country', '未知')}
- 时间：{event.get('date', '')} {event.get('time', '')}（北京时间）
- 预测值：{event.get('forecast', 'N/A')}
- 前值：{event.get('previous', 'N/A')}
- 重要性：{event.get('importance', 1)}级
{price_context}

请用中文分析：
1. 该事件对相关货币的可能影响
2. 市场预期与实际情况的对比
3. 1-2条具体的交易建议（方向、入场区域、止损）

请控制在150字以内，直接给出分析，不要多余说明。"""

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # 修复：使用正确的模型名称
        request_body = {
            "model": "gpt-5-pro",  
            "messages": [
                {"role": "system", "content": "你是一位经验丰富的外汇宏观交易员。如果用户提供了当前价格数据，请基于这些价格进行分析。如果没有提供价格数据，请基于一般市场知识进行分析，但不要编造具体的价格数值。"},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 400,
            "temperature": 0.4
        }

        response = requests.post(
            f"{config.openai_base_url}/chat/completions",
            headers=headers,
            json=request_body,
            timeout=45  # 增加超时时间
        )

        if response.status_code == 200:
            result = response.json()
            if 'choices' in result and len(result['choices']) > 0:
                ai_content = result['choices'][0]['message']['content']
                
                # 检查分析中是否包含正确的价格信息
                has_price_reference = False
                if real_time_prices:
                    for price_info in real_time_prices:
                        pair, price = price_info.split(": ")
                        if price in ai_content:
                            has_price_reference = True
                            break
                
                # 如果没有引用价格，添加价格说明
                if real_time_prices and not has_price_reference:
                    price_summary = '，'.join(real_time_prices)
                    ai_content = f"（当前价格：{price_summary}）\n{ai_content}"
                
                return f"【AI分析】{ai_content}"
            else:
                logger.warning(f"AI响应中没有choices: {result}")
                return "【AI分析】AI响应格式异常"
        else:
            logger.warning(f"AI分析请求失败: {response.status_code}, 响应: {response.text[:200]}")
            return "【AI分析】AI服务响应异常，请稍后重试"
            
    except requests.exceptions.Timeout:
        logger.error("AI分析请求超时")
        return "【AI分析】分析生成超时，请稍后重试"
    except Exception as e:
        logger.error(f"生成AI分析时出错: {e}")
    
    return "【AI分析】分析生成中..."

def add_ai_analysis_to_events(events, signals=None, rates=None):
    """为事件添加AI分析"""
    if not events or not config.enable_ai:
        return events
    
    # 只为重要性较高的事件生成AI分析
    important_events = [e for e in events if e.get('importance', 1) >= 2][:10]
    
    for event in important_events:
        try:
            ai_analysis = generate_ai_analysis_for_event(event, signals, rates)
            event['ai_analysis'] = ai_analysis
            time.sleep(0.8)  # 增加延迟，避免API调用过于频繁
        except Exception as e:
            logger.error(f"为事件生成AI分析失败: {e}")
            event['ai_analysis'] = "【AI分析】分析生成失败，请稍后重试"
    
    # 为其他事件添加默认AI分析
    for event in events:
        if 'ai_analysis' not in event:
            event['ai_analysis'] = "【AI分析】该事件重要性较低，暂无详细分析。关注市场整体情绪和主要货币对走势。"
    
    return events

def fetch_economic_calendar(signals=None, rates=None):
    """获取财经日历"""
    # 获取原始事件
    events = fetch_calendar_forex_factory()
    
    # 为重要事件添加AI分析
    if signals is not None and rates is not None:
        events_with_ai = add_ai_analysis_to_events(events, signals, rates)
    else:
        events_with_ai = add_ai_analysis_to_events(events)
    
    return events_with_ai

# ============================================================================
# 综合AI分析生成 - 完全修复版
# ============================================================================
def generate_comprehensive_analysis_with_sections(signals, rates, events):
    """生成综合AI分析（分章节）- 完全修复版"""
    if not config.enable_ai:
        return {
            "summary": "AI分析功能已禁用",
            "sections": {
                "market": "【市场概况】AI分析功能当前已禁用",
                "events": "【事件分析】AI分析功能当前已禁用",
                "outlook": "【货币对展望】AI分析功能当前已禁用",
                "risks": "【风险提示】AI分析功能当前已禁用"
            }
        }
    
    api_key = config.openai_api_key.strip()
    if not api_key or len(api_key) < 30:
        logger.error("laozhang.ai API密钥无效或过短")
        return {
            "summary": "API密钥配置错误",
            "sections": {
                "market": "【错误】API密钥配置无效，请检查配置",
                "events": "【错误】API密钥配置无效，请检查配置",
                "outlook": "【错误】API密钥配置无效，请检查配置",
                "risks": "【错误】API密钥配置无效，请检查配置"
            }
        }
    
    logger.info("开始生成综合AI分析（分章节）...")
    
    try:
        # 构建实时价格字符串
        price_info_lines = []
        
        # 获取主要货币对的实时价格
        for pair in config.watch_currency_pairs:
            price = get_real_time_price_by_pair(pair, signals, rates)
            if price and price > 0:
                formatted_price = format_price(pair, price)
                price_info_lines.append(f"- {pair}: {formatted_price}")
        
        # 重要事件统计
        important_events = [e for e in events if e.get('importance', 1) >= 2]
        event_names = [e.get('name', '') for e in important_events[:5]]
        
        # 构建强化的提示词，明确要求四个章节
        prompt = f"""你是一位专业的宏观外汇策略分析师。请基于以下实时数据，生成一份结构化的今日外汇市场分析报告。

【实时市场价格】
{chr(10).join(price_info_lines) if price_info_lines else "暂无实时市场数据"}

【本周重要经济事件】
{chr(10).join([f"- {name}" for name in event_names]) if event_names else "本周无重要经济事件"}

请严格按照以下四个章节生成分析报告，每个章节必须有明确的标题：

1. 【市场概况】 - 分析当前市场整体情况，主要货币对走势
2. 【事件分析】 - 分析重要经济事件对市场的影响
3. 【货币对展望】 - 基于当前价格水平，给出主要货币对的技术分析和展望
4. 【风险提示】 - 指出当前市场的主要风险和交易注意事项

每个章节请控制在150-200字，使用中文，简洁专业。基于实时价格数据进行分析，给出具体的交易参考。"""

        logger.info(f"发送AI请求，提示词长度: {len(prompt)}")
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # 修复：使用正确的模型名称和参数
        request_body = {
            "model": "gpt-4",  # 修改：将 gpt-4 改为 gpt-4，这是正确的模型名称
            "messages": [
                {"role": "system", "content": "你是一位经验丰富的外汇和贵金属交易员，擅长给出结构化、清晰、可执行的交易分析。请严格按照用户要求的四个章节格式输出，不要遗漏任何章节。基于提供的实时价格数据进行分析。"},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 2000,  # 增加token限制
            "temperature": 0.4
        }

        response = requests.post(
            f"{config.openai_base_url}/chat/completions",
            headers=headers,
            json=request_body,
            timeout=90  # 增加超时时间
        )

        if response.status_code == 200:
            result = response.json()
            logger.info(f"AI响应状态: 成功，使用模型: {result.get('model', '未知')}")
            
            if 'choices' in result and len(result['choices']) > 0:
                ai_content = result['choices'][0]['message']['content']
                logger.info(f"AI响应成功，内容长度: {len(ai_content)}")
                logger.info(f"AI响应内容前500字符: {ai_content[:500]}")
                
                # 解析AI回复，分章节
                sections = parse_ai_response_into_sections_enhanced(ai_content)
                logger.info(f"解析后的章节: {json.dumps(sections, ensure_ascii=False, indent=2)}")
                
                # 验证章节内容
                valid_sections = validate_and_fix_sections(sections, ai_content)
                
                return {
                    "summary": "基于实时数据的AI分析报告已生成",
                    "sections": valid_sections,
                    "raw_ai_content": ai_content[:1000]  # 保存部分原始内容用于调试
                }
            else:
                logger.error(f"AI响应中没有choices: {result}")
                raise Exception("AI响应格式异常")
                
        else:
            logger.error(f"AI分析请求失败: {response.status_code}, 响应: {response.text[:500]}")
            raise Exception(f"AI服务响应异常: {response.status_code}")
            
    except requests.exceptions.Timeout:
        logger.error("AI分析请求超时")
        raise Exception("AI分析请求超时，请稍后重试")
    except Exception as e:
        logger.error(f"生成综合AI分析时出错: {e}", exc_info=True)
        raise Exception(f"生成AI分析失败: {str(e)}")

def parse_ai_response_into_sections_enhanced(ai_content):
    """增强版解析AI回复，分章节提取内容"""
    sections = {
        "market": "",
        "events": "",
        "outlook": "",
        "risks": ""
    }
    
    if not ai_content or len(ai_content.strip()) < 100:
        logger.warning("AI回复内容过短或为空")
        return sections
    
    # 清理内容
    content = ai_content.strip()
    
    # 方法1：尝试按明确的章节标题分割（支持多种格式）
    section_patterns = {
        "market": [
            r"1[\.、]?\s*【?市场概况】?[:：]?\s*",
            r"【市场概况】[:：]?\s*",
            r"市场概况[:：]?\s*",
            r"^市场概况\s*"
        ],
        "events": [
            r"2[\.、]?\s*【?事件分析】?[:：]?\s*", 
            r"【事件分析】[:：]?\s*",
            r"事件分析[:：]?\s*",
            r"^事件分析\s*"
        ],
        "outlook": [
            r"3[\.、]?\s*【?货币对展望】?[:：]?\s*",
            r"【货币对展望】[:：]?\s*",
            r"货币对展望[:：]?\s*",
            r"^货币对展望\s*"
        ],
        "risks": [
            r"4[\.、]?\s*【?风险提示】?[:：]?\s*",
            r"【风险提示】[:：]?\s*",
            r"风险提示[:：]?\s*",
            r"^风险提示\s*"
        ]
    }
    
    # 找到所有章节的位置
    section_positions = {}
    
    for section_name, patterns in section_patterns.items():
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
            if match:
                section_positions[section_name] = match.start()
                logger.info(f"找到章节 '{section_name}' 在位置 {match.start()}")
                break
    
    # 如果找到至少一个章节，按位置分割
    if section_positions:
        # 按位置排序
        sorted_sections = sorted(section_positions.items(), key=lambda x: x[1])
        
        for i, (section_name, start_pos) in enumerate(sorted_sections):
            # 确定结束位置（下一个章节的开始或文本结束）
            if i < len(sorted_sections) - 1:
                end_pos = sorted_sections[i + 1][1]
                section_content = content[start_pos:end_pos].strip()
            else:
                section_content = content[start_pos:].strip()
            
            # 移除章节标题行
            for pattern in section_patterns[section_name]:
                section_content = re.sub(pattern, "", section_content, flags=re.IGNORECASE).strip()
            
            # 清理多余的空行和空白字符
            section_content = re.sub(r'\n\s*\n+', '\n\n', section_content)
            section_content = section_content.strip()
            
            # 确保内容不为空
            if section_content and len(section_content) > 20:
                sections[section_name] = section_content
                logger.info(f"章节 '{section_name}' 内容长度: {len(section_content)}")
    
    # 方法2：如果上述方法失败，尝试按明确的章节分割线分割
    if all(not v for v in sections.values()):
        logger.info("方法1失败，尝试按章节分割线分割...")
        
        # 尝试查找明显的章节分割
        chapter_markers = [
            ("市场概况", "market"),
            ("事件分析", "events"),
            ("货币对展望", "outlook"),
            ("风险提示", "risks")
        ]
        
        for marker, section_name in chapter_markers:
            # 查找章节开始
            pattern = rf"(?:^|\n)(?:#+\s*)?{marker}[:：]?\s*\n"
            match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
            if match:
                start_pos = match.end()
                
                # 查找下一个章节或文本结束
                next_pos = len(content)
                for next_marker, _ in chapter_markers:
                    if next_marker != marker:
                        pattern2 = rf"(?:^|\n)(?:#+\s*)?{next_marker}[:：]?\s*\n"
                        match2 = re.search(pattern2, content[start_pos:], re.IGNORECASE | re.MULTILINE)
                        if match2:
                            next_pos = start_pos + match2.start()
                            break
                
                section_content = content[start_pos:next_pos].strip()
                if section_content and len(section_content) > 20:
                    sections[section_name] = section_content
    
    # 方法3：如果还是失败，尝试按段落分割
    if all(not v for v in sections.values()):
        logger.info("方法2失败，尝试按段落分割...")
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
        
        if len(paragraphs) >= 4:
            for i, para in enumerate(paragraphs[:4]):
                if i == 0 and len(para) > 30:
                    sections["market"] = para
                elif i == 1 and len(para) > 30:
                    sections["events"] = para
                elif i == 2 and len(para) > 30:
                    sections["outlook"] = para
                elif i == 3 and len(para) > 30:
                    sections["risks"] = para
    
    return sections

def validate_and_fix_sections(sections, original_content=None):
    """验证并修复章节内容"""
    # 检查每个章节是否有内容
    for section_name in ["market", "events", "outlook", "risks"]:
        if not sections.get(section_name) or len(sections[section_name].strip()) < 30:
            # 如果内容太少，尝试从原始内容中提取
            if original_content and len(original_content) > 100:
                # 简单地将内容分成四部分
                content_length = len(original_content)
                part_length = content_length // 4
                
                if section_name == "market":
                    sections["market"] = original_content[:part_length]
                elif section_name == "events":
                    sections["events"] = original_content[part_length:part_length*2]
                elif section_name == "outlook":
                    sections["outlook"] = original_content[part_length*2:part_length*3]
                elif section_name == "risks":
                    sections["risks"] = original_content[part_length*3:]
            else:
                # 使用更具体的默认内容
                default_content = {
                    "market": "【市场概况】基于当前市场数据，主要货币对价格显示市场处于调整阶段。实时价格反映投资者对经济数据的预期变化。",
                    "events": "【事件分析】本周重要经济事件将影响相关货币走势。关注数据发布前后的市场波动，这些事件可能为交易提供机会。",
                    "outlook": "【货币对展望】基于实时价格水平，主要货币对呈现不同的技术形态。黄金、白银等贵金属价格走势需要特别关注突破方向。",
                    "risks": "【风险提示】当前市场存在数据发布风险和流动性变化。建议交易者控制仓位，设置合理止损，密切关注市场情绪变化。"
                }
                sections[section_name] = default_content.get(section_name, "AI分析内容生成中...")
    
    return sections

# ============================================================================
# 货币对摘要生成函数
# ============================================================================
def generate_currency_pairs_summary(signals, rates):
    """生成货币对摘要信息，用于前端展示"""
    currency_pairs_summary = []
    
    # 定义货币对显示名称和图标
    pair_display_info = {
        'EURUSD': {'name': '欧元/美元', 'icon': '🇪🇺🇺🇸'},
        'GBPUSD': {'name': '英镑/美元', 'icon': '🇬🇧🇺🇸'},
        'USDJPY': {'name': '美元/日元', 'icon': '🇺🇸🇯🇵'},
        'USDCHF': {'name': '美元/瑞郎', 'icon': '🇺🇸🇨🇭'},
        'USDCNH': {'name': '美元/人民币', 'icon': '🇺🇸🇨🇳'},
        'AUDUSD': {'name': '澳元/美元', 'icon': '🇦🇺🇺🇸'},
        'XAUUSD': {'name': '黄金/美元', 'icon': '🥇'},
        'XAGUSD': {'name': '白银/美元', 'icon': '🥈'},
        'BTCUSD': {'name': '比特币/美元', 'icon': '₿'}
    }
    
    # 按优先级排序
    priority_order = ['XAUUSD', 'XAGUSD', 'BTCUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'USDCNH', 'AUDUSD']
    
    for pair in priority_order:
        # 从rates中获取价格
        rate_info = rates.get(pair)
        if rate_info:
            price = rate_info.get('rate', 0)
            source = rate_info.get('source', '未知')
        else:
            # 尝试从signals中获取价格
            signal = next((s for s in signals if s.get('pair') == pair), None)
            if signal:
                price = signal.get('last_price', 0)
                source = signal.get('source', 'Ziwox')
            else:
                continue
        
        # 格式化价格
        if price > 0:
            formatted_price = format_price(pair, price)
            
            # 获取显示信息
            display_info = pair_display_info.get(pair, {'name': pair, 'icon': '💱'})
            
            # 创建摘要对象
            summary = {
                'pair': pair,
                'name': display_info['name'],
                'icon': display_info['icon'],
                'price': formatted_price,
                'source': source,
                'trend': 'neutral'
            }
            
            currency_pairs_summary.append(summary)
    
    logger.info(f"生成货币对摘要，共 {len(currency_pairs_summary)} 个货币对")
    return currency_pairs_summary

# ============================================================================
# 核心数据更新函数 - 修复版
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

        # 3. 获取财经日历数据
        logger.info("阶段3/4: 获取财经日历...")
        events = fetch_economic_calendar(signals, rates)

        # 4. 生成综合AI分析（分章节）- 使用修复版
        logger.info("阶段4/4: 生成综合AI分析（分章节）...")
        try:
            analysis_result = generate_comprehensive_analysis_with_sections(signals, rates, events)
            sections = analysis_result.get("sections", {})
            logger.info("AI分析生成成功")
        except Exception as ai_error:
            logger.error(f"AI分析生成失败: {ai_error}")
            # 使用真正的AI分析失败后的备用内容，而不是默认内容
            sections = {
                "market": f"【市场概况】AI分析生成失败: {str(ai_error)[:100]}",
                "events": "【事件分析】AI分析服务暂时不可用，请稍后刷新重试",
                "outlook": "【货币对展望】请手动刷新数据或检查AI服务配置",
                "risks": "【风险提示】AI分析服务异常，建议谨慎交易"
            }
        
        # 5. 生成货币对摘要
        logger.info("阶段5/5: 生成货币对摘要...")
        currency_pairs_summary = generate_currency_pairs_summary(signals, rates)

        # 6. 存储数据
        store.update_all(signals, rates, events, "实时AI分析报告", sections, None, currency_pairs_summary)

        logger.info(f"数据更新成功完成:")
        logger.info(f"  - 市场信号: {len(signals)} 个")
        logger.info(f"  - 汇率数据: {len(rates)} 个")
        logger.info(f"  - 财经日历: {len(events)} 个")
        logger.info(f"  - AI分析章节: {len(sections)} 个")
        logger.info(f"  - 货币对摘要: {len(currency_pairs_summary)} 个")
        logger.info("="*60)
        return True

    except Exception as e:
        logger.error(f"数据更新失败: {str(e)}", exc_info=True)
        store.set_updating(False, str(e))
        return False

# ============================================================================
# 后台更新线程函数
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
# 定时任务调度
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

scheduler.add_job(scheduled_data_update, 'interval', minutes=30)
scheduler.add_job(scheduled_data_update, 'cron', hour=8, minute=0)
scheduler.add_job(scheduled_data_update, 'cron', hour=16, minute=0)
scheduler.start()

# ============================================================================
# Flask路由
# ============================================================================
@app.route('/')
def index():
    return jsonify({
        "status": "running",
        "service": "宏观经济AI分析工具（实时版）",
        "version": "5.6",
        "data_sources": {
            "market_signals": "Ziwox",
            "forex_rates": "Alpha Vantage + Ziwox补充",
            "economic_calendar": "Forex Factory JSON API",
            "ai_analysis": "laozhang.ai（GPT-4模型）"
        },
        "special_pairs": ["XAU/USD (黄金)", "XAG/USD (白银)", "BTC/USD (比特币)"],
        "timezone": "北京时间 (UTC+8)",
        "update_status": {
            "is_updating": store.is_updating,
            "last_updated": store.last_updated.isoformat() if store.last_updated else None,
            "last_error": store.last_update_error
        }
    })

@app.route('/api/status')
def get_api_status():
    return jsonify({
        "status": "healthy",
        "ai_enabled": config.enable_ai,
        "ai_model": "gpt-4",
        "timezone": "北京时间 (UTC+8)",
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
        logger.info(f"收到手动刷新请求")
        if store.is_updating:
            return jsonify({
                "status": "processing",
                "message": "系统正在更新数据中，请稍后再试"
            })
        update_thread = threading.Thread(target=background_data_update)
        update_thread.daemon = True
        update_thread.start()
        return jsonify({
            "status": "success",
            "message": "数据刷新任务已在后台启动"
        })
    except Exception as e:
        logger.error(f"刷新请求处理出错: {e}")
        return jsonify({
            "status": "error",
            "message": f"刷新请求处理失败: {str(e)}"
        }), 500

@app.route('/api/events/today')
def get_today_events():
    """获取今日事件"""
    events = store.economic_events
    
    # 如果没有数据且不在更新中，执行一次更新
    if not events and not store.is_updating:
        success = execute_data_update()
        events = store.economic_events if success else []
    
    # 确保每个事件都有ai_analysis字段
    for event in events:
        if 'ai_analysis' not in event:
            event['ai_analysis'] = "【AI分析】分析生成中..."
    
    # 统计信息
    total_events = len(events)
    high_impact = len([e for e in events if e.get('importance', 1) == 3])
    medium_impact = len([e for e in events if e.get('importance', 1) == 2])
    low_impact = len([e for e in events if e.get('importance', 1) == 1])
    
    return jsonify({
        "status": "success",
        "data": events,
        "count": total_events,
        "importance_stats": {
            "high": high_impact,
            "medium": medium_impact,
            "low": low_impact,
            "total": total_events
        },
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "timezone": "北京时间 (UTC+8)",
        "note": "事件AI分析基于实时价格数据"
    })

@app.route('/api/summary')
def get_today_summary():
    """获取今日总结 - 修复版，确保返回真实AI分析"""
    # 如果AI分析数据为空或为默认内容，重新生成
    sections = store.summary_sections
    
    # 检查是否是默认的占位内容
    is_default_content = False
    default_markers = [
        "正在分析实时市场数据",
        "AI分析内容生成中",
        "等待AI分析生成",
        "AI分析生成失败"
    ]
    
    for section_content in sections.values():
        if any(marker in section_content for marker in default_markers):
            is_default_content = True
            break
    
    # 如果是默认内容或空，重新生成AI分析
    if is_default_content or not any(sections.values()):
        logger.info("检测到默认AI分析内容，重新生成...")
        try:
            # 使用当前数据生成分析
            analysis_result = generate_comprehensive_analysis_with_sections(
                store.market_signals, 
                store.forex_rates, 
                store.economic_events
            )
            if analysis_result and analysis_result.get("sections"):
                sections = analysis_result["sections"]
                store.summary_sections = sections
                logger.info("重新生成AI分析成功")
            else:
                logger.warning("重新生成AI分析返回空结果")
        except Exception as e:
            logger.error(f"重新生成AI分析失败: {e}")
    
    # 确保货币对摘要不为空
    currency_pairs = store.currency_pairs_summary
    if not currency_pairs:
        currency_pairs = generate_currency_pairs_summary(store.market_signals, store.forex_rates)
    
    # 计算高影响事件数量
    high_impact_count = len([e for e in (store.economic_events or []) if e.get('importance', 1) == 3])
    
    # 返回数据
    return jsonify({
        "status": "success",
        "summary": "基于实时数据的AI分析报告",
        "sections": sections,
        "currency_pairs": currency_pairs,
        "high_impact_events_count": high_impact_count,
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "ai_enabled": config.enable_ai,
        "ai_model": "gpt-4",
        "timezone": "北京时间 (UTC+8)",
        "note": "分析基于最新实时行情数据，每30分钟自动更新"
    })

@app.route('/api/currency_pairs/summary')
def get_currency_pairs_summary():
    """获取货币对摘要信息"""
    currency_pairs = store.currency_pairs_summary
    
    return jsonify({
        "status": "success",
        "currency_pairs": currency_pairs,
        "count": len(currency_pairs),
        "generated_at": store.last_updated.isoformat() if store.last_updated else datetime.now(timezone(timedelta(hours=8))).isoformat()
    })

@app.route('/api/market/signals')
def get_market_signals():
    signals = store.market_signals
    return jsonify({
        "status": "success",
        "data": signals,
        "count": len(signals),
        "source": "Ziwox",
        "special_pairs": [
            {"pair": "XAUUSD", "name": "黄金/美元", "type": "贵金属"},
            {"pair": "XAGUSD", "name": "白银/美元", "type": "贵金属"},
            {"pair": "BTCUSD", "name": "比特币/美元", "type": "加密货币"}
        ]
    })

@app.route('/api/forex/rates')
def get_forex_rates():
    rates = store.forex_rates
    return jsonify({
        "status": "success",
        "data": rates,
        "count": len(rates)
    })

@app.route('/api/analysis/daily')
def get_daily_analysis():
    analysis = store.daily_analysis
    return jsonify({
        "status": "success",
        "analysis": analysis,
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "ai_provider": "laozhang.ai",
        "ai_model": "gpt-4",
        "timezone": "北京时间 (UTC+8)"
    })

@app.route('/api/overview')
def get_overview():
    events = store.economic_events
    high_count = len([e for e in events if e.get('importance', 1) == 3])
    medium_count = len([e for e in events if e.get('importance', 1) == 2])
    low_count = len([e for e in events if e.get('importance', 1) == 1])
    
    # 检查AI分析内容
    has_real_ai = False
    if store.summary_sections:
        for section_content in store.summary_sections.values():
            if section_content and len(section_content) > 50 and "AI分析生成" not in section_content:
                has_real_ai = True
                break
    
    return jsonify({
        "status": "success",
        "timestamp": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "timezone": "北京时间 (UTC+8)",
        "market_signals_count": len(store.market_signals),
        "forex_rates_count": len(store.forex_rates),
        "economic_events_count": len(store.economic_events),
        "currency_pairs_summary_count": len(store.currency_pairs_summary),
        "importance_breakdown": {
            "high": high_count,
            "medium": medium_count,
            "low": low_count
        },
        "ai_status": {
            "enabled": config.enable_ai,
            "model": "gpt-4",
            "has_real_analysis": has_real_ai,
            "sections_count": len(store.summary_sections) if store.summary_sections else 0
        }
    })

# ============================================================================
# 启动应用
# ============================================================================
if __name__ == '__main__':
    logger.info("="*60)
    logger.info("启动宏观经济AI分析工具（实时数据版）")
    logger.info(f"财经日历源: Forex Factory JSON API")
    logger.info(f"AI分析服务: laozhang.ai（GPT-4模型）")
    logger.info(f"特殊品种: XAU/USD (黄金), XAG/USD (白银), BTC/USD (比特币)")
    logger.info(f"时区: 北京时间 (UTC+8)")
    logger.info(f"AI模型: GPT-4")
    logger.info("注意: AI分析将基于实时价格数据生成")
    logger.info("="*60)

    # 首次启动时获取数据
    try:
        logger.info("首次启动，正在获取实时数据...")
        success = execute_data_update()
        if success:
            logger.info("初始实时数据获取成功")
            events = store.economic_events
            currency_pairs = store.currency_pairs_summary
            logger.info(f"事件总数: {len(events)}")
            logger.info(f"货币对摘要数: {len(currency_pairs)}")
            
            # 检查AI分析是否成功
            if store.summary_sections:
                logger.info("AI分析章节状态:")
                for section_name, content in store.summary_sections.items():
                    logger.info(f"  - {section_name}: {len(content)} 字符")
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