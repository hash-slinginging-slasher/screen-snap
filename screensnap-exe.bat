@echo off
REM ScreenSnap - Portable Screenshot & Annotation Tool
REM Windows executable entry point

REM Get the directory where this batch file is located
set "SCRIPT_DIR=%~dp0"

REM Run the ScreenSnap executable
if exist "%SCRIPT_DIR%dist\ScreenSnap.exe" (
    "%SCRIPT_DIR%dist\ScreenSnap.exe" %*
) else if exist "%SCRIPT_DIR%ScreenSnap.exe" (
    "%SCRIPT_DIR%ScreenSnap.exe" %*
) else (
    echo ScreenSnap.exe not found!
    echo Looking for alternatives...
    if exist "%SCRIPT_DIR%dist\ScreenSnap_v*.exe" (
        for %%f in ("%SCRIPT_DIR%dist\ScreenSnap_v*.exe") do (
            echo Running %%~nxf
            "%%f" %*
            goto :eof
        )
    ) else (
        echo ERROR: No ScreenSnap executable found.
        echo Please run build-exe.bat to create one.
        pause
    )
)
