@echo off
REM Build ScreenSnap executable with custom icon
REM This script creates a standalone .exe using PyInstaller

echo Building ScreenSnap executable with custom icon...
echo.

REM First create the icon if it doesn't exist
if not exist "screensnap.ico" (
    echo Creating custom icon...
    python create-icon.py
    echo.
)

pyinstaller --onefile --windowed --name ScreenSnap --icon=screensnap.ico --hidden-import PIL --hidden-import pyperclip --hidden-import tkinter --clean screensnap.py

echo.
if exist "dist\ScreenSnap.exe" (
    echo Build successful!
    echo Executable location: dist\ScreenSnap.exe
    echo.
    dir dist\ScreenSnap.exe | find "ScreenSnap.exe"
) else (
    echo Build failed! Check the error messages above.
    echo.
    echo Tip: If you get "Access is denied", the old .exe is locked.
    echo Try rebooting your computer, or build as ScreenSnap_v2.exe instead.
)

echo.
pause
