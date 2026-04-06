@echo off
REM ScreenSnap - Portable Screenshot & Annotation Tool
REM Windows executable entry point (v2 - Fixed settings.ini location)

REM Get the directory where this batch file is located
set "SCRIPT_DIR=%~dp0"

REM Run the ScreenSnap executable (v6 with multi-monitor + settings button)
if exist "%SCRIPT_DIR%dist\ScreenSnap_v6.exe" (
    "%SCRIPT_DIR%dist\ScreenSnap_v6.exe" %*
) else if exist "%SCRIPT_DIR%ScreenSnap_v6.exe" (
    "%SCRIPT_DIR%ScreenSnap_v6.exe" %*
) else (
    echo ScreenSnap_v6.exe not found!
    echo Looking for alternatives...
    if exist "%SCRIPT_DIR%dist\ScreenSnap.exe" (
        echo Running old ScreenSnap.exe (multi-monitor may not work)
        "%SCRIPT_DIR%dist\ScreenSnap.exe" %*
    ) else (
        echo ERROR: No ScreenSnap executable found.
        echo Please run build-exe.bat to create one.
        pause
    )
)
