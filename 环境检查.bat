@echo off
chcp 65001 >nul
title 环境检测工具
color 0E

echo.
echo ══════════════════════════════════════════
echo       煤炉助手 - 环境检测工具
echo ══════════════════════════════════════════
echo.
echo 正在检测您的电脑环境...
echo.

:: 检测 Python
set PYTHON_OK=0
python --version >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYVER=%%i
    echo [✓] Python 已安装: %PYVER%
    set PYTHON_OK=1
) else (
    echo [✗] Python 未安装或未添加到 PATH
    echo     请访问 https://www.python.org/downloads/ 安装 Python 3.11
)

echo.

:: 检测 Node.js
set NODE_OK=0
node --version >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=1" %%i in ('node --version') do set NODEVER=%%i
    echo [✓] Node.js 已安装: %NODEVER%
    set NODE_OK=1
) else (
    echo [✗] Node.js 未安装
    echo     请访问 https://nodejs.org/ 安装 LTS 版本
)

echo.

:: 检测 uv
set UV_OK=0
uv --version >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=2" %%i in ('uv --version') do set UVVER=%%i
    echo [✓] uv 已安装: %UVVER%
    set UV_OK=1
) else (
    echo [✗] uv 未安装
    echo     请在命令提示符运行: powershell -Command "irm https://astral.sh/uv/install.ps1 | iex"
)

echo.
echo ══════════════════════════════════════════

:: 总结
if %PYTHON_OK% equ 1 if %NODE_OK% equ 1 if %UV_OK% equ 1 (
    echo.
    echo ★★★ 恭喜！所有环境都已就绪！★★★
    echo.
    echo 现在可以双击 "一键启动.bat" 开始使用了！
    goto :good_end
) else (
    echo.
    echo ⚠ 检测到以下问题需要解决：
    echo.
    
    if %PYTHON_OK% equ 0 (
        echo   ❌ Python 未安装
        echo      → 下载地址: https://www.python.org/downloads/
        echo      → 安装时务必勾选 "Add Python to PATH"！
        echo.
    )
    
    if %NODE_OK% equ 0 (
        echo   ❌ Node.js 未安装
        echo      → 下载地址: https://nodejs.org/
        echo      → 选择 LTS 版本（长期支持版）
        echo      → 安装完成后需要重启电脑
        echo.
    )
    
    if %UV_OK% equ 0 (
        echo   ❌ uv 未安装
        echo      → 打开命令提示符（Win+R 输入 cmd 回车）
        echo      → 粘贴并回车:
        echo        powershell -Command "irm https://astral.sh/uv/install.ps1 | iex"
        echo.
    )
    
    echo 解决以上问题后重新运行此工具检测。
    goto :bad_end
)

:good_end
echo.
echo 按任意键打开部署指南...
pause >nul
start "" "网页版部署指南.txt"
exit /b 0

:bad_end
echo.
echo 按任意键打开详细安装指南...
pause >nul
start "" "网页版部署指南.txt"
exit /b 1