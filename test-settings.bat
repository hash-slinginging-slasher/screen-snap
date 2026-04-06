@echo off
REM Test ScreenSnap_v2 executable settings behavior
echo ========================================
echo ScreenSnap Settings Test
echo ========================================
echo.

echo Current directory: %CD%
echo.

echo Looking for settings.ini in: %~dp0
if exist "%~dp0settings.ini" (
    echo [FOUND] settings.ini exists
    echo Contents:
    type "%~dp0settings.ini"
) else (
    echo [NOT FOUND] settings.ini does not exist in current directory
)

echo.
echo ========================================
echo Running ScreenSnap_v2.exe...
echo The executable should create/read settings.ini
echo from the SAME directory as the .exe file.
echo ========================================
echo.

start "" "%~dp0dist\ScreenSnap_v2.exe"

echo.
echo ScreenSnap launched. Check if settings.ini appears in the executable folder.
echo.
pause
