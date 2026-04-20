@echo off
title Stop Crypto Bot
echo ========================================
echo   Stop Crypto Trading Bot
echo ========================================
echo.

:: Check if bot is running
tasklist | findstr /i "python.exe" >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Bot is not running.
    echo.
    pause
    goto :eof
)

echo [*] Running bot processes:
tasklist /fi "imagename eq python.exe" /fo table
echo.

:: Stop bot
choice /M "Do you want to stop the bot"
if errorlevel 2 goto :eof

echo.
echo [~] Stopping bot...
for /f "tokens=2" %%i in ('tasklist /fi "imagename eq python.exe" /fo list ^| findstr "PID:"') do (
    echo [~] Killing PID: %%i
    taskkill /F /PID %%i >nul 2>&1
)

timeout /t 2 >nul

:: Verify stopped
tasklist | findstr /i "python.exe" >nul 2>&1
if %errorlevel% neq 0 (
    echo [+] Bot stopped successfully.
) else (
    echo [!] Some processes still running. Force killing...
    taskkill /F /IM python.exe >nul 2>&1
)

echo.
pause
