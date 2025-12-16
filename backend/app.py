"""
宏观经济AI分析工具 - 完整版本
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
        self.use_mock = os.getenv("USE_MOCK_DATA", "false").lower() == "true"
        self.enable_ai = os.getenv("ENABLE_AI", "true").lower() == "true"

        # 监控的货币对 - 增加黄金、白银、比特币
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
# 模块3：财经日历获取 (Forex Factory JSON API) - 完整抓取版本
# ============================================================================
def fetch_calendar_forex_factory():
    """
    从Forex Factory JSON API获取本周所有经济日历数据
    不再限制50个事件，完整抓取
    """
    try:
        logger.info("正在从Forex Factory JSON API获取完整经济日历...")
        
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
                events = parse_forex_factory_events_complete(data)
                logger.info(f"成功从Forex Factory解析 {len(events)} 个事件（北京时间）")
                return events
        else:
            logger.error(f"Forex Factory API请求失败，状态码: {response.status_code}")
            
    except Exception as e:
        logger.error(f"获取Forex Factory日历时出错: {str(e)}")
    
    # 如果失败，回退到模拟数据
    logger.warning("Forex Factory API获取失败，使用模拟数据")
    return get_complete_simulated_calendar()

def parse_forex_factory_events_complete(raw_events):
    """
    完整解析Forex Factory返回的所有事件
    不再限制数量，获取所有有效事件
    """
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
            
            # 特别关注重要事件
            is_non_farm = "non-farm" in title.lower() or "employment" in title.lower()
            is_important = impact.lower() in ["high", "medium"] or is_non_farm
            
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
                    # 如果没有日期时间，使用默认值
                    event_date = today
                    time_str = "00:00"
                    date_str_formatted = today.strftime("%Y-%m-%d")
                    
            except (ValueError, TypeError) as e:
                logger.warning(f"解析日期时间失败: {date_str}, 错误: {e}")
                continue
            
            # 重要性映射
            importance = map_impact_to_importance(impact)
            
            # 如果是重要事件，提高重要性级别
            if is_important and importance < 3:
                importance = min(importance + 1, 3)
            
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
                "is_important": is_important
            }
            
            events.append(event)
            
        except Exception as e:
            logger.warning(f"解析Forex Factory事件 {i} 时出错: {e}")
            continue
    
    # 按日期和时间排序（从今天最近的时间开始）
    events.sort(key=lambda x: (x["date"], x["time"]))
    
    # 移除限制，返回所有事件
    return events

def get_complete_simulated_calendar():
    """完整的模拟数据生成 - 包含更多事件"""
    beijing_timezone = timezone(timedelta(hours=8))
    now_beijing = datetime.now(beijing_timezone)
    today_str = now_beijing.strftime("%Y-%m-%d")
    hour = now_beijing.hour
    
    # 获取本周的日期
    base_events = []
    
    # 今天的事件
    today_events = [
        {
            "id": 1,
            "date": today_str,
            "time": "21:00",
            "country": "US",
            "name": "美联储利率决议",
            "forecast": "5.5%",
            "previous": "5.5%",
            "actual": "5.5%" if hour >= 21 else "待公布",
            "importance": 3,
            "currency": "USD",
            "description": "美联储联邦基金利率决定",
            "source": "模拟数据",
            "is_important": True
        },
        {
            "id": 2,
            "date": today_str,
            "time": "09:30",
            "country": "CN",
            "name": "中国CPI年率",
            "forecast": "0.2%",
            "previous": "0.1%",
            "actual": "0.3%" if hour >= 9 else "待公布",
            "importance": 2,
            "currency": "CNY",
            "description": "中国消费者价格指数同比变化",
            "source": "模拟数据",
            "is_important": True
        },
        {
            "id": 3,
            "date": today_str,
            "time": "20:30",
            "country": "US",
            "name": "美国非农就业人数变化",
            "forecast": "180K",
            "previous": "199K",
            "actual": "待公布" if hour < 20 else "185K",
            "importance": 3,
            "currency": "USD",
            "description": "美国非农业就业人数月度变化",
            "source": "模拟数据",
            "is_important": True
        },
        {
            "id": 4,
            "date": today_str,
            "time": "21:45",
            "country": "US",
            "name": "美国ISM制造业PMI",
            "forecast": "49.5",
            "previous": "48.7",
            "actual": "待公布" if hour < 21 else "50.1",
            "importance": 2,
            "currency": "USD",
            "description": "美国供应管理协会制造业采购经理人指数",
            "source": "模拟数据",
            "is_important": True
        }
    ]
    
    # 明天的事件
    tomorrow = now_beijing + timedelta(days=1)
    tomorrow_str = tomorrow.strftime("%Y-%m-%d")
    tomorrow_events = [
        {
            "id": 5,
            "date": tomorrow_str,
            "time": "15:00",
            "country": "GB",
            "name": "英国GDP月率",
            "forecast": "0.1%",
            "previous": "0.0%",
            "actual": "待公布",
            "importance": 2,
            "currency": "GBP",
            "description": "英国国内生产总值月度增长率",
            "source": "模拟数据",
            "is_important": True
        },
        {
            "id": 6,
            "date": tomorrow_str,
            "time": "17:00",
            "country": "EU",
            "name": "欧元区CPI年率",
            "forecast": "2.4%",
            "previous": "2.6%",
            "actual": "待公布",
            "importance": 2,
            "currency": "EUR",
            "description": "欧元区消费者价格指数同比变化",
            "source": "模拟数据",
            "is_important": True
        }
    ]
    
    # 后天的事件
    day_after = now_beijing + timedelta(days=2)
    day_after_str = day_after.strftime("%Y-%m-%d")
    day_after_events = [
        {
            "id": 7,
            "date": day_after_str,
            "time": "10:00",
            "country": "CN",
            "name": "中国贸易帐",
            "forecast": "85.0B",
            "previous": "68.1B",
            "actual": "待公布",
            "importance": 2,
            "currency": "CNY",
            "description": "中国进出口贸易差额",
            "source": "模拟数据",
            "is_important": True
        }
    ]
    
    # 更多事件（本周内）
    for i in range(3, 7):  # 本周剩下的日子
        event_date = now_beijing + timedelta(days=i)
        date_str = event_date.strftime("%Y-%m-%d")
        
        # 添加一些常规事件
        base_events.append({
            "id": 100 + i,
            "date": date_str,
            "time": "14:30",
            "country": "US",
            "name": "美国初请失业金人数",
            "forecast": "210K",
            "previous": "209K",
            "actual": "待公布",
            "importance": 2,
            "currency": "USD",
            "description": "美国每周首次申请失业救济人数",
            "source": "模拟数据",
            "is_important": True
        })
        
        base_events.append({
            "id": 200 + i,
            "date": date_str,
            "time": "16:00",
            "country": "EU",
            "name": "欧元区零售销售月率",
            "forecast": "0.3%",
            "previous": "-0.1%",
            "actual": "待公布",
            "importance": 1,
            "currency": "EUR",
            "description": "欧元区零售销售月度变化",
            "source": "模拟数据",
            "is_important": False
        })
    
    base_events.extend(today_events)
    base_events.extend(tomorrow_events)
    base_events.extend(day_after_events)
    
    # 按日期和时间排序
    base_events.sort(key=lambda x: (x["date"], x["time"]))
    
    logger.info(f"使用完整模拟财经日历数据，共 {len(base_events)} 个事件")
    return base_events

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
    
    # 货币到国家代码的映射
    currency_to_country = {
        "USD": "US", "EUR": "EU", "GBP": "GB", "JPY": "JP",
        "AUD": "AU", "CAD": "CA", "CHF": "CH", "CNY": "CN",
        "NZD": "NZ", "RUB": "RU", "BRL": "BR", "INR": "IN",
        "KRW": "KR", "MXN": "MX", "ZAR": "ZA", "SEK": "SE",
        "NOK": "NO", "DKK": "DK", "TRY": "TR", "PLN": "PL",
        "HKD": "HK", "SGD": "SG", "THB": "TH", "IDR": "ID"
    }
    
    # 如果本身就是货币代码
    if country_str in currency_to_country:
        return currency_to_country[country_str]
    
    # 国家代码映射
    country_mapping = {
        "US": "US", "USA": "US", "UNITED STATES": "US",
        "EU": "EU", "EURO": "EU", "EZ": "EU", "EUROZONE": "EU",
        "UK": "GB", "GB": "GB", "GBR": "GB", "UNITED KINGDOM": "GB",
        "JP": "JP", "JPN": "JP", "JAPAN": "JP",
        "AU": "AU", "AUS": "AU", "AUSTRALIA": "AU",
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
        "HK": "HK", "HKG": "HK", "HONG KONG": "HK",
        "SG": "SG", "SGP": "SG", "SINGAPORE": "SG",
        "TH": "TH", "THA": "TH", "THAILAND": "TH",
        "ID": "ID", "IDN": "ID", "INDONESIA": "ID"
    }
    
    # 尝试匹配国家
    for code, country_code in country_mapping.items():
        if country_str == code or country_str.startswith(code):
            return country_code
    
    return country_str[:2] if len(country_str) >= 2 else "GL"

def fetch_economic_calendar():
    """主函数：获取财经日历"""
    if config.use_mock:
        logger.info("配置为使用模拟数据模式")
        return get_complete_simulated_calendar()
    
    # 优先尝试：Forex Factory JSON API
    events = fetch_calendar_forex_factory()
    
    # 确保事件有AI分析
    events_with_ai = add_ai_analysis_to_events(events)
    
    return events_with_ai

def add_ai_analysis_to_events(events):
    """为事件添加AI分析"""
    if not events:
        return events
    
    # 只为重要性较高的事件生成AI分析
    important_events = [e for e in events if e.get('importance', 1) >= 2][:10]
    
    for event in important_events:
        try:
            ai_analysis = generate_ai_analysis_for_event(event)
            event['ai_analysis'] = ai_analysis
            time.sleep(0.5)  # 避免API调用过于频繁
        except Exception as e:
            logger.error(f"为事件生成AI分析失败: {e}")
            event['ai_analysis'] = "【AI分析】分析生成失败，请稍后重试"
    
    # 为其他事件添加默认AI分析
    for event in events:
        if 'ai_analysis' not in event:
            event['ai_analysis'] = "【AI分析】该事件重要性较低，暂无详细分析。关注市场整体情绪和主要货币对走势。"
    
    return events

# ============================================================================
# 模块4：AI综合分析生成 (laozhang.ai) - 修复self错误并加入实时数据
# ============================================================================
def generate_ai_analysis_for_event(event):
    """为单个事件生成AI分析"""
    if not config.enable_ai:
        return "【AI分析】AI分析功能当前已禁用"
    
    api_key = config.openai_api_key.strip()
    if not api_key or len(api_key) < 30:
        return "【AI分析】API密钥配置无效"
    
    try:
        # 构建提示词
        prompt = f"""你是一位专业的宏观外汇分析师。请基于以下经济事件，生成简要的AI分析：

