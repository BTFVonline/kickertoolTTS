import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
from pathlib import Path

# Optional: pyttsx3 Fallback
try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

# ==== KONFIGURATION ====
enable_tts = True
use_piper = True

if os.name == "nt":
    piper_executable = str(Path(".venv") / "Scripts" / "piper.exe")
else:
    piper_executable = "piper"

piper_model_path = str(Path("voices") / "de_DE-thorsten-medium.onnx")
piper_speaker = None
piper_length_scale = 0.95
piper_noise_scale = 0.5
piper_noise_w = 0.8

tts_rate = 170
tts_volume = 1.0
tts_voice_index = None
# ========================


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
        os.remove(wav_path)
        return True
    except Exception as e:
        print(f"[WARN] Piper Fehler: {e}")
        return False


def _piper_say(text: str) -> bool:
    if not use_piper:
        return False
    t = _normalize_text_for_tts(text)
    if _piper_say_once(t):
        return True
    t2 = _umlaut_fallback(t)
    if t2 != t:
        return _piper_say_once(t2)
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
    if not enable_tts:
        return
    if _piper_say(text):
        return
    _pyttsx3_say(text)


if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(
        description="Einfaches TTS-CLI (Piper bevorzugt, pyttsx3 als Fallback)."
    )
    g_engine = parser.add_mutually_exclusive_group()
    g_engine.add_argument("--piper", action="store_true", help="Piper erzwingen")
    g_engine.add_argument("--pyttsx3", action="store_true", help="pyttsx3 erzwingen (Fallback)")
    parser.add_argument("-t", "--text", help="Direkter Text")
    parser.add_argument("-f", "--file", help="Text aus Datei lesen (UTF-8)")
    parser.add_argument("--stdin", action="store_true", help="Text von STDIN lesen")
    parser.add_argument("--rate", type=int, help="Sprechgeschwindigkeit für pyttsx3 (z. B. 170)")
    parser.add_argument("--volume", type=float, help="Lautstärke 0.0–1.0 für pyttsx3")
    parser.add_argument("--voice-index", type=int, help="pyttsx3 Voice-Index")

    args = parser.parse_args()

    # Engine-Wahl & Parameter anpassen
    if args.piper:
        use_piper = True
    if args.pyttsx3:
        use_piper = False
    if args.rate is not None:
        tts_rate = args.rate
    if args.volume is not None:
        tts_volume = args.volume
    if args.voice_index is not None:
        tts_voice_index = args.voice_index

    # Textquelle bestimmen
    collected = []
    if args.text:
        collected.append(args.text)
    if args.file:
        from pathlib import Path
        p = Path(args.file)
        if not p.exists():
            print(f"[ERROR] Datei nicht gefunden: {p}")
            sys.exit(2)
        collected.append(p.read_text(encoding="utf-8"))
    if args.stdin:
        collected.append(sys.stdin.read())

    if not collected:
        parser.print_help()
        sys.exit(1)

    text_input = "\n".join([s.strip() for s in collected if s.strip()])
    if not text_input:
        print("[INFO] Kein Text nach dem Filtern.")
        sys.exit(0)

    speak_text(text_input)
