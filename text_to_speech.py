import os
import re
import sys
import shutil
import yaml
import argparse
import subprocess
import tempfile
import unicodedata
from pathlib import Path
from typing import Callable, Optional

# Optional: pyttsx3 Fallback
try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

# =========================
# Config laden (config.yaml)
# =========================
CONFIG_PATH = Path("config.yaml")
if not CONFIG_PATH.exists():
    DEFAULT_CONFIG = {}
else:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        DEFAULT_CONFIG = yaml.safe_load(f) or {}

TTS_CFG = (DEFAULT_CONFIG.get("tts") or {})
FILES_CFG = (DEFAULT_CONFIG.get("files") or {})

# ---- Defaults aus YAML (mit Fallbacks) ----
provider = (TTS_CFG.get("provider") or "piper").lower()          # "piper" | "pyttsx3"
use_piper = provider == "piper"

# Piper-Optionen
piper_model_path = str(TTS_CFG.get("model_path", "voices/de_DE-thorsten-medium.onnx"))
piper_speaker = TTS_CFG.get("speaker")          # z.B. 0 oder None
piper_length_scale = float(TTS_CFG.get("length_scale", 0.95))
piper_noise_scale  = float(TTS_CFG.get("noise_scale", 0.5))
piper_noise_w      = float(TTS_CFG.get("noise_w", 0.8))

# pyttsx3-Optionen
tts_rate = int(TTS_CFG.get("rate", 170))
tts_volume = float(TTS_CFG.get("volume", 1.0))
tts_voice_index = TTS_CFG.get("voice_index")    # int oder None

# Dateien
save_audio = bool(FILES_CFG.get("save_audio", False))
_tts_muted = False

# Pfad zu piper-Executable
if os.name == "nt":
    piper_executable = str(Path(".venv") / "Scripts" / "piper.exe")
else:
    piper_executable = "piper"


def _play_wav(path: str):
    """Spielt eine WAV-Datei möglichst portabel ab (blocking)."""
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


def _piper_generate_audio(text: str,
                          exe="piper",
                          model_path="voices/de_DE-thorsten-medium.onnx",
                          speaker=None,
                          length_scale=0.95,
                          noise_scale=0.5,
                          noise_w=0.8,
                          persist=False) -> Optional[str]:
    exe_path = exe
    if os.name == "nt" and not Path(exe_path).exists():
        exe_path = "piper"

    if shutil.which(exe_path) is None and not Path(exe_path).exists():
        print(f"[WARN] Piper nicht gefunden unter: {exe_path}")
        return None

    model_path = Path(model_path)
    json_path = Path(str(model_path) + ".json")
    if not model_path.exists() or not json_path.exists():
        print("[WARN] Piper-Model oder Config fehlt.")
        return None

    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name.replace("\\", "/")

        cmd = [
            exe_path, "--model", str(model_path), "--config", str(json_path),
            "--output_file", wav_path,
            "--length_scale", str(length_scale),
            "--noise_scale", str(noise_scale),
            "--noise_w", str(noise_w),
        ]
        if speaker is not None:
            cmd += ["--speaker", str(speaker)]

        subprocess.run(cmd, input=_normalize_text_for_tts(text).encode("ansi"), check=True)
        if persist:
            print(f"[INFO] Audio gespeichert: {wav_path}")
        return wav_path
    except Exception as e:
        print(f"[WARN] Piper Fehler: {e}")
        try:
            if wav_path:
                os.remove(wav_path)
        except Exception:
            pass
        return None


def _piper_say_once(text: str,
                    exe="piper",
                    model_path="voices/de_DE-thorsten-medium.onnx",
                    speaker=None,
                    length_scale=0.95,
                    noise_scale=0.5,
                    noise_w=0.8,
                    keep_file=False) -> bool:
    wav_path = _piper_generate_audio(
        text=text,
        exe=exe,
        model_path=model_path,
        speaker=speaker,
        length_scale=length_scale,
        noise_scale=noise_scale,
        noise_w=noise_w,
        persist=keep_file,
    )
    if not wav_path:
        return False
    _play_wav(wav_path)
    if not keep_file:
        _safe_delete(wav_path)
    return True


def _safe_delete(path: str):
    if not path:
        return
    try:
        os.remove(path)
    except Exception:
        pass


def set_tts_muted(value: bool):
    global _tts_muted
    _tts_muted = bool(value)


def _pyttsx3_say(text: str, rate=170, volume=1.0, voice_index=None) -> bool:
    try:
        import pyttsx3  # sicherstellen, dass Importfehler sauber handled werden
    except Exception:
        return False
    try:
        engine = pyttsx3.init()
        engine.setProperty('rate', rate)
        engine.setProperty('volume', volume)
        if voice_index is not None:
            voices = engine.getProperty('voices') or []
            if 0 <= int(voice_index) < len(voices):
                engine.setProperty('voice', voices[int(voice_index)].id)
        engine.say(_normalize_text_for_tts(text))
        engine.runAndWait()
        engine.stop()
        del engine
        return True
    except Exception as e:
        print(f"[WARN] TTS-Fehler (pyttsx3): {e}")
        return False


