"""
宏观经济事件分析工具 - 增强版后端服务 (集成实时数据)
支持Ziwox交易信号与Alpha Vantage汇率（含贵金属和比特币）
采用数据互补方案：当Alpha Vantage不支持某些品种时，从Ziwox信号中提取价格
"""

import os
import json
import logging
import time
import threading
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
# 配置管理 (API密钥已直接配置)
# ============================================================================
class Config:
    def __init__(self):
        # laozhang.ai / OpenAI 配置
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.openai_base_url = "https://api.laozhang.ai/v1"
        
        # Alpha Vantage 配置 - 用于实时汇率 (用户密钥已填入)
        self.alpha_vantage_key = os.getenv("ALPHA_VANTAGE_KEY", "2M66S0EB6ZMHO2ST")
        
        # Ziwox API 配置 - 用于交易信号数据 (用户密钥已填入)
        self.ziwox_api_key = os.getenv("ZIWOX_API_KEY", "B65991B99EB498AB")
        self.ziwox_api_url = "https://ziwox.com/terminal/services/API/V1/fulldata.php"
        
        # 模式开关
        self.use_mock = os.getenv("USE_MOCK_DATA", "false").lower() == "true"
        self.enable_ai = os.getenv("ENABLE_AI", "true").lower() == "true"
        
        # 重点关注的国家和货币
        self.watch_countries = ['US', 'EU', 'CN', 'JP', 'GB', 'AU', 'CA', 'CH']
        
        # 指定的货币对列表 (已重新加入XAUUSD, XAGUSD, BTCUSD)
        self.watch_currency_pairs = [
            'EURUSD', 'GBPUSD', 'USDCHF', 'USDCNH', 
            'USDJPY', 'AUDUSD', 'XAUUSD', 'XAGUSD', 'BTCUSD'
        ]
        
        # Ziwox API 需要小写参数 (全部转换为小写)
        self.ziwox_pairs = [pair.lower() for pair in self.watch_currency_pairs]
        
        # 为Alpha Vantage定义特殊品种的映射关系（from_currency -> to_currency）
        self.av_special_pairs = {
            'XAUUSD': ('XAU', 'USD'),
            'XAGUSD': ('XAG', 'USD'),
            'BTCUSD': ('BTC', 'USD')
        }
        
        # 货币与国家映射 (新增贵金属和加密货币)
        self.currency_to_country = {
            'USD': 'US', 'EUR': 'EU', 'CNY': 'CN', 'CNH': 'CN',
            'JPY': 'JP', 'GBP': 'GB', 'AUD': 'AU', 
            'CAD': 'CA', 'CHF': 'CH', 'XAU': 'GLOBAL', 
            'XAG': 'GLOBAL', 'BTC': 'CRYPTO'
        }

config = Config()

# ============================================================================
# 数据存储
# ============================================================================
class DataStore:
    def __init__(self):
        self.market_signals = []  # 存储从Ziwox获取的交易信号
        self.forex_rates = {}     # 存储从Alpha Vantage获取的实时汇率
        self.summary = ""
        self.last_updated = None
    
    def update_all(self, signals, forex_rates, summary):
        self.market_signals = signals
        self.forex_rates = forex_rates
        self.summary = summary
        self.last_updated = datetime.now()
    
    def get_market_signals(self):
        return self.market_signals
    
    def get_forex_rates(self):
        return self.forex_rates
    
    def get_summary(self):
        return self.summary

store = DataStore()

