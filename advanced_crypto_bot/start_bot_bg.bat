@echo off
title Crypto Bot (Background)
echo ========================================
echo   Advanced Crypto Trading Bot (Background)
echo ========================================
echo.

:: Check if bot is already running
tasklist | findstr /i "python.exe" >nul 2>&1
if %errorlevel% equ 0 (
    echo [!] Bot is already running!
    echo.
    tasklist /fi "imagename eq python.exe" /fo table
    echo.
    echo To restart: Run stop_bot.bat first, then this script.
    echo.
    pause
    goto :eof
)

:: Set UTF-8 encoding to prevent UnicodeEncodeError on Windows
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1

:: Create log directory if not exists
if not exist logs mkdir logs

:: Start bot in background (hidden window)
echo [+] Starting bot in background...
echo [+] Time: %date% %time%
echo.
echo Log files:
echo   - logs\trading_bot.log      (main log)
echo   - logs\smart_profit_hunter.log (poller log)
echo   - logs\errors.log           (errors only)
echo   - logs\bot_stdout.log       (console output)
echo.

start /B pythonw bot.py >> logs\bot_stdout.log 2>&1

timeout /t 3 >nul

:: Verify bot started
tasklist | findstr /i "python.exe" >nul 2>&1
if %errorlevel% equ 0 (
    echo [+] Bot started successfully!
    echo.
    for /f "tokens=2" %%i in ('tasklist /fi "imagename eq python.exe" /fo list ^| findstr "PID:"') do (
        echo [+] PID: %%i
    )
) else (
    echo [!] Bot failed to start. Check logs\bot_stdout.log
    echo.
    type logs\bot_stdout.log 2>nul
    echo.
    pause
    goto :eof
)

echo.
echo Use stop_bot.bat to stop the bot.
echo.
