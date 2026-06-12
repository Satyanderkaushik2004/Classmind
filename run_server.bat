@echo off
title VYOM Server Starter
echo ---------------------------------------------------
echo VYOM: Starting Backend Server...
echo ---------------------------------------------------

set "PYTHON_CMD=python"

:: Check if Python in PATH is installed and working (not the 0-byte alias)
python --version >nul 2>&1
if %errorlevel% neq 0 (
    :: Try local user AppData Python 3.11 path
    if exist "%USERPROFILE%\AppData\Local\Programs\Python\Python311\python.exe" (
        set "PYTHON_CMD=%USERPROFILE%\AppData\Local\Programs\Python\Python311\python.exe"
    ) else (
        echo [ERROR] Python is not installed or not in PATH!
        echo Please install Python from python.org
        pause
        exit /b
    )
)

echo [1/3] Checking/Installing requirements...
"%PYTHON_CMD%" -m pip install -r requirements.txt --quiet

echo [2/3] Starting Server on http://localhost:8003
echo (Keep this window open while using the app)
echo ---------------------------------------------------

set "PORT=8003"
:: Run uvicorn using the module flag to avoid PATH issues
"%PYTHON_CMD%" -m uvicorn main:app --host 0.0.0.0 --port 8003 --reload

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Server failed to start. 
    echo Try running: pip install -r requirements.txt
    pause
)
