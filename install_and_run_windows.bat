@echo off
setlocal ENABLEEXTENSIONS
title Piper TTS Setup + Start (robust)

REM ================== Einstellungen ==================
set "VENV_DIR=.venv"
set "VOICE_DIR=voices"

REM Standard: thorsten / medium (HuggingFace)
set "VOICE_ONNX_URL=https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx?download=true"
set "VOICE_JSON_URL=https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx.json?download=true"

REM Lokale Dateinamen (müssen zu deinem Python piper_model_path passen)
set "VOICE_ONNX_FILE=de_DE-thorsten-medium.onnx"
set "VOICE_JSON_FILE=de_DE-thorsten-medium.onnx.json"
REM ====================================================

echo.
echo ============================================
echo   Einrichtung: Piper TTS (offline) + Script
echo ============================================
echo.

if not exist "%VOICE_DIR%" mkdir "%VOICE_DIR%"

REM 1) venv
if not exist "%VENV_DIR%" (
  echo [1/6] Erstelle virtuelles Environment...
  python -m venv "%VENV_DIR%"
  if errorlevel 1 (
    echo [FEHLER] venv fehlgeschlagen. Stelle sicher, dass Python installiert ist und im PATH liegt.
    exit /b 1
  )
) else (
  echo [1/6] Virtuelles Environment existiert bereits.
)

REM 2) aktivieren
call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 (
  echo [FEHLER] venv aktivieren fehlgeschlagen.
  exit /b 1
)

REM 3) Pakete
echo [2/6] Aktualisiere pip...
"%VENV_DIR%\Scripts\python.exe" -m pip install -U pip
if errorlevel 1 (
  echo [FEHLER] pip-Update fehlgeschlagen.
  exit /b 1
)

echo [3/6] Installiere Pakete...
"%VENV_DIR%\Scripts\pip.exe" install --upgrade requests piper-tts simpleaudio onnxruntime pyttsx3
if errorlevel 1 (
  echo [FEHLER] Paketinstallation fehlgeschlagen.
  exit /b 1
)

REM 4) Downloader wählen (curl bevorzugt)
where curl >nul 2>&1
if %errorlevel%==0 ( set "DOWNLOADER=curl" ) else ( set "DOWNLOADER=powershell" )
echo [4/6] Downloader: %DOWNLOADER%

REM 5) Stimmen laden (ohne Subroutinen, PowerShell- und CMD-freundlich)
echo [5/6] Lade Stimme (Model + Config) nach "%VOICE_DIR%"...

REM alte Dateien ggf. löschen, um "leere -o" Fehler zu vermeiden
if exist "%VOICE_DIR%\%VOICE_ONNX_FILE%" del /f /q "%VOICE_DIR%\%VOICE_ONNX_FILE%"
if exist "%VOICE_DIR%\%VOICE_JSON_FILE%" del /f /q "%VOICE_DIR%\%VOICE_JSON_FILE%"

if /I "%DOWNLOADER%"=="curl" (
  curl -L -f -o "%VOICE_DIR%\%VOICE_ONNX_FILE%" "%VOICE_ONNX_URL%"
  if errorlevel 1 (
    echo [FEHLER] Model-Download via curl fehlgeschlagen.
    exit /b 1
  )
  curl -L -f -o "%VOICE_DIR%\%VOICE_JSON_FILE%" "%VOICE_JSON_URL%"
  if errorlevel 1 (
    echo [FEHLER] Config-Download via curl fehlgeschlagen.
    exit /b 1
  )
) else (
  powershell -NoProfile -Command "try { Invoke-WebRequest -Uri '%VOICE_ONNX_URL%' -OutFile '%VOICE_DIR%\%VOICE_ONNX_FILE%' -UseBasicParsing; exit 0 } catch { Write-Host $_; exit 1 }"
  if errorlevel 1 (
    echo [FEHLER] Model-Download via PowerShell fehlgeschlagen.
    exit /b 1
  )
  powershell -NoProfile -Command "try { Invoke-WebRequest -Uri '%VOICE_JSON_URL%' -OutFile '%VOICE_DIR%\%VOICE_JSON_FILE%' -UseBasicParsing; exit 0 } catch { Write-Host $_; exit 1 }"
  if errorlevel 1 (
    echo [FEHLER] Config-Download via PowerShell fehlgeschlagen.
    exit /b 1
  )
)

echo [5/6] Prüfe Dateigrößen...
powershell -NoProfile -Command "$m='%CD%\%VOICE_DIR%\%VOICE_ONNX_FILE%'; $j='%CD%\%VOICE_DIR%\%VOICE_JSON_FILE%'; if (!(Test-Path $m) -or !(Test-Path $j)) { Write-Host 'Dateien fehlen'; exit 2 }; $ms=(Get-Item $m).Length; $js=(Get-Item $j).Length; if ($ms -lt 100000) { Write-Host 'Model zu klein:' $ms; exit 3 }; if ($js -lt 1000) { Write-Host 'Config zu klein:' $js; exit 4 }; Write-Host ('OK: Model {0} B, Config {1} B' -f $ms, $js); exit 0"
if errorlevel 1 (
  echo [FEHLER] Stimmen-Dateien sehen ungueltig aus.
  exit /b 1
)

REM 6) Script starten (immer venv-Python nutzen)
echo.
echo [6/6] Starte Script...
"%VENV_DIR%\Scripts\python.exe" announcement_tts.py
set "RET=%ERRORLEVEL%"

echo.
if "%RET%"=="0" (
  echo Fertig.
) else (
  echo Script beendete sich mit Fehlercode %RET%.
)
endlocal
exit /b %RET%
