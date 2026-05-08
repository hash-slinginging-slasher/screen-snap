@echo off
REM Build ScreenSnap and ScreenSnapMonitor executables
REM Produces dist\ScreenSnap.exe and dist\ScreenSnapMonitor.exe

echo Building ScreenSnap executables...
echo.

echo Ensuring build dependencies are installed...
python -m pip install --quiet pyinstaller Pillow pyperclip keyboard pystray pytesseract
if errorlevel 1 (
    echo Failed to install required Python packages.
    goto :fail
)
echo.

if not exist "screensnap.ico" (
    echo Creating custom icon...
    python create-icon.py
    echo.
)

echo [1/2] Building ScreenSnap.exe...
pyinstaller --clean --noconfirm ScreenSnap.spec
if errorlevel 1 goto :fail

echo.
echo [2/2] Building ScreenSnapMonitor.exe...
pyinstaller --clean --noconfirm ScreenSnapMonitor.spec
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
