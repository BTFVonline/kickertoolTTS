import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
import yaml
from pathlib import Path

# ==== CONFIG LADEN ====
CONFIG_PATH = Path("config.yaml")
if not CONFIG_PATH.exists():
    raise FileNotFoundError("config.yaml fehlt! Bitte anlegen.")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

TTS_CFG = CONFIG.get("tts", {})
provider = TTS_CFG.get("provider", "piper")
use_piper = provider.lower() == "piper"

# Piper-Optionen
piper_model_path = str(TTS_CFG.get("model_path", "voices/de_DE-thorsten-medium.onnx"))
piper_speaker = TTS_CFG.get("speaker")
piper_length_scale = TTS_CFG.get("length_scale", 0.95)
piper_noise_scale = TTS_CFG.get("noise_scale", 0.5)
piper_noise_w = TTS_CFG.get("noise_w", 0.8)

# pyttsx3-Optionen
tts_rate = TTS_CFG.get("rate", 170)
tts_volume = TTS_CFG.get("volume", 1.0)
tts_voice_index = TTS_CFG.get("voice_index")

save_audio = CONFIG.get("files", {}).get("save_audio", False)

# ==== SETUP ====
if os.name == "nt":
    piper_executable = str(Path(".venv") / "Scripts" / "piper.exe")
else:
    piper_executable = "piper"


try:
    import pyttsx3
except ImportError:
    pyttsx3 = None


def _play_wav(path: str):
    abs_path = os.path.abspath(path)
    if os.name == "nt":
        try:
            subprocess.run([
                "powershell", "-NoProfile", "-Command",
                f"[System.Media.SoundPlayer]::new('{abs_path}').PlaySync()"
            ], check=True)
            return
        except Exception as e:
            print(f"[WARN] PowerShell SoundPlayer fehlgeschlagen: {e}")
    else:
        for player in ["afplay", "ffplay", "aplay"]:
            if shutil.which(player):
                subprocess.run([player, abs_path], check=False)
                return
    print("[WARN] Konnte WAV nicht automatisch abspielen.")


def _normalize_text_for_tts(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"(Tisch\s+\S+):", r"\1.", text)
    text = text.replace(" gegen ", ", gegen ")
    return text


def _umlaut_fallback(text: str) -> str:
    repl = {
        "ä": "ae", "ö": "oe", "ü": "ue",
        "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
        "ß": "ss",
    }
    return "".join(repl.get(ch, ch) for ch in text)


def _piper_say_once(text: str) -> bool:
    exe_path = piper_executable
    if os.name == "nt" and not Path(exe_path).exists():
        exe_path = "piper"

    if shutil.which(exe_path) is None and not Path(exe_path).exists():
        print(f"[WARN] Piper nicht gefunden unter: {exe_path}")
        return False

    model_path = Path(piper_model_path)
    json_path = Path(str(model_path) + ".json")
    if not model_path.exists() or not json_path.exists():
        print("[WARN] Piper-Model oder Config fehlt.")
        return False

    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name.replace("\\", "/")

        cmd = [
            exe_path, "--model", str(model_path), "--config", str(json_path),
            "--output_file", wav_path,
            "--length_scale", str(piper_length_scale),
            "--noise_scale", str(piper_noise_scale),
            "--noise_w", str(piper_noise_w),
        ]
        if piper_speaker is not None:
            cmd += ["--speaker", str(piper_speaker)]

        subprocess.run(cmd, input=text.encode("ansi"), check=True)
        _play_wav(wav_path)
        if not save_audio:
            os.remove(wav_path)
        return True
    except Exception as e:
        print(f"[WARN] Piper Fehler: {e}")
        return False


def _pyttsx3_say(text: str) -> bool:
    if pyttsx3 is None:
        return False
    try:
        engine = pyttsx3.init()
        engine.setProperty('rate', tts_rate)
        engine.setProperty('volume', tts_volume)
        if tts_voice_index is not None:
            voices = engine.getProperty('voices') or []
            if 0 <= tts_voice_index < len(voices):
                engine.setProperty('voice', voices[tts_voice_index].id)
        engine.say(_normalize_text_for_tts(text))
        engine.runAndWait()
        engine.stop()
        del engine
        return True
    except Exception as e:
        print(f"[WARN] TTS-Fehler (pyttsx3): {e}")
        return False


def speak_text(text: str):
    if use_piper:
        if _piper_say_once(text):
            return
        text2 = _umlaut_fallback(text)
        if text2 != text:
            if _piper_say_once(text2):
                return
    _pyttsx3_say(text)
