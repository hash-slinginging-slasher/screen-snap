@echo off
REM Download and stage Tesseract OCR binaries into .\tesseract\ so the
REM installer can bundle them alongside ScreenSnap.exe.
REM
REM Result (on success): .\tesseract\tesseract.exe plus required DLLs
REM and tessdata\eng.traineddata (and osd.traineddata if available).
REM
REM Safe to re-run: exits early if staging dir already populated.

setlocal

REM --- Configuration ------------------------------------------------
set "TESS_VERSION=5.5.0.20241111"
REM GitHub releases is the authoritative source. The UB-Mannheim mirror
REM (digi.bib.uni-mannheim.de) can 403 on default User-Agents.
set "TESS_URL=https://github.com/tesseract-ocr/tesseract/releases/download/5.5.0/tesseract-ocr-w64-setup-%TESS_VERSION%.exe"
REM Language data is NOT bundled in the NSIS installer (it's downloaded
REM on demand at install time). Grab eng.traineddata directly from the
REM official tessdata repo.
set "ENG_TRAINEDDATA_URL=https://github.com/tesseract-ocr/tessdata/raw/main/eng.traineddata"
set "OSD_TRAINEDDATA_URL=https://github.com/tesseract-ocr/tessdata/raw/main/osd.traineddata"
set "CACHE_DIR=build-cache"
set "INSTALLER=%CACHE_DIR%\tesseract-installer-%TESS_VERSION%.exe"
set "STAGING=%CD%\%CACHE_DIR%\tesseract-install"
set "OUT_DIR=tesseract"

echo ============================================
echo  Tesseract OCR -- fetch ^& stage
echo ============================================
echo.

REM --- Skip if already staged ---------------------------------------
if exist "%OUT_DIR%\tesseract.exe" (
    if exist "%OUT_DIR%\tessdata\eng.traineddata" (
        echo Tesseract already staged at %OUT_DIR%\tesseract.exe
        goto :done
    )
)

if not exist "%CACHE_DIR%" mkdir "%CACHE_DIR%"
if not exist "%OUT_DIR%"   mkdir "%OUT_DIR%"

REM --- Download installer (cached) ----------------------------------
if not exist "%INSTALLER%" (
    echo Downloading Tesseract %TESS_VERSION% from GitHub releases...
    echo   %TESS_URL%
    powershell -NoProfile -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%TESS_URL%' -OutFile '%INSTALLER%' -UseBasicParsing -UserAgent 'Mozilla/5.0 ScreenSnap-Installer' -MaximumRedirection 10 } catch { Write-Error $_; exit 1 }"
    if errorlevel 1 (
        echo ERROR: Download failed. Check your network and the URL above.
        if exist "%INSTALLER%" del /q "%INSTALLER%"
        exit /b 1
    )
) else (
    echo Using cached installer: %INSTALLER%
)

REM --- Extract installer via 7-Zip ----------------------------------
REM The Tesseract installer is NSIS. Running /S can silently fail when
REM UAC elevation is denied. 7-Zip can read NSIS archives directly, so
REM we extract without ever executing the installer.
set "SEVENZIP="
if exist "%ProgramFiles%\7-Zip\7z.exe"      set "SEVENZIP=%ProgramFiles%\7-Zip\7z.exe"
if exist "%ProgramFiles(x86)%\7-Zip\7z.exe" set "SEVENZIP=%ProgramFiles(x86)%\7-Zip\7z.exe"
if "%SEVENZIP%"=="" (
    where 7z >nul 2>&1 && set "SEVENZIP=7z"
)
if "%SEVENZIP%"=="" (
    echo ERROR: 7-Zip not found. Install from https://www.7-zip.org/
    echo        ^(needed to extract the Tesseract NSIS installer without UAC.^)
    exit /b 1
)

echo.
echo Extracting Tesseract into staging dir via 7-Zip...
if exist "%STAGING%" rmdir /s /q "%STAGING%"
mkdir "%STAGING%"
"%SEVENZIP%" x "%INSTALLER%" -o"%STAGING%" -y >nul
if errorlevel 1 (
    echo ERROR: 7-Zip extraction failed.
    exit /b 1
)
if not exist "%STAGING%\tesseract.exe" (
    echo ERROR: tesseract.exe not found after 7-Zip extraction.
    echo Contents of %STAGING%:
    dir /b "%STAGING%"
    exit /b 1
)

REM --- Copy the subset we actually ship -----------------------------
echo.
echo Copying runtime files to %OUT_DIR%\...
copy /Y "%STAGING%\tesseract.exe"     "%OUT_DIR%\"  >nul
copy /Y "%STAGING%\*.dll"             "%OUT_DIR%\"  >nul
if not exist "%OUT_DIR%\tessdata" mkdir "%OUT_DIR%\tessdata"

REM --- Download language data ---------------------------------------
REM The NSIS installer downloads tessdata at install time and does not
REM bundle it, so we fetch eng.traineddata directly from the official
REM tessdata repo.
if not exist "%OUT_DIR%\tessdata\eng.traineddata" (
    echo Downloading eng.traineddata...
    echo   %ENG_TRAINEDDATA_URL%
    powershell -NoProfile -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%ENG_TRAINEDDATA_URL%' -OutFile '%OUT_DIR%\tessdata\eng.traineddata' -UseBasicParsing -UserAgent 'Mozilla/5.0 ScreenSnap-Installer' -MaximumRedirection 10 } catch { Write-Error $_; exit 1 }"
    if errorlevel 1 (
        echo ERROR: Download of eng.traineddata failed.
        if exist "%OUT_DIR%\tessdata\eng.traineddata" del /q "%OUT_DIR%\tessdata\eng.traineddata"
        exit /b 1
    )
)
if not exist "%OUT_DIR%\tessdata\osd.traineddata" (
    echo Downloading osd.traineddata...
    echo   %OSD_TRAINEDDATA_URL%
    powershell -NoProfile -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%OSD_TRAINEDDATA_URL%' -OutFile '%OUT_DIR%\tessdata\osd.traineddata' -UseBasicParsing -UserAgent 'Mozilla/5.0 ScreenSnap-Installer' -MaximumRedirection 10 } catch { Write-Error $_; exit 1 }"
    if errorlevel 1 (
        echo WARNING: osd.traineddata download failed -- continuing without it.
        if exist "%OUT_DIR%\tessdata\osd.traineddata" del /q "%OUT_DIR%\tessdata\osd.traineddata"
    )
)

REM --- Verify -------------------------------------------------------
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