def _build_piper_job(text: str) -> Optional[Callable[[], None]]:
    wav_path = _piper_generate_audio(
        text=text,
        exe=piper_executable,
        model_path=piper_model_path,
        speaker=piper_speaker,
        length_scale=piper_length_scale,
        noise_scale=piper_noise_scale,
        noise_w=piper_noise_w,
        persist=save_audio,
    )
    if not wav_path:
        text2 = _umlaut_fallback(text)
        if text2 != text:
            wav_path = _piper_generate_audio(
                text=text2,
                exe=piper_executable,
                model_path=piper_model_path,
                speaker=piper_speaker,
                length_scale=piper_length_scale,
                noise_scale=piper_noise_scale,
                noise_w=piper_noise_w,
                persist=save_audio,
            )
    if not wav_path:
        return None

    def _player():
        if _tts_muted:
            if not save_audio:
                _safe_delete(wav_path)
            return
        _play_wav(wav_path)
        if not save_audio:
            _safe_delete(wav_path)

    return _player


def _build_pyttsx_job(text: str) -> Callable[[], None]:
    def _player():
        if _tts_muted:
            return
        _pyttsx3_say(text, rate=tts_rate, volume=tts_volume, voice_index=tts_voice_index)

    return _player


def prepare_tts_playback(text: str) -> Optional[Callable[[], None]]:
    provider = (TTS_CFG.get("provider") or "piper").lower()
    job = None
    if provider == "piper":
        job = _build_piper_job(text)
        if job:
            return job
        return _build_pyttsx_job(text)
    else:
        job = _build_pyttsx_job(text)
        if job:
            return job
        return _build_piper_job(text)


def speak_text(text: str):
    job = prepare_tts_playback(text)
    if job:
        job()
    else:
        print("[WARN] Keine TTS-Ausgabe möglich.")


# =========================
# CLI (Standalone-Nutzung)
# =========================
def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Einfaches TTS-CLI (liest config.yaml; CLI-Flags überschreiben YAML)."
    )
    g_engine = p.add_mutually_exclusive_group()
    g_engine.add_argument("--piper", action="store_true", help="Piper erzwingen")
    g_engine.add_argument("--pyttsx3", action="store_true", help="pyttsx3 erzwingen")

    p.add_argument("-t", "--text", help="Direkter Text")
    p.add_argument("-f", "--file", help="Text aus Datei lesen (UTF-8)")
    p.add_argument("--stdin", action="store_true", help="Text von STDIN lesen")

    p.add_argument("--model", dest="model_path", help="Piper: Pfad zum .onnx-Modell")
    p.add_argument("--speaker", type=int, help="Piper: Speaker-ID (z.B. 0)")
    p.add_argument("--length-scale", type=float, help="Piper: length_scale")
    p.add_argument("--noise-scale", type=float, help="Piper: noise_scale")
    p.add_argument("--noise-w", type=float, help="Piper: noise_w")

    p.add_argument("--rate", type=int, help="pyttsx3: Sprechgeschwindigkeit")
    p.add_argument("--volume", type=float, help="pyttsx3: Lautstärke 0.0–1.0")
    p.add_argument("--voice-index", type=int, help="pyttsx3: Voice-Index")

    p.add_argument("--save-audio", action="store_true", help="WAV nicht löschen")
    p.add_argument("--no-save-audio", action="store_true", help="WAV nach Abspielen löschen")
    return p


def _apply_overrides_from_args(args):
    global TTS_CFG, save_audio
    # Provider-Override
    if args.piper:
        TTS_CFG["provider"] = "piper"
    if args.pyttsx3:
        TTS_CFG["provider"] = "pyttsx3"

    # Piper
    if args.model_path is not None:
        globals()["piper_model_path"] = args.model_path
    if args.speaker is not None:
        globals()["piper_speaker"] = args.speaker
    if args.length_scale is not None:
        globals()["piper_length_scale"] = args.length_scale
    if args.noise_scale is not None:
        globals()["piper_noise_scale"] = args.noise_scale
    if args.noise_w is not None:
        globals()["piper_noise_w"] = args.noise_w

    # pyttsx3
    if args.rate is not None:
        globals()["tts_rate"] = args.rate
    if args.volume is not None:
        globals()["tts_volume"] = args.volume
    if args.voice_index is not None:
        globals()["tts_voice_index"] = args.voice_index

    # Files
    if args.save_audio:
        save_audio = True
    if args.no_save_audio:
        save_audio = False


def _collect_text_from_sources(args) -> str:
    chunks = []
    if args.text:
        chunks.append(args.text)
    if args.file:
        p = Path(args.file)
        if not p.exists():
            print(f"[ERROR] Datei nicht gefunden: {p}")
            sys.exit(2)
        chunks.append(p.read_text(encoding="utf-8"))
    if args.stdin:
        chunks.append(sys.stdin.read())
    return "\n".join(s.strip() for s in chunks if s and s.strip())


if __name__ == "__main__":
    parser = _build_arg_parser()
    args = parser.parse_args()
    _apply_overrides_from_args(args)

    text_input = _collect_text_from_sources(args)
    if not text_input:
        parser.print_help()
        sys.exit(1)

    speak_text(text_input)
