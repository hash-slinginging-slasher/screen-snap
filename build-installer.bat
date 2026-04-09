@echo off
REM Full installer build: exes + Inno Setup installer
setlocal

echo ============================================
echo  ScreenSnap Installer Build
echo ============================================
echo.

REM 1. Build the executables
if not exist "dist\ScreenSnap.exe" (
    echo Building executables first...
    call build-exe.bat
)
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

if "%ISCC%"=="" (
    echo ERROR: Inno Setup 6 not found.
    echo Download from https://jrsoftware.org/isinfo.php and install, then re-run.
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
