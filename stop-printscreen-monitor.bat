@echo off
REM Stop ScreenSnap Print Screen Monitor
REM This kills the background monitor process

setlocal

echo ========================================
echo  Stop ScreenSnap Print Screen Monitor
echo ========================================
echo.

tasklist /FI "IMAGENAME eq python.exe" /FO TABLE | find /I "python" >nul
if %errorLevel% neq 0 (
    echo No Python processes found. The monitor is not running.
) else (
    echo Stopping all ScreenSnap Print Screen Monitor processes...
    taskkill /F /FI "WINDOWTITLE eq ScreenSnap Print Screen Monitor" /T 2>nul
    taskkill /F /IM python.exe /FI "WINDOWTITLE eq ScreenSnap Print Screen Monitor" 2>nul
    
    echo.
    echo Looking for monitor processes by command line...
    wmic process where "name='python.exe' and commandline like '%%screensnap-printscreen-monitor%%'" get ProcessId 2>nul | findstr "[0-9]" > "%TEMP%\screensnap_pids.txt"
    
    for /f %%i in (%TEMP%\screensnap_pids.txt) do (
        echo Stopping process %%i...
        taskkill /F /PID %%i 2>nul
    )
    
    del "%TEMP%\screensnap_pids.txt" 2>nul
)

echo.
echo ========================================
echo  Monitor Stopped
echo ========================================
echo.
echo The Print Screen key is no longer monitored by ScreenSnap.
echo.
pause
