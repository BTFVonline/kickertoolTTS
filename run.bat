
@echo off
setlocal

REM Falls ein virtuelles Environment vorhanden ist, aktivieren
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
)

python announcement_tts.py %*
