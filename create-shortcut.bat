@echo off
REM Create desktop shortcut for ScreenSnap with custom icon
echo Creating desktop shortcut for ScreenSnap...
echo.

set "SCRIPT_DIR=%~dp0"
set "EXE_PATH=%SCRIPT_DIR%dist\ScreenSnap_Final.exe"
set "ICON_PATH=%SCRIPT_DIR%screensnap-icon-preview.png"
set "DESKTOP=%USERPROFILE%\Desktop"

if not exist "%EXE_PATH%" (
    echo ERROR: ScreenSnap_Final.exe not found at:
    echo %EXE_PATH%
    echo.
    echo Please run build-exe.bat first to create the executable.
    pause
    exit /b 1
)

if not exist "%ICON_PATH%" (
    echo WARNING: Icon file not found, creating shortcut without icon...
    set "ICON_PATH="
)

REM Create shortcut using PowerShell
if defined ICON_PATH (
    powershell -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%DESKTOP%\ScreenSnap.lnk'); $Shortcut.TargetPath = '%EXE_PATH%'; $Shortcut.WorkingDirectory = '%SCRIPT_DIR%'; $Shortcut.IconLocation = '%ICON_PATH%'; $Shortcut.Description = 'ScreenSnap - Portable Screenshot Tool'; $Shortcut.Save(); Write-Host 'Shortcut created on desktop with custom icon!' -ForegroundColor Green"
) else (
    powershell -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%DESKTOP%\ScreenSnap.lnk'); $Shortcut.TargetPath = '%EXE_PATH%'; $Shortcut.WorkingDirectory = '%SCRIPT_DIR%'; $Shortcut.Description = 'ScreenSnap - Portable Screenshot Tool'; $Shortcut.Save(); Write-Host 'Shortcut created on desktop (no icon)' -ForegroundColor Yellow"
)

echo.
echo You can now launch ScreenSnap from your desktop!
echo.
pause
