@echo off
REM Full installer build: exes + Inno Setup installer
setlocal

echo ============================================
echo  ScreenSnap Installer Build
echo ============================================
echo.

REM 1. Build the executables (always rebuild to avoid stale exes)
if exist "dist\ScreenSnap.exe"        del /q "dist\ScreenSnap.exe"
if exist "dist\ScreenSnapMonitor.exe" del /q "dist\ScreenSnapMonitor.exe"
if exist "build" rmdir /s /q "build"
echo Building executables...
call build-exe.bat
if not exist "dist\ScreenSnap.exe" (
    echo ERROR: dist\ScreenSnap.exe missing. Build failed.
    pause & exit /b 1
)
if not exist "dist\ScreenSnapMonitor.exe" (
    echo ERROR: dist\ScreenSnapMonitor.exe missing. Run build-exe.bat.
    pause & exit /b 1
)

REM 2. Locate Inno Setup compiler
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe"      set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
where iscc >nul 2>&1 && set "ISCC=iscc"

if exist "inno\Inno Setup 6\ISCC.exe" set "ISCC=%CD%\inno\Inno Setup 6\ISCC.exe"

if "%ISCC%"=="" (
    echo Inno Setup 6 not found. Installing locally into inno\Inno Setup 6 ...
    if not exist "inno\innosetup-6.7.1.exe" (
        echo ERROR: inno\innosetup-6.7.1.exe not found.
        echo Download Inno Setup 6 from https://jrsoftware.org/isinfo.php and place it at inno\innosetup-6.7.1.exe
        pause & exit /b 1
    )
    "inno\innosetup-6.7.1.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER /DIR="%CD%\inno\Inno Setup 6" /NOICONS
    if exist "inno\Inno Setup 6\ISCC.exe" set "ISCC=%CD%\inno\Inno Setup 6\ISCC.exe"
)

if "%ISCC%"=="" (
    echo ERROR: Inno Setup 6 install failed or ISCC.exe still not found.
    pause & exit /b 1
)

REM 3. Build the installer
echo Compiling installer with: %ISCC%
"%ISCC%" installer.iss
if errorlevel 1 (
    echo Installer build FAILED.
    pause & exit /b 1
)

echo.
echo Installer created in: installer-output\
dir /b installer-output\*.exe
echo.
pause
