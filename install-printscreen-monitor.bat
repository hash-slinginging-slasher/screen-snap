@echo off
REM Install and Run ScreenSnap Print Screen Monitor
REM This installs the background service that monitors the Print Screen key

setlocal

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

echo ========================================
echo  ScreenSnap Print Screen Monitor Setup
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH.
    echo Python 3.10+ is required for the Print Screen monitor.
    echo.
    pause
    exit /b 1
)

echo Installing required Python packages...
python -m pip install keyboard pystray Pillow

echo.
echo ========================================
echo  Starting Print Screen Monitor
echo ========================================
echo.
echo The monitor will run in the background and watch for Print Screen key presses.
echo A system tray icon will appear in the notification area.
echo.
echo To stop the monitor, right-click the tray icon and select "Quit".
echo.

REM Start the monitor (use pythonw to avoid console window)
start "" pythonw "%SCRIPT_DIR%\screensnap-printscreen-monitor.py"

echo Print Screen Monitor started!
echo.
pause
