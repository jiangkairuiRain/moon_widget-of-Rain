@echo off
chcp 65001 > nul
title Moon Widget Launcher

REM 检查是否已经隐藏了窗口
if "%1"=="hidden" goto main

REM 第一次运行，使用VBScript隐藏窗口并重新启动
echo Set UAC = CreateObject("Shell.Application") > "%temp%\hidden.vbs"
echo UAC.ShellExecute "%~f0", "hidden", "", "runas", 0 >> "%temp%\hidden.vbs"
"%temp%\hidden.vbs"
exit /b

:main
REM 删除临时VBScript文件
if exist "%temp%\hidden.vbs" del "%temp%\hidden.vbs"

REM 切换到脚本所在目录
cd /d "%~dp0"

REM 检查pythonw是否可用
where pythonw >nul 2>nul
if %errorlevel% equ 0 (
    echo 使用pythonw启动月球位置小部件...
    pythonw moon_widget.py
) else (
    echo pythonw不可用，尝试使用python...
    python moon_widget.py
)

REM 如果以上都失败，显示错误信息
if %errorlevel% neq 0 (
    echo.
    echo 启动失败，请确保已安装Python并配置环境变量
    echo 按任意键退出...
    pause >nul
)