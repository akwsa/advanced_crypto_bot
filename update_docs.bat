@echo off
echo ================================================================================
echo   Auto Documentation Generator
echo ================================================================================
echo.

cd /d "%~dp0"

echo Current directory: %CD%
echo.

python generate_docs.py

echo.
echo ================================================================================
echo Press any key to open documentation...
pause >nul

notepad README_COMMANDS.txt
