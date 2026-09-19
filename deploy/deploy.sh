#!/usr/bin/env bash
# 服务器端部署脚本：创建 venv 并安装依赖（清华镜像加速）
# 用法：把整包上传解压后，在包目录执行  bash deploy/deploy.sh
set -e
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
echo "使用 Python: $($PY --version 2>&1)"
cd backend
if [ ! -d .venv ]; then
  echo "创建虚拟环境 .venv ..."
  "$PY" -m venv .venv
fi
./.venv/bin/pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
./.venv/bin/pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
echo ""
echo "依赖安装完成。后续步骤："
echo "  1. 编辑 deploy/fengkong.service，确认 WorkingDirectory/ExecStart 路径与 APP_PASSWORD"
echo "  2. sudo cp deploy/fengkong.service /etc/systemd/system/"
echo "  3. sudo systemctl daemon-reload && sudo systemctl enable --now fengkong"
echo "  4. 访问 http://服务器IP:8000"