事件信息：
- 国家：{event.get('country', '未知')}
- 事件：{event.get('name', '未知事件')}
- 时间：{event.get('date', '')} {event.get('time', '')}（北京时间）
- 预测值：{event.get('forecast', 'N/A')}
- 前值：{event.get('previous', 'N/A')}
- 重要性：{event.get('importance', 1)}级

请用中文分析：
1. 该事件对相关货币的可能影响
2. 市场预期与实际情况的对比
3. 1-2条具体的交易建议（方向、入场区域、止损）

请控制在150字以内，直接给出分析，不要多余说明。"""

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        request_body = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": "你是一位经验丰富的外汇宏观交易员，擅长给出清晰、直接、可执行的交易分析。"},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 300,
            "temperature": 0.4
        }

        response = requests.post(
            f"{config.openai_base_url}/chat/completions",
            headers=headers,
            json=request_body,
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            if 'choices' in result and len(result['choices']) > 0:
                ai_content = result['choices'][0]['message']['content']
                return f"【AI分析】{ai_content}"
        else:
            logger.warning(f"AI分析请求失败: {response.status_code}")
            return "【AI分析】数据更新中..."
            
    except Exception as e:
        logger.error(f"生成AI分析时出错: {e}")
    
    return "【AI分析】分析生成中..."

def generate_comprehensive_analysis_with_sections(signals, rates, events):
    """生成综合AI分析，并分章节"""
    if not config.enable_ai:
        logger.info("AI分析功能已被禁用")
        return {
            "summary": "【AI分析】AI分析功能当前已禁用。",
            "sections": {
                "market": "市场分析功能当前已禁用。",
                "events": "事件分析功能当前已禁用。",
                "outlook": "展望功能当前已禁用。",
                "risks": "风险提示功能当前已禁用。"
            }
        }
    
    api_key = config.openai_api_key.strip()
    if not api_key or len(api_key) < 30:
        logger.error("laozhang.ai API密钥无效或过短")
        return {
            "summary": "【AI分析】错误：API密钥配置无效。",
            "sections": {
                "market": "API密钥配置无效。",
                "events": "API密钥配置无效。",
                "outlook": "API密钥配置无效。",
                "risks": "API密钥配置无效。"
            }
        }
    
    logger.info("开始生成综合AI分析（分章节）...")
    
    try:
        # 重要事件统计
        important_events = [e for e in events if e.get('importance', 1) >= 2]
        event_names = [e.get('name', '') for e in important_events[:5]]
        
        # 市场数据摘要 - 特别关注黄金、白银、比特币
        market_data = []
        special_pairs = ['XAUUSD', 'XAGUSD', 'BTCUSD']
        
        # 先添加特殊品种
        for pair in special_pairs:
            signal = next((s for s in signals if s.get('pair') == pair), None)
            rate = rates.get(pair, {}).get('rate', 'N/A') if rates else 'N/A'
            if signal:
                market_data.append(f"{pair}: {rate}")
        
        # 添加其他主要货币对
        for i, signal in enumerate(signals[:3]):
            pair = signal.get('pair', '')
            if pair not in special_pairs:
                rate = rates.get(pair, {}).get('rate', 'N/A') if rates else 'N/A'
                market_data.append(f"{pair}: {rate}")
        
        # 构建提示词，要求分章节生成，特别关注贵金属和加密货币
        prompt = f"""你是一位专业的宏观外汇策略分析师。请基于以下实时数据，生成一份结构化的今日外汇市场分析报告。

