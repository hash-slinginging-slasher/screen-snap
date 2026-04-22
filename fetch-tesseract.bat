@echo off
REM Download and stage Tesseract OCR binaries into .\tesseract\ so the
REM installer can bundle them alongside ScreenSnap.exe.
REM
REM Result (on success): .\tesseract\tesseract.exe plus required DLLs
REM and tessdata\eng.traineddata (and osd.traineddata if available).
REM
REM Safe to re-run: exits early if staging dir already populated.

setlocal

REM ── Configuration ─────────────────────────────────────────────────
set "TESS_VERSION=5.5.0.20241111"
set "TESS_URL=https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-%TESS_VERSION%.exe"
set "CACHE_DIR=build-cache"
set "INSTALLER=%CACHE_DIR%\tesseract-installer-%TESS_VERSION%.exe"
set "STAGING=%CD%\%CACHE_DIR%\tesseract-install"
set "OUT_DIR=tesseract"

echo ============================================
echo  Tesseract OCR — fetch ^& stage
echo ============================================
echo.

REM ── Skip if already staged ────────────────────────────────────────
if exist "%OUT_DIR%\tesseract.exe" (
    if exist "%OUT_DIR%\tessdata\eng.traineddata" (
        echo Tesseract already staged at %OUT_DIR%\tesseract.exe
        goto :done
    )
)

if not exist "%CACHE_DIR%" mkdir "%CACHE_DIR%"
if not exist "%OUT_DIR%"   mkdir "%OUT_DIR%"

REM ── Download installer (cached) ───────────────────────────────────
if not exist "%INSTALLER%" (
    echo Downloading Tesseract %TESS_VERSION% from UB-Mannheim...
    echo   %TESS_URL%
    powershell -NoProfile -Command "try { Invoke-WebRequest -Uri '%TESS_URL%' -OutFile '%INSTALLER%' -UseBasicParsing } catch { Write-Error $_; exit 1 }"
    if errorlevel 1 (
        echo ERROR: Download failed. Check your network and the URL above.
        if exist "%INSTALLER%" del /q "%INSTALLER%"
        exit /b 1
    )
) else (
    echo Using cached installer: %INSTALLER%
)

REM ── Silent install into staging dir ───────────────────────────────
echo.
echo Extracting Tesseract into staging dir...
if exist "%STAGING%" rmdir /s /q "%STAGING%"
REM NSIS installer: /S silent, /D=<path> must be LAST arg, NO quotes.
"%INSTALLER%" /S /D=%STAGING%
if errorlevel 1 (
    echo ERROR: Silent install failed.
    exit /b 1
)
if not exist "%STAGING%\tesseract.exe" (
    echo ERROR: %STAGING%\tesseract.exe not found after install.
    exit /b 1
)

REM ── Copy the subset we actually ship ──────────────────────────────
echo.
echo Copying runtime files to %OUT_DIR%\...
copy /Y "%STAGING%\tesseract.exe"     "%OUT_DIR%\"  >nul
copy /Y "%STAGING%\*.dll"             "%OUT_DIR%\"  >nul
if not exist "%OUT_DIR%\tessdata" mkdir "%OUT_DIR%\tessdata"
copy /Y "%STAGING%\tessdata\eng.traineddata" "%OUT_DIR%\tessdata\"  >nul
if exist "%STAGING%\tessdata\osd.traineddata" (
    copy /Y "%STAGING%\tessdata\osd.traineddata" "%OUT_DIR%\tessdata\" >nul
)

REM ── Verify ────────────────────────────────────────────────────────
if not exist "%OUT_DIR%\tesseract.exe" (
    echo ERROR: %OUT_DIR%\tesseract.exe missing after copy.
    exit /b 1
)
if not exist "%OUT_DIR%\tessdata\eng.traineddata" (
    echo ERROR: %OUT_DIR%\tessdata\eng.traineddata missing after copy.
    exit /b 1
)

echo.
echo Tesseract staged successfully.
echo   %OUT_DIR%\tesseract.exe
echo   %OUT_DIR%\tessdata\eng.traineddata

:done
endlocal
exit /b 0