# ============================================================================
# 实时数据获取模块 (增强版，支持贵金属和比特币，采用数据互补方案)
# ============================================================================
def fetch_forex_rates_alpha_vantage(ziwox_signals=[]):
    """
    从Alpha Vantage获取实时汇率，失败时尝试从Ziwox信号补充。
    参数 ziwox_signals: 可选的Ziwox信号列表，用于补充缺失数据。
    """
    if not config.alpha_vantage_key:
        logger.warning("Alpha Vantage密钥为空，跳过汇率获取")
        return {}

    rates = {}
    logger.info(f"开始从Alpha Vantage获取 {len(config.watch_currency_pairs)} 个品种汇率...")

    try:
        fx = ForeignExchange(key=config.alpha_vantage_key)

        for pair in config.watch_currency_pairs:
            # 1. 尝试从Alpha Vantage获取
            try:
                if pair in config.av_special_pairs:
                    from_cur, to_cur = config.av_special_pairs[pair]
                    logger.info(f"  正在从Alpha Vantage获取特殊品种 {pair}...")
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
                    # Alpha Vantage返回了数据但没有汇率字段
                    logger.warning(f"    Alpha Vantage 未返回 {pair} 的有效汇率")
                    # 标记为获取失败，后续尝试补充
                    raise ValueError(f"Alpha Vantage returned no rate for {pair}")

                time.sleep(0.3)

            except Exception as e:
                # 2. Alpha Vantage 获取失败，尝试从 Ziwox 信号补充
                logger.warning(f"    Alpha Vantage 获取 {pair} 失败: {str(e)[:100]}")
                supplement_success = False

                if ziwox_signals:
                    for signal in ziwox_signals:
                        if signal.get('pair') == pair:
                            try:
                                last_price = float(signal.get('last_price', 0))
                                if last_price > 0:
                                    rates[pair] = {
                                        'rate': last_price,
                                        'bid': last_price * 0.999,  # 简单模拟买卖价
                                        'ask': last_price * 1.001,
                                        'last_refreshed': signal.get('fetched_at', datetime.now().isoformat()),
                                        'source': 'Ziwox (估算)',
                                        'note': '价格取自Ziwox市场信号Last Price字段'
                                    }
                                    logger.info(f"    ↳ 已从Ziwox信号补充 {pair}: {rates[pair]['rate']}")
                                    supplement_success = True
                                    break
                            except (ValueError, TypeError) as conv_err:
                                logger.warning(f"      无法转换Ziwox价格: {conv_err}")
                                continue

                if not supplement_success:
                    logger.warning(f"    无法为 {pair} 获取任何汇率数据")
                    
        logger.info(f"汇率获取完成，共得到 {len(rates)} 个品种数据")
        return rates

    except Exception as e:
        logger.error(f"Alpha Vantage API整体调用失败: {e}")
        return {}


