@echo off
rem 本机一键：构建前端 + 打 tar 包（上传服务器用）
setlocal
cd /d %~dp0
echo [1/3] 安装并构建前端...
cd frontend
call npm install --no-audit --no-fund
if errorlevel 1 goto :err
call npm run build
if errorlevel 1 goto :err
cd ..
echo [2/3] 打包...
if exist fengkong-dist.tar.gz del fengkong-dist.tar.gz
tar -czf fengkong-dist.tar.gz --exclude backend/.venv --exclude backend/data --exclude "backend/__pycache__" --exclude "backend/routers/__pycache__" --exclude "backend/tests/__pycache__" --exclude frontend/node_modules backend deploy start.sh README.md frontend/dist
if errorlevel 1 goto :err
echo [3/3] 完成：fengkong-dist.tar.gz （上传服务器解压后执行 bash deploy/deploy.sh）
exit /b 0
:err
echo 构建失败！
exit /b 1
