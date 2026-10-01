@echo off
chcp 65001 >nul
title 煤炉助手 - 打包工具
color 0B

echo ════════════════════════════════════════════════════════
echo              煤炉助手 - 打包发布工具
echo ════════════════════════════════════════════════════════
echo.
echo 请选择操作:
echo.
echo   [1] 打包桌面版 EXE（单文件，直接发给客户）★推荐
echo   [2] 打包网页版静态文件（用于服务器部署）
echo   [3] 全部打包
echo   [4] 清理缓存
echo   [0] 退出
echo.
set /p choice=请输入选项编号 (0-4):

if "%choice%"=="1" goto build_desktop
if "%choice%"=="2" goto build_web
if "%choice%"=="3" goto build_all
if "%choice%"=="4" goto clean
if "%choice%"=="0" goto end

echo [错误] 无效选项！
pause
goto end

:build_desktop
echo.
echo ═══════════════════════════════════════════
echo   正在打包单文件 EXE（包含所有依赖）
echo ═══════════════════════════════════════════
echo.
echo [提示] 这个过程需要 5-15 分钟...
echo [提示] 生成的EXE可以直接发给客户双击使用
echo [提示] 不需要客户安装任何东西！
echo.
uv run python build.py --desktop
echo.
if %errorlevel% equ 0 (
    echo.
    echo ★★★ 打包成功！★★★
    echo.
    echo 发送给客户的步骤：
    echo   1. 找到 dist\二手监控助手.exe 文件
    echo   2. 直接把这个EXE发给客户
    echo   3. 客户双击就能运行，不需要其他任何文件！
    echo.
)
goto end

:build_web
echo.
echo [信息] 开始打包网页版 ...
uv run python build.py --web
goto end

:build_all
echo.
echo [信息] 开始全部打包 ...
uv run python build.py --all
goto end

:clean
echo.
echo [信息] 清理构建缓存 ...
uv run python build.py --clean
echo [完成] 缓存已清理！
goto end

:end
echo.
pause