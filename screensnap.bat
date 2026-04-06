@echo off
REM ScreenSnap - Portable Screenshot & Annotation Tool
REM Windows CMD entry point

REM Get the directory where this batch file is located
set "SCRIPT_DIR=%~dp0"

REM Run the Python script with all passed arguments
python "%SCRIPT_DIR%screensnap.py" %*

REM If Python is not found, show helpful message
if errorlevel 9009 (
    echo.
    echo ERROR: Python is not found on your PATH.
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo and ensure it's added to your PATH during installation.
    echo.
    pause
)
