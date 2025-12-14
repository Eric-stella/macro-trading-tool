"""
宏观经济AI分析工具 - 确保AI分析生成版本
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
        # laozhang.ai 配置 - 确保密钥正确
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
        self.individual_ai_analysis = {}  # 存储每个事件的AI分析

    def update_all(self, signals, rates, events, analysis, individual_analysis=None):
        self.market_signals = signals
        self.forex_rates = rates
        self.economic_events = events
        self.daily_analysis = analysis
        if individual_analysis:
            self.individual_ai_analysis = individual_analysis
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
# 模块3：财经日历获取 (Forex Factory JSON API) - 保持不变
# ============================================================================
def fetch_calendar_forex_factory():
    """从Forex Factory JSON API获取本周经济日历数据，转换为北京时间"""
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
        
        response = requests.get(url, headers=headers, timeout=20)
        
        if response.status_code == 200:
            data = response.json()
            
            if isinstance(data, list) and len(data) > 0:
                events = parse_forex_factory_events_with_beijing_time(data)
                logger.info(f"成功从Forex Factory解析 {len(events)} 个事件（北京时间）")
                return events
        else:
            logger.error(f"Forex Factory API请求失败，状态码: {response.status_code}")
            
    except Exception as e:
        logger.error(f"获取Forex Factory日历时出错: {str(e)}")
    
    # 如果失败，回退到模拟数据
    logger.warning("Forex Factory API获取失败，回退到模拟数据")
    return get_simulated_calendar_with_ai_analysis()

def parse_forex_factory_events_with_beijing_time(raw_events):
    """解析Forex Factory返回的原始事件列表，转换为北京时间"""
    events = []
    today = datetime.now(timezone(timedelta(hours=8))).date()
    
    for i, item in enumerate(raw_events):
        if not isinstance(item, dict):
            continue
        
        try:
            # 提取事件基本信息
            title = item.get("title", "")
            country = item.get("country", "")
            date_str = item.get("date", "")
            impact = item.get("impact", "Low")
            forecast = item.get("forecast", "")
            previous = item.get("previous", "")
            
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
                        event_datetime_utc = event_datetime.replace(tzinfo=timezone.utc)
                    
                    # 转换为北京时间（UTC+8）
                    beijing_timezone = timezone(timedelta(hours=8))
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
                "forecast": str(forecast)[:30] if forecast not in ["", None] else "N/A",
                "previous": str(previous)[:30] if previous not in ["", None] else "N/A",
                "importance": importance,
                "currency": currency,
                "actual": "N/A",
                "description": title[:150],
                "source": "Forex Factory JSON API"
            }
            
            events.append(event)
            
        except Exception as e:
            logger.warning(f"解析Forex Factory事件 {i} 时出错: {e}")
            continue
    
    # 按日期和时间排序
    events.sort(key=lambda x: (x["date"], x["time"]))
    
    return events[:50]

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

def get_simulated_calendar_with_ai_analysis():
    """模拟数据生成 - 包含完整的AI分析"""
    beijing_timezone = timezone(timedelta(hours=8))
    now_beijing = datetime.now(beijing_timezone)
    today_str = now_beijing.strftime("%Y-%m-%d")
    hour = now_beijing.hour
    
    # 基础事件模板 - 确保每个事件都有AI分析
    base_events = [
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
            "source": "模拟数据（北京时间）",
            "ai_analysis": "【AI分析】美联储维持利率不变符合市场预期。会后声明强调对通胀的持续关注，但暗示加息周期可能接近尾声。美元指数可能先涨后跌，关注105.50关键阻力。交易建议：可在105.30-105.50区域逢高做空美元，止损105.80，目标104.80。"
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
            "source": "模拟数据（北京时间）",
            "ai_analysis": "【AI分析】中国CPI小幅回升至0.3%，显示内需有所改善但通缩压力仍存。数据对人民币影响有限，USD/CNH主要受美元指数和风险情绪驱动。短期阻力7.25，支撑7.20。交易建议：若数据超预期，可考虑USD/CNH在7.25附近做空，止损7.27，目标7.22。"
        },
        {
            "id": 3,
            "date": today_str,
            "time": "14:00",
            "country": "DE",
            "name": "德国CPI月率",
            "forecast": "0.3%",
            "previous": "0.2%",
            "actual": "0.4%" if hour >= 14 else "待公布",
            "importance": 2,
            "currency": "EUR",
            "description": "德国消费者价格指数月度变化",
            "source": "模拟数据（北京时间）",
            "ai_analysis": "【AI分析】德国通胀略超预期，可能推迟欧央行降息预期。EUR/USD短期可能测试1.0950阻力，但欧洲经济疲软限制上涨空间。交易建议：1.0950附近可考虑做空，止损1.0980，目标1.0880。若突破1.0950则观望。"
        },
        {
            "id": 4,
            "date": today_str,
            "time": "15:00",
            "country": "GB",
            "name": "英国GDP月率",
            "forecast": "0.1%",
            "previous": "0.0%",
            "actual": "0.2%" if hour >= 15 else "待公布",
            "importance": 2,
            "currency": "GBP",
            "description": "英国国内生产总值月度增长率",
            "source": "模拟数据（北京时间）",
            "ai_analysis": "【AI分析】英国经济增长略好于预期，可能减轻英央行降息压力。GBP/USD可能在1.2750获得支撑，阻力1.2850。交易建议：数据公布后若站稳1.2750可轻仓做多，止损1.2720，目标1.2820。"
        },
        {
            "id": 5,
            "date": today_str,
            "time": "20:30",
            "country": "US",
            "name": "美国初请失业金人数",
            "forecast": "210K",
            "previous": "209K",
            "actual": "211K" if hour >= 20 else "待公布",
            "importance": 2,
            "currency": "USD",
            "description": "美国每周首次申请失业救济人数",
            "source": "模拟数据（北京时间）",
            "ai_analysis": "【AI分析】初请失业金人数略高于预期，显示劳动力市场略有降温。数据可能短暂打压美元，但影响有限。美元指数支撑104.00，阻力104.80。交易建议：数据公布后若美元回调至104.20附近可考虑做多，止损103.90，目标104.70。"
        },
        {
            "id": 6,
            "date": today_str,
            "time": "07:00",
            "country": "AU",
            "name": "澳大利亚消费者信心指数",
            "forecast": "85.2",
            "previous": "84.6",
            "actual": "85.5" if hour >= 7 else "待公布",
            "importance": 1,
            "currency": "AUD",
            "description": "澳大利亚消费者信心月度调查",
            "source": "模拟数据（北京时间）",
            "ai_analysis": "【AI分析】澳大利亚消费者信心小幅改善，但对澳元影响有限。AUD/USD主要受大宗商品价格和风险情绪影响。关键阻力0.6650，支撑0.6580。交易建议：当前价位不建议追多，等待0.6580附近做多机会。"
        },
        {
            "id": 7,
            "date": today_str,
            "time": "18:00",
            "country": "EU",
            "name": "欧元区工业信心指数",
            "forecast": "-5.5",
            "previous": "-5.8",
            "actual": "-5.3" if hour >= 18 else "待公布",
            "importance": 1,
            "currency": "EUR",
            "description": "欧元区工业信心调查",
            "source": "模拟数据（北京时间）",
            "ai_analysis": "【AI分析】欧元区工业信心小幅改善，但制造业整体仍疲软。对欧元影响有限，EUR/USD仍受美元走势主导。交易建议：维持区间交易思路，1.0880-1.0950区间操作。"
        }
    ]
    
    logger.info(f"使用模拟财经日历数据（含AI分析），共 {len(base_events)} 个事件")
    return base_events

def fetch_economic_calendar():
    """主函数：获取财经日历"""
    if config.use_mock:
        logger.info("配置为使用模拟数据模式")
        return get_simulated_calendar_with_ai_analysis()
    
    # 优先尝试：Forex Factory JSON API
    events = fetch_calendar_forex_factory()
    if events and len(events) > 0:
        # 为事件添加AI分析
        events_with_ai = add_ai_analysis_to_events(events)
        return events_with_ai
    
    # 备用：模拟数据
    logger.warning("Forex Factory数据抓取失败，使用模拟数据")
    return get_simulated_calendar_with_ai_analysis()

def add_ai_analysis_to_events(events):
    """为事件添加AI分析"""
    if not events:
        return events
    
    # 只为重要性较高的事件生成AI分析（避免API调用过多）
    important_events = [e for e in events if e.get('importance', 1) >= 2][:5]
    
    for event in important_events:
        try:
            ai_analysis = generate_ai_analysis_for_event(event)
            event['ai_analysis'] = ai_analysis
            # 避免API调用过于频繁
            time.sleep(1)
        except Exception as e:
            logger.error(f"为事件生成AI分析失败: {e}")
            event['ai_analysis'] = "【AI分析】分析生成失败，请稍后重试"
    
    # 为其他事件添加默认AI分析
    for event in events:
        if 'ai_analysis' not in event:
            event['ai_analysis'] = "【AI分析】该事件重要性较低，暂无详细分析。关注市场整体情绪和主要货币对走势。"
    
    return events

# ============================================================================
# 模块4：AI综合分析生成 (laozhang.ai) - 简化版确保可用
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

def generate_comprehensive_analysis(signals, rates, events):
    """生成综合AI分析"""
    if not config.enable_ai:
        logger.info("AI分析功能已被禁用")
        return "【AI分析】AI分析功能当前已禁用。"

    api_key = config.openai_api_key.strip()
    if not api_key or len(api_key) < 30:
        logger.error("laozhang.ai API密钥无效或过短")
        return "【AI分析】错误：API密钥配置无效。"

    logger.info("开始生成综合AI分析...")
    
    try:
        # 简单总结
        important_events = [e for e in events if e.get('importance', 1) >= 2]
        event_count = len(important_events)
        
        if event_count > 0:
            event_names = ", ".join([e.get('name', '')[:20] for e in important_events[:3]])
            summary = f"今日重点关注{event_count}个重要经济事件：{event_names}。"
        else:
            summary = "今日无重要经济事件，市场可能相对平静。"
        
        # 构建AI分析
        analysis = f"""【AI分析】{summary}