【实时市场价格】
{chr(10).join(market_data) if market_data else "暂无实时市场数据"}

【本周重要经济事件】
{chr(10).join([f"- {name}" for name in event_names]) if event_names else "本周无重要经济事件"}

【分析要求】
请按以下章节结构组织分析，每个章节单独成段：

1. 市场概况（market）：基于当前价格水平的市场整体状况和主要特征
2. 事件分析（events）：对本周重要经济事件的分析和预期，特别是对黄金(XAU/USD)、白银(XAG/USD)、比特币(BTC/USD)的影响
3. 货币对展望（outlook）：主要货币对（EUR/USD, USD/JPY, GBP/USD, AUD/USD）和贵金属/加密货币（XAU/USD, XAG/USD, BTC/USD）的技术分析和关键位，必须基于上述实时价格
4. 风险提示（risks）：今日交易的主要风险和注意事项

每个章节请控制在150-200字，使用中文，简洁专业。
特别要求：对黄金、白银、比特币的分析必须准确反映当前价格水平。"""

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        request_body = {
            "model": "gpt-4",
            "messages": [
                {"role": "system", "content": "你是一位经验丰富的外汇和贵金属交易员，擅长基于实时数据给出结构化、清晰、可执行的交易分析。"},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 1500,
            "temperature": 0.4
        }

        response = requests.post(
            f"{config.openai_base_url}/chat/completions",
            headers=headers,
            json=request_body,
            timeout=60
        )

        if response.status_code == 200:
            result = response.json()
            if 'choices' in result and len(result['choices']) > 0:
                ai_content = result['choices'][0]['message']['content']
                
                # 解析AI回复，分章节
                sections = parse_ai_response_into_sections(ai_content)
                
                # 确保货币对展望包含实时价格
                sections = enhance_sections_with_real_data(sections, signals, rates)
                
                return {
                    "summary": "基于实时数据的AI分析报告已生成",
                    "sections": sections
                }
                
    except Exception as e:
        logger.error(f"生成综合AI分析时出错: {e}")
    
    # 失败时返回默认数据
    return get_default_analysis_sections()

def parse_ai_response_into_sections(ai_content):
    """解析AI回复，分章节提取内容"""
    sections = {
        "market": "等待AI分析生成...",
        "events": "等待AI分析生成...",
        "outlook": "等待AI分析生成...",
        "risks": "等待AI分析生成..."
    }
    
    if not ai_content:
        return sections
    
    # 尝试按章节解析
    lines = ai_content.split('\n')
    current_section = None
    current_content = []
    
    for line in lines:
        line = line.strip()
        
        # 检测章节标题
        if "市场概况" in line or "市场概况（market）" in line:
            if current_section and current_content:
                sections[current_section] = ' '.join(current_content)
            current_section = "market"
            current_content = []
        elif "事件分析" in line or "事件分析（events）" in line:
            if current_section and current_content:
                sections[current_section] = ' '.join(current_content)
            current_section = "events"
            current_content = []
        elif "货币对展望" in line or "货币对展望（outlook）" in line:
            if current_section and current_content:
                sections[current_section] = ' '.join(current_content)
            current_section = "outlook"
            current_content = []
        elif "风险提示" in line or "风险提示（risks）" in line:
            if current_section and current_content:
                sections[current_section] = ' '.join(current_content)
            current_section = "risks"
            current_content = []
        elif line and current_section:
            current_content.append(line)
    
    # 处理最后一个章节
    if current_section and current_content:
        sections[current_section] = ' '.join(current_content)
    
    return sections

def enhance_sections_with_real_data(sections, signals, rates):
    """用实时数据增强分析章节"""
    # 获取实时价格
    real_time_prices = {}
    for signal in signals:
        pair = signal.get('pair', '')
        price = signal.get('last_price', 0)
        if pair and price > 0:
            real_time_prices[pair] = price
    
    # 在货币对展望中添加实时数据说明
    if sections.get('outlook'):
        outlook = sections['outlook']
        
        # 检查是否包含实时价格
        price_mentioned = False
        for pair, price in real_time_prices.items():
            if str(price) in outlook:
                price_mentioned = True
                break
        
        if not price_mentioned and real_time_prices:
            price_summary = []
            for pair in ['XAUUSD', 'XAGUSD', 'BTCUSD', 'EURUSD']:
                if pair in real_time_prices:
                    price_summary.append(f"{pair}: {real_time_prices[pair]}")
            
            if price_summary:
                sections['outlook'] = outlook + f"\n\n（基于实时价格：{', '.join(price_summary)}）"
    
    return sections

def get_default_analysis_sections():
    """获取默认的分析章节"""
    return {
        "summary": "【AI分析】基于实时数据生成分析中...",
        "sections": {
            "market": "正在分析实时市场数据...",
            "events": "正在分析实时经济事件...",
            "outlook": "正在生成货币对展望...",
            "risks": "正在评估交易风险..."
        }
    }

# ============================================================================
# 新增：货币对摘要生成函数
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
    
    # 按优先级排序：黄金、白银、比特币优先，然后是主要货币对
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
                continue  # 如果都没有价格信息，跳过这个货币对
        
        # 格式化价格
        if price > 0:
            # 根据货币对类型决定小数位数
            if pair in ['XAUUSD', 'XAGUSD']:
                # 贵金属显示2位小数
                formatted_price = f"{price:.2f}"
            elif pair == 'BTCUSD':
                # 比特币显示整数
                formatted_price = f"{int(price)}"
            else:
                # 外汇货币对显示4-5位小数
                if price < 10:
                    formatted_price = f"{price:.5f}"
                else:
                    formatted_price = f"{price:.4f}"
            
            # 获取显示信息
            display_info = pair_display_info.get(pair, {'name': pair, 'icon': '💱'})
            
            # 创建摘要对象
            summary = {
                'pair': pair,
                'name': display_info['name'],
                'icon': display_info['icon'],
                'price': formatted_price,
                'source': source,
                'trend': 'neutral'  # 这里可以添加趋势判断逻辑
            }
            
            currency_pairs_summary.append(summary)
    
    logger.info(f"生成货币对摘要，共 {len(currency_pairs_summary)} 个货币对")
    return currency_pairs_summary

# ============================================================================
# 核心数据更新函数
# ============================================================================
def execute_data_update():
    """执行数据更新的核心逻辑"""
    try:
        logger.info("="*60)
        logger.info(f"开始执行数据更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # 1. 获取市场信号数据
        logger.info("阶段1/4: 获取市场信号...")
        signals = fetch_market_signals_ziwox()
        
        # 记录获取到的实时价格
        for signal in signals:
            pair = signal.get('pair', '')
            price = signal.get('last_price', 0)
            if pair and price > 0:
                logger.info(f"  实时价格: {pair} = {price}")

        # 2. 获取实时汇率数据
        logger.info("阶段2/4: 获取实时汇率...")
        rates = fetch_forex_rates_alpha_vantage(signals)

        # 3. 获取财经日历数据（完整版）
        logger.info("阶段3/4: 获取财经日历（完整版）...")
        events = fetch_economic_calendar()
        
        # 确保事件按正确时间排序
        events = sort_events_by_datetime(events)

        # 4. 生成综合AI分析（分章节）
        logger.info("阶段4/4: 生成综合AI分析（分章节）...")
        analysis_result = generate_comprehensive_analysis_with_sections(signals, rates, events)
        
        sections = analysis_result.get("sections", {})
        
        # 5. 生成货币对摘要
        logger.info("阶段5/4: 生成货币对摘要...")
        currency_pairs_summary = generate_currency_pairs_summary(signals, rates)

        # 6. 存储数据
        store.update_all(signals, rates, events, "实时AI分析报告", sections, None, currency_pairs_summary)

        logger.info(f"数据更新成功完成:")
        logger.info(f"  - 市场信号: {len(signals)} 个")
        logger.info(f"  - 汇率数据: {len(rates)} 个")
        logger.info(f"  - 财经日历: {len(events)} 个（完整版）")
        logger.info(f"  - AI分析章节: {len(sections)} 个")
        logger.info(f"  - 货币对摘要: {len(currency_pairs_summary)} 个")
        logger.info("="*60)
        return True

    except Exception as e:
        logger.error(f"数据更新失败: {str(e)}", exc_info=True)
        store.set_updating(False, str(e))
        return False

def sort_events_by_datetime(events):
    """按日期时间排序（从最近到最远）"""
    if not events:
        return events
    
    # 首先确保我们只保留今天及以后的事件
    today = datetime.now(timezone(timedelta(hours=8))).date()
    future_events = []
    
    for event in events:
        try:
            event_date_str = event.get('date', '')
            if event_date_str:
                event_date = datetime.strptime(event_date_str, "%Y-%m-%d").date()
                if event_date >= today:
                    future_events.append(event)
        except:
            continue
    
    # 按日期和时间排序（从早到晚）
    future_events.sort(key=lambda x: (x.get('date', '9999-12-31'), x.get('time', '23:59')))
    
    return future_events

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
# Flask路由 - 新增货币对摘要接口
# ============================================================================
@app.route('/')
def index():
    return jsonify({
        "status": "running",
        "service": "宏观经济AI分析工具（实时版）",
        "version": "5.2",
        "data_sources": {
            "market_signals": "Ziwox",
            "forex_rates": "Alpha Vantage + Ziwox补充",
            "economic_calendar": "Forex Factory JSON API（完整版）",
            "ai_analysis": "laozhang.ai（实时数据版）"
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
    """获取今日事件 - 完整版，按时间排序"""
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
    
    # 检查今天的事件
    today = datetime.now(timezone(timedelta(hours=8))).date()
    today_str = today.strftime("%Y-%m-%d")
    today_events = [e for e in events if e.get('date') == today_str]
    
    # 检查明天的事件
    tomorrow = today + timedelta(days=1)
    tomorrow_str = tomorrow.strftime("%Y-%m-%d")
    tomorrow_events = [e for e in events if e.get('date') == tomorrow_str]
    
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
        "date_stats": {
            "today": len(today_events),
            "tomorrow": len(tomorrow_events),
            "future": total_events - len(today_events) - len(tomorrow_events)
        },
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "timezone": "北京时间 (UTC+8)",
        "note": "事件已按日期时间排序（从最近到最远）"
    })

@app.route('/api/summary')
def get_today_summary():
    """获取今日总结 - 分章节版本，包含货币对摘要"""
    sections = store.summary_sections
    currency_pairs = store.currency_pairs_summary
    
    # 计算高影响事件数量
    high_impact_count = len([e for e in store.economic_events if e.get('importance', 1) == 3])
    
    # 确保返回北京时间格式
    beijing_timezone = timezone(timedelta(hours=8))
    generated_at = datetime.now(beijing_timezone)
    
    if store.last_updated:
        # 如果已有时间，确保是北京时间
        if store.last_updated.tzinfo is None:
            # 如果没有时区信息，添加北京时间
            generated_at = store.last_updated.replace(tzinfo=beijing_timezone)
        else:
            # 转换为北京时间
            generated_at = store.last_updated.astimezone(beijing_timezone)
    
    return jsonify({
        "status": "success",
        "summary": "基于实时数据的AI分析报告",
        "sections": sections,
        "currency_pairs": currency_pairs,
        "high_impact_events_count": high_impact_count,
        "generated_at": generated_at.isoformat(),
        "ai_enabled": config.enable_ai,
        "timezone": "北京时间 (UTC+8)"
    })

@app.route('/api/summary/sections')
def get_summary_sections():
    """专门获取各个章节的内容 - 供前端使用"""
    sections = store.summary_sections
    
    return jsonify({
        "status": "success",
        "sections": sections,
        "generated_at": store.last_updated.isoformat() if store.last_updated else datetime.now(timezone(timedelta(hours=8))).isoformat()
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
        "timezone": "北京时间 (UTC+8)"
    })

@app.route('/api/overview')
def get_overview():
    events = store.economic_events
    high_count = len([e for e in events if e.get('importance', 1) == 3])
    medium_count = len([e for e in events if e.get('importance', 1) == 2])
    low_count = len([e for e in events if e.get('importance', 1) == 1])
    
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
        "has_ai_analysis": bool(store.daily_analysis and len(store.daily_analysis) > 10),
        "has_summary_sections": bool(store.summary_sections and len(store.summary_sections) > 0)
    })

# ============================================================================
# 启动应用
# ============================================================================
if __name__ == '__main__':
    logger.info("="*60)
    logger.info("启动宏观经济AI分析工具（实时数据版）")
    logger.info(f"财经日历源: Forex Factory JSON API")
    logger.info(f"AI分析服务: laozhang.ai（实时数据版）")
    logger.info(f"特殊品种: XAU/USD (黄金), XAG/USD (白银), BTC/USD (比特币)")
    logger.info(f"模拟模式: {config.use_mock}")
    logger.info(f"时区: 北京时间 (UTC+8)")
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
            
            # 检查非农就业数据是否被抓取
            non_farm_events = [e for e in events if 'non-farm' in e.get('name', '').lower() or 'employment' in e.get('name', '').lower()]
            if non_farm_events:
                logger.info(f"成功抓取到非农就业相关事件: {[e['name'] for e in non_farm_events]}")
            else:
                logger.warning("未发现非农就业相关事件，请检查数据源")
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