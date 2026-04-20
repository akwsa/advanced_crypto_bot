@echo off
title Crypto Trading Bot
echo ========================================
echo   Advanced Crypto Trading Bot
echo ========================================
echo.

:: Check if bot is already running
tasklist | findstr /i "python" >nul 2>&1
if %errorlevel% equ 0 (
    echo [!] Bot is already running!
    echo.
    choice /M "Do you want to restart"
    if errorlevel 2 goto :eof
    
    echo [~] Stopping existing bot...
    for /f "tokens=2" %%i in ('tasklist /fi "imagename eq python.exe" /fo list ^| findstr "PID:"') do (
        echo [~] Killing PID: %%i
        taskkill /F /PID %%i >nul 2>&1
    )
    echo [+] Existing process stopped.
    echo.
)

:: Set UTF-8 encoding to prevent UnicodeEncodeError on Windows
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1

:: Create log directory if not exists
if not exist logs mkdir logs

:: Start bot
echo [+] Starting bot...
echo [+] Time: %date% %time%
echo.

python bot.py > logs\bot_stdout.log 2>&1

if errorlevel 1 (
    echo.
    echo [!] Bot crashed! Check logs\bot_stdout.log for details.
    echo.
    pause
)
