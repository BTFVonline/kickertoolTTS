#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ================== Einstellungen ==================
VENV_DIR=".venv"
VOICE_DIR="voices"

VOICE_ONNX_FILE="de_DE-thorsten-medium.onnx"
VOICE_JSON_FILE="de_DE-thorsten-medium.onnx.json"
VOICE_ONNX_URL="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx?download=true"
VOICE_JSON_URL="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx.json?download=true"
# ====================================================

echo
echo "============================================"
echo "  Setup: Piper TTS (offline) + Script"
echo "============================================"
echo

mkdir -p "$VOICE_DIR"

# 1) Python finden (3.10+)
echo "[1/6] Suche Python 3.10+..."
PYTHON_BIN=""
for candidate in python3 python python3.13 python3.12 python3.11 python3.10; do
  if command -v "$candidate" >/dev/null 2>&1; then
    version=$("$candidate" -c 'import sys; print(sys.version_info >= (3,10))' 2>/dev/null || echo "False")
    if [[ "$version" == "True" ]]; then
      PYTHON_BIN="$candidate"
      echo "       Verwende: $PYTHON_BIN ($("$PYTHON_BIN" --version))"
      break
    fi
  fi
done

if [[ -z "$PYTHON_BIN" ]]; then
  echo "[FEHLER] Python 3.10 oder neuer nicht gefunden."
  echo "         Installiere Python z.B. über https://www.python.org oder 'brew install python'"
  exit 1
fi

# 2) venv erstellen
if [[ ! -f "$VENV_DIR/bin/activate" ]]; then
  echo "[2/6] Erstelle virtuelle Umgebung..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
else
  echo "[2/6] Virtuelle Umgebung bereits vorhanden."
fi

source "$VENV_DIR/bin/activate"

# 3) pip + Pakete aktualisieren
echo "[3/6] Aktualisiere pip..."
pip install -U pip --quiet

echo "[4/6] Installiere/aktualisiere Pakete..."
pip install --upgrade requests piper-tts onnxruntime pyttsx3 pyyaml pathvalidate --quiet

# 4) Sprachmodell herunterladen (nur wenn fehlend oder zu klein)
echo "[5/6] Prüfe Sprachmodell in '$VOICE_DIR'..."

download_needed=false

if [[ ! -f "$VOICE_DIR/$VOICE_ONNX_FILE" ]] || [[ $(wc -c < "$VOICE_DIR/$VOICE_ONNX_FILE") -lt 100000 ]]; then
  download_needed=true
fi
if [[ ! -f "$VOICE_DIR/$VOICE_JSON_FILE" ]] || [[ $(wc -c < "$VOICE_DIR/$VOICE_JSON_FILE") -lt 1000 ]]; then
  download_needed=true
fi

if [[ "$download_needed" == "true" ]]; then
  echo "       Lade Stimme herunter (ca. 63 MB, einmalig)..."
  curl -L -f --progress-bar -o "$VOICE_DIR/$VOICE_ONNX_FILE" "$VOICE_ONNX_URL" || {
    echo "[FEHLER] Download des Sprachmodells fehlgeschlagen."
    exit 1
  }
  curl -L -f --progress-bar -o "$VOICE_DIR/$VOICE_JSON_FILE" "$VOICE_JSON_URL" || {
    echo "[FEHLER] Download der Sprachkonfiguration fehlgeschlagen."
    exit 1
  }
  echo "       Stimme erfolgreich heruntergeladen."
else
  echo "       Stimme bereits vorhanden, kein Download nötig."
fi

# 5) Starten
echo
echo "[6/6] Starte Skript..."
echo
python announcement_tts.py "$@"