def fetch_market_signals_ziwox():
    """
    从Ziwox API获取市场交易信号数据。
    已更新：支持所有货币对，包括转为小写的贵金属和比特币对。
    """
    if not config.ziwox_api_key:
        logger.error("Ziwox API密钥为空")
        return []
    
    all_signals = []
    
    for pair in config.ziwox_pairs:  # 这里已经是完整的小写列表
        try:
            # 构建请求URL和参数
            params = {
                'expn': 'ziwoxuser',
                'apikey': config.ziwox_api_key,
                'apitype': 'json',
                'pair': pair  # 确保pair是小写，如 xauusd, btcusd
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
                
                # 根据实际响应，返回的是一个列表，里面包含一个字典
                if isinstance(data_list, list) and len(data_list) > 0:
                    raw_data = data_list[0]
                    
                    # 构建标准化的市场信号对象
                    signal = {
                        'pair': pair.upper(),
                        'last_price': raw_data.get('Last Price', 'N/A'),
                        'base_currency': raw_data.get('Base', ''),
                        'quote_currency': raw_data.get('Quote', ''),
                        'fundamental_bias': raw_data.get('Fundamental Bias', 'Neutral'),
                        'fundamental_power': raw_data.get('Fundamental Power', '--'),
                        'ai_bullish_forecast': raw_data.get('AI Bullish Forecast', '50'),  # AI看涨预测百分比
                        'ai_bearish_forecast': raw_data.get('AI Bearish Forecast', '50'),  # AI看跌预测百分比
                        'd1_trend': raw_data.get('D1 Trend', 'NEUTRAL'),  # 日线趋势
                        'd1_rsi': raw_data.get('D1 RSI', '50'),
                        'retail_long_ratio': raw_data.get('Retail Long Ratio', '50%'),
                        'retail_short_ratio': raw_data.get('Retail Short Ratio', '50%'),
                        'support_levels': raw_data.get('supports', '').split(),  # 支撑位列表
                        'resistance_levels': raw_data.get('resistance', '').split(),  # 阻力位列表
                        'pivot_points': raw_data.get('pivot', '').split(),  # 枢轴点
                        'risk_sentiment': raw_data.get('Risk Sentiment', 'Neutral'),
                        'source': 'Ziwox',
                        'fetched_at': datetime.now().isoformat()
                    }
                    all_signals.append(signal)
                    logger.info(f"  成功解析 {pair.upper()} 的市场信号")
                else:
                    logger.warning(f"  {pair.upper()} 的响应数据格式不符预期或为空列表")
                    
            else:
                logger.warning(f"  请求 {pair.upper()} 数据失败，状态码: {response.status_code}")
            
            # 请求间隔，避免过快
            time.sleep(0.5)
                
        except requests.exceptions.Timeout:
            logger.error(f"  请求 {pair} 数据超时")
        except json.JSONDecodeError:
            logger.error(f"  解析 {pair} 的JSON响应失败，响应文本: {response.text[:200] if response else '无响应'}")
        except Exception as e:
            logger.error(f"  获取 {pair} 数据时出错: {e}")
    
    logger.info(f"Ziwox市场信号获取完成，共得到 {len(all_signals)} 个货币对数据")
    return all_signals


def fetch_real_time_data():
    """
    并行获取实时汇率和市场信号 (采用顺序执行以确保数据互补)
    """
    signals_result = []
    forex_rates_result = {}
    
    def get_signals():
        nonlocal signals_result
        if not config.use_mock:
            signals_result = fetch_market_signals_ziwox()
    
    def get_forex():
        nonlocal forex_rates_result
        # 将已获取的Ziwox信号作为参数传入，用于补充缺失汇率
        forex_rates_result = fetch_forex_rates_alpha_vantage(ziwox_signals=signals_result)
    
    # 为了数据互补，这里需要先获取信号，再获取汇率
    # 1. 先启动信号获取
    thread_signals = threading.Thread(target=get_signals)
    thread_signals.start()
    thread_signals.join()  # 等待信号获取完成
    
    # 2. 再启动汇率获取（此时signals_result已就绪）
    thread_forex = threading.Thread(target=get_forex)
    thread_forex.start()
    thread_forex.join()
    
    return signals_result, forex_rates_result


# ============================================================================
# AI分析模块 (增强版，适配新加入的贵金属和加密货币)
# ============================================================================
def generate_ai_analysis(signal, forex_rates):
    """
    为每个货币对的市场信号生成AI分析。
    增强：针对贵金属(XAU, XAG)和加密货币(BTC)调整分析视角。
    """
    if not config.enable_ai or not config.openai_api_key:
        return "AI分析功能未启用"
    
    try:
        pair = signal.get('pair', '')
        current_rate = forex_rates.get(pair, {}).get('rate', 'N/A') if forex_rates else 'N/A'
        
        # 根据品种类型调整分析侧重点
        analysis_focus = ""
        if pair.startswith('XAU') or pair.startswith('XAG'):
            analysis_focus = "（此为贵金属，分析时请额外关注全球通胀预期、美元实际利率、央行购金动态及工业需求等因素）"
        elif pair.startswith('BTC'):
            analysis_focus = "（此为加密货币，分析时请额外关注全球监管动向、主流机构 adoption、市场风险偏好及区块链网络活动等因素）"
        
        # 添加数据来源说明
        data_source_note = ""
        if pair in ['XAUUSD', 'XAGUSD']:
            # 检查该品种的汇率数据来源
            pair_source = forex_rates.get(pair, {}).get('source', '')
            if 'Ziwox' in pair_source:
                data_source_note = f" (注：当前价格数据来源于Ziwox市场信号分析，非直接汇率报价)"
        
        # 构建详细的提示词
        prompt = f"""作为资深交易员，请综合分析以下市场信号并提供交易洞察：

货币对: {pair} {analysis_focus}{data_source_note}
当前汇率: {current_rate}
最后报价: {signal.get('last_price', 'N/A')}
---
核心市场信号:
1. 基本面偏向: {signal.get('fundamental_bias', 'N/A')} (强度: {signal.get('fundamental_power', 'N/A')})
2. AI预测: 看涨 {signal.get('ai_bullish_forecast', '50')}% | 看跌 {signal.get('ai_bearish_forecast', '50')}%
3. 日线趋势: {signal.get('d1_trend', 'N/A')} (RSI: {signal.get('d1_rsi', 'N/A')})
4. 散户情绪: 多头 {signal.get('retail_long_ratio', 'N/A')} | 空头 {signal.get('retail_short_ratio', 'N/A')}
5. 风险情绪: {signal.get('risk_sentiment', 'N/A')}
---
关键技术位:
• 支撑位: {', '.join(signal.get('support_levels', ['N/A'])[:3])}
• 阻力位: {', '.join(signal.get('resistance_levels', ['N/A'])[:3])}
• 枢轴点: {signal.get('pivot_points', ['N/A'])[0] if signal.get('pivot_points') else 'N/A'}
---
请提供简洁的交易分析:
1. 多空方向判断及理由（综合以上信号及品种特性）
2. 关键入场位和止损位建议
3. 短期（1-3天）目标位
4. 主要风险提示

要求：专业、直接、具有可操作性，适合专业交易员参考。"""
        
        # 调用AI API
        response = requests.post(
            f"{config.openai_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {config.openai_api_key}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "你是专业交易员，擅长结合技术面、基本面和市场情绪进行综合分析，对贵金属和加密货币也有深入理解。"},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 450,
                "temperature": 0.3
            },
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            logger.error(f"AI API错误: {response.status_code}")
            return f"AI分析生成失败 (HTTP {response.status_code})"
            
    except Exception as e:
        logger.error(f"生成AI分析时出错: {e}")
        return "分析生成异常"


def generate_daily_summary(signals, forex_rates):
    """基于所有货币对的市场信号生成每日总结，涵盖外汇、贵金属和加密货币"""
    
    if not config.enable_ai or not config.openai_api_key:
        return "AI总结功能未启用"
    
    try:
        if not signals:
            return "暂无市场信号数据，无法生成总结"
        
        # 按资产类别分类
        forex_signals = [s for s in signals if len(s['pair']) == 6 and not s['pair'].startswith(('XAU', 'XAG', 'BTC'))]
        metal_signals = [s for s in signals if s['pair'].startswith(('XAU', 'XAG'))]
        crypto_signals = [s for s in signals if s['pair'].startswith('BTC')]
        
        # 准备市场概况
        market_overview = []
        for signal in signals[:6]:  # 展示前6个主要品种
            pair = signal.get('pair', '')
            rate = forex_rates.get(pair, {}).get('rate', 'N/A') if forex_rates else 'N/A'
            trend = signal.get('d1_trend', 'NEUTRAL')
            market_overview.append(f"{pair} {rate} ({trend})")
        
        prompt = f"""基于当前全球市场信号生成交易日报：

整体概况:
{chr(10).join(market_overview)}

资产类别分布:
- 外汇主要货币对: {len(forex_signals)} 个
- 贵金属: {len(metal_signals)} 个 (XAU, XAG)
- 加密货币: {len(crypto_signals)} 个 (BTC)

数据来源: Ziwox市场信号 + Alpha Vantage实时汇率
---
请生成涵盖外汇、贵金属和加密货币的今日市场交易日报，格式:

📊 市场总览: [阐述跨资产类别的整体格局与资金流向]

🎯 重点机会:
1. 外汇 ({forex_signals[0].get('pair') if forex_signals else 'N/A'}): [核心逻辑与关键位]
2. 贵金属 ({metal_signals[0].get('pair') if metal_signals else 'N/A'}): [核心驱动与关键位]
3. 加密货币 ({crypto_signals[0].get('pair') if crypto_signals else 'N/A'}): [核心逻辑与关键位]

⚠️ 跨市场风险提示: [指出可能联动影响各大类资产的主要风险]

💡 本日多资产策略: [提出1-2条可涵盖不同资产类别的交易思路或配置建议]

要求：视野宏观、逻辑清晰、直接服务于当日交易决策。"""
        
        response = requests.post(
            f"{config.openai_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {config.openai_api_key}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "你是顶尖的宏观策略师，擅长从跨资产视角（外汇、贵金属、加密货币）提供清晰、直接、可执行的每日交易指导。"},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 600,
                "temperature": 0.4
            },
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            return "【AI总结生成失败】"
            
    except Exception as e:
        logger.error(f"生成每日总结时出错: {e}")
        return "总结生成异常"


# ============================================================================
# 定时任务
# ============================================================================
scheduler = BackgroundScheduler()

def scheduled_update():
    """定时更新任务 - 适配新版数据格式"""
    try:
        logger.info("="*60)
        logger.info(f"开始执行实时数据更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 1. 获取实时数据
        signals, forex_rates = fetch_real_time_data()
        
        # 2. 为每个货币对信号生成AI分析
        signals_with_analysis = []
        for signal in signals:
            analysis = generate_ai_analysis(signal, forex_rates)
            signal_with_analysis = {
                **signal,
                "ai_analysis": analysis,
                "id": hash(f"{signal.get('pair', '')}{datetime.now().timestamp()}")
            }
            signals_with_analysis.append(signal_with_analysis)
        
        # 3. 生成每日总结
        summary = generate_daily_summary(signals_with_analysis, forex_rates) if signals_with_analysis else "暂无足够数据生成总结"
        
        # 4. 存储数据
        store.update_all(signals_with_analysis, forex_rates, summary)
        
        logger.info(f"更新完成: {len(signals_with_analysis)}个交易品种信号, {len(forex_rates)}个实时汇率")
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"定时任务失败: {e}", exc_info=True)

# 定时任务配置：每小时更新一次（因为市场信号变化较快）
scheduler.add_job(scheduled_update, 'interval', minutes=60)
scheduler.add_job(scheduled_update, 'cron', hour=9, minute=0)  # 每日开盘前
scheduler.add_job(scheduled_update, 'cron', hour=16, minute=0) # 伦敦收盘后

scheduler.start()


# ============================================================================
# Flask路由 (适配新的数据格式)
# ============================================================================
@app.route('/')
def index():
    return jsonify({
        "status": "running",
        "data_source": "real-time" if not config.use_mock else "mock",
        "sources": ["Ziwox Market Signals", "Alpha Vantage Forex"],
        "supported_pairs": config.watch_currency_pairs,
        "last_updated": store.last_updated.isoformat() if store.last_updated else None,
        "endpoints": {
            "market_signals": "/api/market/signals",
            "forex": "/api/forex/rates",
            "summary": "/api/summary/today",
            "refresh": "/api/refresh"
        }
    })


@app.route('/api/market/signals')
def get_market_signals():
    """获取市场信号与AI分析"""
    signals = store.get_market_signals()
    if not signals:
        scheduled_update()
        signals = store.get_market_signals()
    
    return jsonify({
        "status": "success",
        "count": len(signals),
        "data": signals,
        "generated_at": datetime.now().isoformat()
    })


@app.route('/api/forex/rates')
def get_forex_rates():
    """获取实时汇率（包含贵金属和加密货币）"""
    rates = store.get_forex_rates()
    return jsonify({
        "status": "success",
        "data": rates,
        "currencies": config.watch_currency_pairs,
        "last_updated": store.last_updated.isoformat() if store.last_updated else None
    })


@app.route('/api/summary/today')
def get_today_summary():
    """获取AI每日总结"""
    summary = store.get_summary()
    if not summary:
        scheduled_update()
        summary = store.get_summary()
    
    return jsonify({
        "status": "success",
        "summary": summary,
        "generated_at": datetime.now().isoformat()
    })


@app.route('/api/refresh', methods=['POST'])
def refresh_data():
    """手动刷新数据"""
    scheduled_update()
    return jsonify({
        "status": "success",
        "message": "数据刷新已触发",
        "last_updated": store.last_updated.isoformat() if store.last_updated else None
    })


# ============================================================================
# 启动应用
# ============================================================================
if __name__ == '__main__':
    logger.info("启动宏观经济AI分析工具 (增强版 - 支持贵金属与加密货币)...")
    logger.info(f"数据模式: {'实时数据' if not config.use_mock else '模拟模式'}")
    logger.info(f"监控品种: {config.watch_currency_pairs}")
    logger.info(f"数据源: Ziwox (市场信号) + Alpha Vantage (实时汇率与贵金属/加密货币)")
    
    # 首次启动时获取数据
    scheduled_update()
    
    app.run(
        host='0.0.0.0',
        port=int(os.getenv('FLASK_PORT', 5000)),
        debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    )