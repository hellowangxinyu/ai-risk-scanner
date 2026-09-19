@echo off
rem 本机 Windows 调试启动（需先构建过前端 frontend/dist）
setlocal
cd /d %~dp0backend
if "%APP_PASSWORD%"=="" set APP_PASSWORD=admin123
if not exist .venv (
  echo 首次运行：创建虚拟环境并安装依赖...
  py -3 -m venv .venv || goto :err
  .venv\Scripts\pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple || goto :err
)
if not exist ..\frontend\dist\index.html (
  echo 警告：未找到 frontend\dist，请先运行 build_and_package.bat 或在 frontend 下执行 npm run build
)
echo 启动服务：http://127.0.0.1:8000  （口令 %%APP_PASSWORD%%）
.venv\Scripts\uvicorn main:app --host 127.0.0.1 --port 8000
exit /b 0
:err
echo 启动失败！
pause
exit /b 1
