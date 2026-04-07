@echo off
REM DEPRECATED: This registry method is not reliable for Windows 10/11
REM Please use install-printscreen-monitor.bat instead

echo ========================================
echo  DEPRECATED - Use New Method Instead
echo ========================================
echo.
echo The registry-based Print Screen handler is not reliable on modern Windows.
echo.
echo Please use the background monitor instead:
echo.
echo   install-printscreen-monitor.bat
echo.
echo This will:
echo   - Install required dependencies
echo   - Start a lightweight system tray monitor
echo   - Intercept Print Screen key globally
echo   - Launch ScreenSnap with region capture
echo.
pause
