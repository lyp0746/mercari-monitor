@echo off
chcp 65001 >nul
title 煤炉助手 - 网页版一键启动
color 0A

echo ════════════════════════════════════════════════════════
echo           煤炉助手 - 网页版一键启动工具
echo ════════════════════════════════════════════════════════
echo.

:: 检查是否在正确的目录
if not exist "src\api\main.py" (
    echo [错误] 请将此文件放在项目根目录下运行！
    echo        当前目录: %cd%
    echo.
    pause
    exit /b 1
)

:: 第一步：检查并安装 uv
echo [步骤 1/4] 检查运行环境...
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [提示] 未检测到 uv (Python包管理器)
    echo [提示] 正在自动安装...
    echo.
    powershell -Command "irm https://astral.sh/uv/install.ps1 | iex"
    if %errorlevel% neq 0 (
        echo [错误] 安装失败！请手动安装：https://docs.astral.sh/uv/getting-started/installation/
        pause
        exit /b 1
    )
    echo [成功] uv 已安装！请重新运行此脚本。
    pause
    exit /b 0
)
echo [✓] 环境检查通过: uv 已安装

:: 第二步：创建虚拟环境并安装依赖
echo.
echo [步骤 2/4] 安装 Python 依赖（首次运行需要几分钟）...
if not exist ".venv" (
    echo [提示] 首次运行，正在创建虚拟环境...
    uv venv --python 3.11
)

call uv pip install -e ".[web]" --quiet
if %errorlevel% neq 0 (
    echo [错误] 依赖安装失败！
    pause
    exit /b 1
)
echo [✓] Python 依赖已就绪

:: 第三步：检查前端依赖
echo.
echo [步骤 3/4] 检查前端依赖...
if not exist "web\node_modules" (
    echo [提示] 首次运行，正在安装前端依赖（需要2-3分钟）...
    cd web
    call npm install
    cd ..
    if %errorlevel% neq 0 (
        echo [错误] 前端依赖安装失败！请确保已安装 Node.js: https://nodejs.org/
        pause
        exit /b 1
    )
)
echo [✓] 前端依赖已就绪

:: 第四步：启动服务
echo.
echo [步骤 4/4] 启动服务...
echo.
echo ════════════════════════════════════════════════════════
echo   正在启动后端服务 (API) 和前端界面...
echo   启动后会自动打开浏览器
echo   
echo   ★ 后端地址: http://localhost:8000
echo   ★ 前端地址: http://localhost:5173
echo   
echo   按 Ctrl+C 可以停止服务
echo ════════════════════════════════════════════════════════
echo.

:: 启动后端 API（后台运行）
start "Mercari-Monitor-API" cmd /c "uv run uvicorn src.api.main:app --reload --port 8000"

:: 等待API启动
timeout /t 3 /nobreak >nul

:: 启动前端开发服务器
start "Mercari-Monitor-Web" cmd /c "cd web && npm run dev"

:: 等待前端启动
timeout /t 5 /nobreak >nul

:: 打开浏览器
start http://localhost:5173

echo.
echo [✓] 服务已启动！
echo.
echo 如果浏览器没有自动打开，请手动访问:
echo   http://localhost:5173
echo.
echo 如需停止服务，关闭此窗口即可（或在任务管理器结束进程）
echo.

:: 保持窗口打开
pause