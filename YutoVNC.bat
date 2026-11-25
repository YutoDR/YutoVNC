@echo off
setlocal
cd /d "%~dp0"
title YutoVNC - Smart Remote Client

REM Check python or pythonw
where pythonw.exe >nul 2>&1
if %ERRORLEVEL% equ 0 (
    start "" pythonw.exe main.py
    exit /b 0
)

where python.exe >nul 2>&1
if %ERRORLEVEL% equ 0 (
    python.exe main.py
    exit /b 0
)

echo [ERROR] Python tidak ditemukan di sistem Anda!
echo Silakan install Python 3.8+ dari https://www.python.org/
pause
