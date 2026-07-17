@echo off
chcp 65001 >nul
cd /d "%~dp0backend"

echo.
echo ╔══════════════════════════════════════════╗
echo ║   🏭  智能制造调查问卷智能体              ║
echo ╚══════════════════════════════════════════╝
echo.

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.9+
    pause
    exit /b 1
)

:: 检查 .env 文件
if not exist ".env" (
    echo [提示] 未找到 .env 文件，从 .env.example 复制...
    copy .env.example .env >nul
    echo [提示] 请编辑 .env 文件，填入您的 LLM_API_KEY
    echo.
)

:: 安装依赖
echo [1/2] 安装依赖...
pip install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

:: 启动服务
echo.
echo [2/2] 启动服务...
echo.
python app.py

pause
