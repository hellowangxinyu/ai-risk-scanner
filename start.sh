#!/usr/bin/env bash
# 本机/Linux 调试启动（需先构建过前端 frontend/dist）
set -e
cd "$(dirname "$0")/backend"
if [ -z "$APP_PASSWORD" ]; then export APP_PASSWORD=admin123; fi
if [ ! -d .venv ]; then
  echo "首次运行：创建虚拟环境并安装依赖..."
  "${PYTHON:-python3}" -m venv .venv
  ./.venv/bin/pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
fi
if [ ! -f ../frontend/dist/index.html ]; then
  echo "警告：未找到 frontend/dist，请先在 frontend 下执行 npm run build"
fi
echo "启动服务：http://127.0.0.1:8000"
exec ./.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
