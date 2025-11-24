"""
启动脚本 - 生产环境使用
"""
from app import app, scheduler
import os

if __name__ == '__main__':
    # 生产环境配置
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)