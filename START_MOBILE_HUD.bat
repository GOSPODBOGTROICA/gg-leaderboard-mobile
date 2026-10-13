@echo off
setlocal enabledelayedexpansion

:: Switch console to UTF-8 code page for clean QR code and unicode display
chcp 65001 >nul 2>&1

:: Change working directory to the folder containing this batch script
cd /d "%~dp0"

title GGPoker Spin ^& Gold Mobile Leaderboard HUD

echo ======================================================================
echo     GGPoker Spin ^& Gold Mobile Leaderboard HUD — One-Click Launcher
echo ======================================================================
echo.

:: Detect Python interpreter
set "PYTHON_CMD="
python --version >nul 2>&1
if !errorlevel! equ 0 (
    set "PYTHON_CMD=python"
) else (
    py --version >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON_CMD=py"
    )
)

if "%PYTHON_CMD%"=="" (
    echo [ERROR] Python was not found in your system PATH!
    echo.
    echo Please install Python 3.11 or newer from:
    echo https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: Activate virtual environment if present
if exist ".venv\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment .venv...
    call ".venv\Scripts\activate.bat"
) else if exist "venv\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment venv...
    call "venv\Scripts\activate.bat"
)

echo [INFO] Launching server launcher run_server.py...
echo.

:: Run the server launcher
%PYTHON_CMD% run_server.py %*
set "EXIT_CODE=%errorlevel%"

if %EXIT_CODE% neq 0 (
    echo.
    echo ======================================================================
    echo [ERROR] Server exited with code %EXIT_CODE%.
    echo ======================================================================
    pause
)

exit /b %EXIT_CODE%
