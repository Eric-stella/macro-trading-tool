"""
宏观经济事件分析工具 - 后端服务
支持本地开发和生产环境
"""

import os
import json
import logging
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
import requests
import tradingeconomics as te

# 创建Flask应用
app = Flask(__name__)
CORS(app)  # 允许跨域请求

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# 配置管理
# ──────────────────────────────────────────────────────────────

class Config:
    """配置管理器"""
    def __init__(self):
        # laozhang.ai配置
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.openai_base_url = "https://api.laozhang.ai/v1"
        
        # TradingEconomics配置
        self.te_key = os.getenv("TRADINGECONOMICS_KEY", "guest:guest")
        
        # 开发模式
        self.use_mock = os.getenv("USE_MOCK_DATA", "true").lower() == "true"
        self.enable_ai = os.getenv("ENABLE_AI", "true").lower() == "true"
        
        # 货币对映射
        self.currency_pairs = {
            'USD': ['US', '美国'],
            'EUR': ['EU', '欧元区', '德国', '法国', '意大利'],
            'CNY': ['CN', '中国'],
            'JPY': ['JP', '日本'],
            'GBP': ['GB', '英国'],
            'AUD': ['AU', '澳大利亚'],
            'CAD': ['CA', '加拿大'],
            'CHF': ['CH', '瑞士']
        }

config = Config()

# ──────────────────────────────────────────────────────────────
# 数据存储（内存数据库，生产环境建议用SQLite）
# ──────────────────────────────────────────────────────────────

class DataStore:
    """内存数据存储"""
    def __init__(self):
        self.events = []
        self.summary = ""
        self.last_updated = None
    
    def update_events(self, events):
        self.events = events
        self.last_updated = datetime.now()
    
    def update_summary(self, summary):
        self.summary = summary
    
    def get_events(self):
        return self.events
    
    def get_summary(self):
        return self.summary

store = DataStore()

# ──────────────────────────────────────────────────────────────
# Mock数据生成器（API未就绪时使用）
# ──────────────────────────────────────────────────────────────

class MockDataGenerator:
    """模拟数据生成器"""
    
    def __init__(self):
        self.sample_events = [
            {
                "time": "20:30",
                "country": "US",
                "name": "CPI月率",
                "forecast": "0.3%",
                "previous": "0.4%",
                "importance": 3,
                "currency": "USD",
                "actual": None
            },
            {
                "time": "15:00",
                "country": "EU",
                "name": "ZEW经济景气指数",
                "forecast": "-20.5",
                "previous": "-22.0",
                "importance": 2,
                "currency": "EUR",
                "actual": None
            },
            {
                "time": "21:00",
                "country": "US",
                "name": "美联储利率决议",
                "forecast": "5.5%",
                "previous": "5.5%",
                "importance": 3,
                "currency": "USD",
                "actual": None
            },
            {
                "time": "07:50",
                "country": "JP",
                "name": "GDP年率",
                "forecast": "1.2%",
                "previous": "1.0%",
                "importance": 2,
                "currency": "JPY",
                "actual": None
            }
        ]
        
        self.sample_ai_analyses = [
            "【AI分析】通胀数据超预期可能提振美元，美元指数或测试105.50阻力位。若数据强劲，EUR/USD可能跌向1.0750。",
            "【AI分析】经济景气度改善利好欧元，但幅度有限。预计影响中性，EUR/USD或在1.0800-1.0850区间震荡。",
            "【AI分析】利率决议按兵不动概率大，市场焦点在鲍威尔讲话。若鹰派表态，美元有望走强。",
            "【AI分析】GDP数据对日本央行政策预期影响有限，预计USD/JPY波动不大，维持150-151区间。"
        ]
    
    def generate_events(self):
        """生成今日模拟事件"""
        logger.info("使用模拟数据模式")
        return self.sample_events
    
    def generate_ai_analysis(self, event):
        """生成模拟AI分析"""
        # 根据事件名称返回对应的模拟分析
        event_name = event.get('name', '')
        for i, sample in enumerate(self.sample_events):
            if event_name in sample['name']:
                return self.sample_ai_analyses[i]
        
        # 默认分析
        return f"【模拟分析】{event_name}可能对市场产生影响，建议关注实际值与预期差异。"

mock_gen = MockDataGenerator()

# ──────────────────────────────────────────────────────────────
# 数据抓取模块
# ──────────────────────────────────────────────────────────────

