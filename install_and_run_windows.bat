@echo off
setlocal ENABLEEXTENSIONS
title Piper TTS Setup + Start (robust)

REM ================== Settings ==================
set "VENV_DIR=.venv"
set "VOICE_DIR=voices"

REM Default: thorsten / medium (HuggingFace)
set "VOICE_ONNX_URL=https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx?download=true"
set "VOICE_JSON_URL=https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx.json?download=true"

REM Local filenames (must match your Python piper_model_path)
set "VOICE_ONNX_FILE=de_DE-thorsten-medium.onnx"
set "VOICE_JSON_FILE=de_DE-thorsten-medium.onnx.json"
REM ====================================================

echo.
echo ============================================
echo   Setup: Piper TTS (offline) + Script
echo ============================================
echo.

if not exist "%VOICE_DIR%" mkdir "%VOICE_DIR%"

REM 1) venv
if not exist "%VENV_DIR%" (
  echo [1/6] Creating virtual environment...
  python -m venv "%VENV_DIR%"
  if errorlevel 1 (
    echo [ERROR] Failed to create venv. Make sure Python is installed and available in PATH.
    exit /b 1
  )
) else (
  echo [1/6] Virtual environment already exists.
)

REM 2) activate
call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 (
  echo [ERROR] Failed to activate venv.
  exit /b 1
)

REM 3) packages
echo [2/6] Updating pip...
"%VENV_DIR%\Scripts\python.exe" -m pip install -U pip
if errorlevel 1 (
  echo [ERROR] pip update failed.
  exit /b 1
)

echo [3/6] Installing packages...
"%VENV_DIR%\Scripts\pip.exe" install --upgrade requests piper-tts simpleaudio onnxruntime pyttsx3 pyyaml
if errorlevel 1 (
  echo [ERROR] Package installation failed.
  exit /b 1
)

REM 4) Choose downloader (curl preferred)
where curl >nul 2>&1
if %errorlevel%==0 ( set "DOWNLOADER=curl" ) else ( set "DOWNLOADER=powershell" )
echo [4/6] Downloader: %DOWNLOADER%

REM 5) Download voice files
echo [5/6] Downloading voice (model + config) to "%VOICE_DIR%"...

REM Delete old files to avoid "empty -o" issues
if exist "%VOICE_DIR%\%VOICE_ONNX_FILE%" del /f /q "%VOICE_DIR%\%VOICE_ONNX_FILE%"
if exist "%VOICE_DIR%\%VOICE_JSON_FILE%" del /f /q "%VOICE_DIR%\%VOICE_JSON_FILE%"

if /I "%DOWNLOADER%"=="curl" (
  curl -L -f -o "%VOICE_DIR%\%VOICE_ONNX_FILE%" "%VOICE_ONNX_URL%"
  if errorlevel 1 (
    echo [ERROR] Model download via curl failed.
    exit /b 1
  )
  curl -L -f -o "%VOICE_DIR%\%VOICE_JSON_FILE%" "%VOICE_JSON_URL%"
  if errorlevel 1 (
    echo [ERROR] Config download via curl failed.
    exit /b 1
  )
) else (
  powershell -NoProfile -Command "try { Invoke-WebRequest -Uri '%VOICE_ONNX_URL%' -OutFile '%VOICE_DIR%\%VOICE_ONNX_FILE%' -UseBasicParsing; exit 0 } catch { Write-Host $_; exit 1 }"
  if errorlevel 1 (
    echo [ERROR] Model download via PowerShell failed.
    exit /b 1
  )
  powershell -NoProfile -Command "try { Invoke-WebRequest -Uri '%VOICE_JSON_URL%' -OutFile '%VOICE_DIR%\%VOICE_JSON_FILE%' -UseBasicParsing; exit 0 } catch { Write-Host $_; exit 1 }"
  if errorlevel 1 (
    echo [ERROR] Config download via PowerShell failed.
    exit /b 1
  )
)

echo [5/6] Checking file sizes...
powershell -NoProfile -Command "$m='%CD%\%VOICE_DIR%\%VOICE_ONNX_FILE%'; $j='%CD%\%VOICE_DIR%\%VOICE_JSON_FILE%'; if (!(Test-Path $m) -or !(Test-Path $j)) { Write-Host 'Files missing'; exit 2 }; $ms=(Get-Item $m).Length; $js=(Get-Item $j).Length; if ($ms -lt 100000) { Write-Host 'Model too small:' $ms; exit 3 }; if ($js -lt 1000) { Write-Host 'Config too small:' $js; exit 4 }; Write-Host ('OK: Model {0} B, Config {1} B' -f $ms, $js); exit 0"
if errorlevel 1 (
  echo [ERROR] Voice files appear invalid.
  exit /b 1
)

REM 6) Run script (always use venv Python)
echo.
echo [6/6] Launching script...
"%VENV_DIR%\Scripts\python.exe" announcement_tts.py
set "RET=%ERRORLEVEL%"

echo.
if "%RET%"=="0" (
  echo Done.
) else (
  echo Script exited with error code %RET%.
)
endlocal
exit /b %RET%