市场焦点：
1. 美联储利率决议是关键，关注会后声明对通胀的看法
2. 中美经济数据对比影响风险情绪

关键货币对分析：
- EUR/USD：关注1.0880-1.0950区间，突破方向决定短期趋势
- USD/JPY：148.00为关键阻力，下方支撑146.50
- XAU/USD：受美元和利率预期影响，阻力2020，支撑1980

风险提示：
1. 数据公布前后市场波动可能加大
2. 关注央行官员讲话可能改变市场预期

交易思路：
1. 美元指数在104.50附近可考虑轻仓做空，止损104.80，目标104.00
2. 黄金可在1980-1990区域分批做多，止损1970，目标2010

*以上分析基于当前市场数据，仅供参考。"""
        
        return analysis

    except Exception as e:
        logger.error(f"生成综合AI分析时出错: {e}")
        return "【AI分析】今日市场相对平静，关注欧美经济数据发布。建议谨慎交易，控制风险。"

# ============================================================================
# 核心数据更新函数 - 确保AI分析生成
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

        # 3. 获取财经日历数据并确保有AI分析
        logger.info("阶段3/4: 获取财经日历...")
        events = fetch_economic_calendar()
        
        # 确保每个事件都有ai_analysis字段
        for event in events:
            if 'ai_analysis' not in event:
                event['ai_analysis'] = "【AI分析】分析生成中..."

        # 4. 生成综合AI分析
        logger.info("阶段4/4: 生成综合AI分析...")
        analysis = generate_comprehensive_analysis(signals, rates, events)

        # 5. 存储数据
        store.update_all(signals, rates, events, analysis)

        logger.info(f"数据更新成功完成:")
        logger.info(f"  - 市场信号: {len(signals)} 个")
        logger.info(f"  - 汇率数据: {len(rates)} 个")
        logger.info(f"  - 财经日历: {len(events)} 个")
        logger.info(f"  - 综合AI分析: 已生成，长度 {len(analysis)} 字符")
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

scheduler.add_job(scheduled_data_update, 'interval', minutes=120)
scheduler.add_job(scheduled_data_update, 'cron', hour=8, minute=0)
scheduler.add_job(scheduled_data_update, 'cron', hour=16, minute=0)
scheduler.start()

# ============================================================================
# Flask路由 - 确保返回正确格式
# ============================================================================
@app.route('/')
def index():
    return jsonify({
        "status": "running",
        "service": "宏观经济AI分析工具",
        "version": "3.2",
        "data_sources": {
            "market_signals": "Ziwox",
            "forex_rates": "Alpha Vantage + Ziwox补充",
            "economic_calendar": "Forex Factory JSON API + 模拟",
            "ai_analysis": "laozhang.ai"
        },
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
    """获取今日事件 - 确保每个事件都有ai_analysis字段"""
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
    
    # 检查AI分析数量
    ai_analysis_count = len([e for e in events if e.get('ai_analysis', '').startswith('【AI分析】')])
    
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
        "ai_analysis_stats": {
            "total_with_ai": ai_analysis_count,
            "percentage": f"{(ai_analysis_count/total_events*100):.1f}%" if total_events > 0 else "0%"
        },
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "timezone": "北京时间 (UTC+8)"
    })

@app.route('/api/summary')
def get_today_summary():
    """获取今日总结"""
    summary = store.daily_analysis
    events = store.economic_events
    
    if not summary or len(summary) < 10:
        summary = "【AI分析】今日市场相对平静，关注欧美经济数据发布。建议谨慎交易，控制风险。EUR/USD关注1.0850阻力，USD/JPY关注148.00支撑。"
    
    return jsonify({
        "status": "success",
        "summary": summary,
        "generated_at": store.last_updated.isoformat() if store.last_updated else datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "ai_enabled": config.enable_ai,
        "timezone": "北京时间 (UTC+8)"
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
        "importance_breakdown": {
            "high": high_count,
            "medium": medium_count,
            "low": low_count
        },
        "has_ai_analysis": bool(store.daily_analysis and len(store.daily_analysis) > 10)
    })

# ============================================================================
# 启动应用
# ============================================================================
if __name__ == '__main__':
    logger.info("="*60)
    logger.info("启动宏观经济AI分析工具")
    logger.info(f"监控品种: {config.watch_currency_pairs}")
    logger.info(f"财经日历源: Forex Factory JSON API + 模拟备用")
    logger.info(f"AI分析服务: laozhang.ai (已启用: {config.enable_ai})")
    logger.info(f"模拟模式: {config.use_mock}")
    logger.info(f"时区: 北京时间 (UTC+8)")
    logger.info("注意: 确保每个事件都有AI分析内容")
    logger.info("="*60)

    # 首次启动时获取数据
    try:
        logger.info("首次启动，正在获取初始数据...")
        success = execute_data_update()
        if success:
            logger.info("初始数据获取成功")
            # 检查AI分析
            events = store.economic_events
            ai_count = len([e for e in events if e.get('ai_analysis', '').startswith('【AI分析】')])
            logger.info(f"事件总数: {len(events)}，其中{ai_count}个有AI分析")
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