def fetch_from_tradingeconomics():
    """从TradingEconomics抓取数据"""
    try:
        logger.info(f"正在连接TradingEconomics: {config.te_key[:10]}...")
        
        # 登录
        te.login(config.te_key)
        
        # 获取今日日历
        today = datetime.now().strftime('%Y-%m-%d')
        
        # 获取高重要性事件
        events = te.getCalendarData(
            country='all',
            importance='high',
            output_type='df'
        )
        
        # 转换为dict
        events_data = events.to_dict('records')
        
        logger.info(f"成功获取 {len(events_data)} 个事件")
        return events_data
        
    except Exception as e:
        logger.error(f"TradingEconomics API失败: {e}")
        if config.use_mock:
            logger.info("切换到模拟数据模式")
            return mock_gen.generate_events()
        else:
            raise

def fetch_today_events():
    """获取今日事件（自动切换模式）"""
    if config.use_mock:
        return mock_gen.generate_events()
    else:
        return fetch_from_tradingeconomics()

# ──────────────────────────────────────────────────────────────
# AI分析模块
# ──────────────────────────────────────────────────────────────

def generate_ai_analysis(event):
    """为单个事件生成AI分析"""
    
    # 如果AI被禁用或key未配置，返回模拟分析
    if not config.enable_ai or not config.openai_api_key or 'mock' in config.openai_api_key:
        logger.info("AI分析处于模拟模式")
        return mock_gen.generate_ai_analysis(event)
    
    try:
        logger.info(f"正在为事件生成AI分析: {event['name']}")
        
        prompt = f"""
        你是一个资深外汇宏观分析师。请分析以下经济事件对货币对的潜在影响：

        事件: {event['name']}
        国家: {event['country']}
        预期值: {event.get('forecast', 'N/A')}
        前值: {event.get('previous', 'N/A')}
        重要性: {'高' if event.get('importance', 3) >= 3 else '中'}

        请提供简洁专业的分析（不超过150字）：
        1. 该事件可能如何影响{event.get('currency', '相关货币')}？
        2. 如果实际值>预期值，市场可能如何反应？
        3. 如果实际值<预期值，市场可能如何反应？
        4. 给出1-2个关键支撑/阻力位

        要求: 专业简洁，适合交易员快速阅读。
        """
        
        response = requests.post(
            f"{config.openai_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {config.openai_api_key}"},
            json={
                "model": "gpt-4o-mini",  # 更便宜的模型
                "messages": [
                    {"role": "system", "content": "你是一个专业的外汇宏观分析师，擅长用简洁的语言分析经济事件对货币对的影响。"},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 250,
                "temperature": 0.3
            },
            timeout=30
        )
        
        if response.status_code == 200:
            analysis = response.json()['choices'][0]['message']['content']
            logger.info("AI分析生成成功")
            return analysis
        else:
            logger.error(f"AI API错误: {response.status_code}")
            return mock_gen.generate_ai_analysis(event)
            
    except Exception as e:
        logger.error(f"AI分析失败: {e}")
        return mock_gen.generate_ai_analysis(event)

def generate_daily_summary(events):
    """生成每日AI总结"""
    
    # 如果AI被禁用，返回模拟总结
    if not config.enable_ai or not config.openai_api_key or 'mock' in config.openai_api_key:
        return """【模拟总结】今日重点关注欧美经济数据。美国CPI将影响美联储政策预期，预计市场波动加剧。欧元区ZEW指数显示经济疲软。美元指数或维持强势，非美货币承压。建议关注关键支撑位。"""

    try:
        logger.info(f"正在生成每日总结，事件数: {len(events)}")
        
        event_summaries = " | ".join([
            f"{e.get('country', '')}-{e.get('name', '')}" 
            for e in events
        ])
        
        prompt = f"""
        基于今日以下{len(events)}个宏观事件:
        {event_summaries}
        
        请生成一份每日外汇市场小结，格式:

        📈 市场主线: [一句话总结今日主题]
        
        🔥 焦点事件: [1-2个最重磅事件]
        
        💱 主要货币对展望:
        • 美元指数: [影响及关键位]
        • EUR/USD: [关键位]
        • USD/JPY: [关键位]
        • GBP/USD: [关键位]
        
        🎯 今日策略: [1条操作建议]
        
        要求: 简洁专业，适合交易员快速阅读，总字数不超过300字。
        """
        
        response = requests.post(
            f"{config.openai_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {config.openai_api_key}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "你是一个资深外汇策略师，擅长总结宏观事件对市场的综合影响。"},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 400
            },
            timeout=30
        )
        
        if response.status_code == 200:
            summary = response.json()['choices'][0]['message']['content']
            logger.info("每日总结生成成功")
            return summary
        else:
            logger.error("每日总结生成失败")
            return "【生成失败】使用昨日的总结作为参考。"
            
    except Exception as e:
        logger.error(f"每日总结失败: {e}")
        return "【生成失败】请检查API配置。"

