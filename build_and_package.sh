#!/usr/bin/env bash
# 本机（git-bash/Linux）构建前端 + 打 tar 包
set -e
cd "$(dirname "$0")"
echo "[1/3] 安装并构建前端..."
cd frontend
npm install --no-audit --no-fund
npm run build
cd ..
echo "[2/3] 打包..."
rm -f fengkong-dist.tar.gz
tar -czf fengkong-dist.tar.gz \
  --exclude backend/.venv --exclude backend/data \
  --exclude "__pycache__" --exclude frontend/node_modules \
  backend deploy start.sh README.md frontend/dist
echo "[3/3] 完成：fengkong-dist.tar.gz"
