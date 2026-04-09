@echo off
REM Build ScreenSnap and ScreenSnapMonitor executables
REM Produces dist\ScreenSnap.exe and dist\ScreenSnapMonitor.exe

echo Building ScreenSnap executables...
echo.

if not exist "screensnap.ico" (
    echo Creating custom icon...
    python create-icon.py
    echo.
)

echo [1/2] Building ScreenSnap.exe...
pyinstaller --onefile --windowed --name ScreenSnap --icon=screensnap.ico ^
    --hidden-import PIL --hidden-import pyperclip --hidden-import tkinter ^
    --clean screensnap.py
if errorlevel 1 goto :fail

echo.
echo [2/2] Building ScreenSnapMonitor.exe...
pyinstaller --onefile --windowed --name ScreenSnapMonitor --icon=screensnap.ico ^
    --hidden-import keyboard --hidden-import pystray --hidden-import PIL ^
    --clean screensnap-printscreen-monitor.py
if errorlevel 1 goto :fail

echo.
if exist "dist\ScreenSnap.exe" if exist "dist\ScreenSnapMonitor.exe" (
    echo Build successful!
    echo   dist\ScreenSnap.exe
    echo   dist\ScreenSnapMonitor.exe
    goto :done
)

:fail
echo Build failed! Check the error messages above.

:done
echo.
pause
