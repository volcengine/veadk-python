#!/bin/bash

# 兼容源码部署到faas & 镜像部署到faas
pip install -r requirements.txt

HOST="0.0.0.0"
PORT="${_FAAS_RUNTIME_PORT:-8000}"

export SERVER_HOST=$HOST
export SERVER_PORT=$PORT

# 设置环境变量
export FLASK_APP=app.py
export FLASK_ENV=production

# 初始化数据库
python init_db.py

echo "Starting Web application..."
# 启动应用，使用生产服务器配置
exec python -m gunicorn -w 4 -b $SERVER_HOST:$SERVER_PORT app:app