# ──────────────────────────────────────────────────────────────
# 定时任务
# ──────────────────────────────────────────────────────────────

scheduler = BackgroundScheduler()

def scheduled_update():
    """定时更新任务"""
    try:
        logger.info("="*60)
        logger.info(f"开始执行定时任务: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 抓取事件
        events = fetch_today_events()
        
        # 为每个事件生成AI分析
        events_with_analysis = []
        for event in events:
            analysis = generate_ai_analysis(event)
            events_with_analysis.append({
                **event,
                "ai_analysis": analysis,
                "id": hash(f"{event.get('name', '')}{event.get('time', '')}")
            })
        
        # 存储数据
        store.update_events(events_with_analysis)
        
        # 生成总结
        if events_with_analysis:
            summary = generate_daily_summary(events_with_analysis)
            store.update_summary(summary)
        
        logger.info(f"任务完成，处理 {len(events_with_analysis)} 个事件")
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"定时任务失败: {e}")

# 添加定时任务（每天早上7点和晚上8点）
scheduler.add_job(scheduled_update, 'cron', hour=7, minute=0)
scheduler.add_job(scheduled_update, 'cron', hour=20, minute=0)

# 启动调度器
scheduler.start()

# ──────────────────────────────────────────────────────────────
# Flask路由
# ──────────────────────────────────────────────────────────────

@app.route('/')
def index():
    """根路径，返回服务状态"""
    return jsonify({
        "status": "running",
        "mode": "mock" if config.use_mock else "production",
        "ai_enabled": config.enable_ai,
        "last_updated": store.last_updated.isoformat() if store.last_updated else None,
        "endpoints": {
            "events": "/api/events/today",
            "summary": "/api/summary/today",
            "refresh": "/api/refresh",
            "status": "/api/status"
        }
    })

@app.route('/api/status')
def status():
    """服务状态检查"""
    return jsonify({
        "status": "healthy",
        "mode": "mock" if config.use_mock else "production",
        "events_count": len(store.get_events()),
        "ai_enabled": config.enable_ai,
        "last_updated": store.last_updated.isoformat() if store.last_updated else None
    })

@app.route('/api/events/today', methods=['GET'])
def get_today_events():
    """获取今日事件（带AI分析）"""
    try:
        events = store.get_events()
        
        # 如果没有数据，立即抓取
        if not events:
            scheduled_update()
            events = store.get_events()
        
        return jsonify({
            "status": "success",
            "data": events,
            "generated_at": datetime.now().isoformat(),
            "mode": "mock" if config.use_mock else "production"
        })
    except Exception as e:
        logger.error(f"获取事件失败: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/api/summary/today', methods=['GET'])
def get_today_summary():
    """获取今日AI总结"""
    try:
        summary = store.get_summary()
        
        # 如果没有总结，立即生成
        if not summary:
            events = fetch_today_events()
            summary = generate_daily_summary(events)
            store.update_summary(summary)
        
        return jsonify({
            "status": "success",
            "summary": summary,
            "generated_at": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"获取总结失败: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/api/refresh', methods=['POST'])
def refresh_data():
    """手动触发数据刷新"""
    try:
        logger.info("收到手动刷新请求")
        scheduled_update()
        return jsonify({
            "status": "success",
            "message": "数据已刷新"
        })
    except Exception as e:
        logger.error(f"刷新失败: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

# ──────────────────────────────────────────────────────────────
# 启动脚本
# ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    # 启动时初始化数据
    logger.info("正在启动宏观经济事件分析工具...")
    logger.info(f"当前模式: {'模拟数据' if config.use_mock else '真实API'}")
    logger.info(f"AI功能: {'已启用' if config.enable_ai else '模拟模式'}")
    
    # 首次启动抓取数据
    scheduled_update()
    
    # 启动Flask应用
    app.run(
        host='0.0.0.0',
        port=int(os.getenv('FLASK_PORT', 5000)),
        debug=True,  # 开发模式，热重载
        use_reloader=True
    )