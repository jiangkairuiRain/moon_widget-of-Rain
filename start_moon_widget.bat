@echo off
chcp 65001 > nul
title Moon Widget Launcher

REM 切换到脚本所在目录
cd /d "%~dp0"

REM 检查pythonw是否可用
where pythonw >nul 2>nul
if %errorlevel% equ 0 (
    echo 使用pythonw启动月球位置小部件...
    start "" pythonw moon_widget.py
) else (
    echo pythonw不可用，尝试使用python...
    start "" python moon_widget.py
)

REM 如果以上都失败，显示错误信息
if %errorlevel% neq 0 (
    echo.
    echo 启动失败，请确保已安装Python并配置环境变量
    echo 按任意键退出...
    pause >nul
)
