#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import time
import yaml
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from extract_announcements_from_kickertool import (
    ensure_dirs, load_state, save_state, fetch_courts,
    extract_match_info_from_court, safe_slug, output_dir
)
from text_to_speech import speak_text

# ==== CONFIG LADEN ====
CONFIG_PATH = Path("config.yaml")
if not CONFIG_PATH.exists():
    raise FileNotFoundError("config.yaml fehlt! Bitte anlegen.")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f) or {}

poll_interval = CONFIG.get("poll_interval", 1)
write_announcement_files = CONFIG.get("files", {}).get("write_announcement_files", False)
announcement_cfg = CONFIG.get("announcement") or {}
default_template = "Tisch {TABLE}: {PLAYER1_FULL} gegen {PLAYER2_FULL}"
speech_template = (announcement_cfg.get("speech_template") or default_template).strip()
notify_sound_raw = (announcement_cfg.get("notify_sound") or "").strip()
notify_sound = notify_sound_raw or None
resume_after_raw = announcement_cfg.get("notify_resume_after_seconds")
if resume_after_raw is None:
    resume_after_raw = announcement_cfg.get("notify_cooldown_seconds")
notify_resume_after_seconds = float(resume_after_raw or 0)
notify_sound_path = None
if notify_sound:
    p = Path(notify_sound)
    if not p.is_absolute():
        p = (CONFIG_PATH.parent / p).resolve()
    notify_sound_path = p
notify_sound_name = notify_sound_path.name if notify_sound_path else (Path(notify_sound).name if notify_sound else "")

# ==== ASCII-LOGO ====
ASCII_LOGO = r"""
██╗  ██╗██╗ ██████╗██╗  ██╗███████╗██████╗ ████████╗ ██████╗  ██████╗ ██╗  ████████╗████████╗███████╗
██║ ██╔╝██║██╔════╝██║ ██╔╝██╔════╝██╔══██╗╚══██╔══╝██╔═══██╗██╔═══██╗██║  ╚══██╔══╝╚══██╔══╝██╔════╝
█████╔╝ ██║██║     █████╔╝ █████╗  ██████╔╝   ██║   ██║   ██║██║   ██║██║     ██║      ██║   ███████╗
██╔═██╗ ██║██║     ██╔═██╗ ██╔══╝  ██╔══██╗   ██║   ██║   ██║██║   ██║██║     ██║      ██║   ╚════██║
██║  ██╗██║╚██████╗██║  ██╗███████╗██║  ██║   ██║   ╚██████╔╝╚██████╔╝███████╗██║      ██║   ███████║
╚═╝  ╚═╝╚═╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝   ╚═╝    ╚═════╝  ╚═════╝ ╚══════╝╚═╝      ╚═╝   ╚══════╝
                                                                                                     
"""

def clear_screen():
    try:
        os.system("cls" if os.name == "nt" else "clear")
    except Exception:
        pass

def show_banner():
    clear_screen()
    print(ASCII_LOGO)
    print(" " * 36 + "Kickertool TTS\n")
    print("-" * 100)


def _split_player_name(name: str) -> dict:
    name = (name or "").strip()
    if not name:
        return {"full": "", "first": "", "last": ""}

    if "," in name:
        last, first = [part.strip() for part in name.split(",", 1)]
    else:
        parts = name.split()
        if len(parts) == 1:
            first, last = parts[0], parts[0]
        else:
            first = parts[0]
            last = parts[-1]

    first = first or name
    last = last or name
    return {"full": name, "first": first, "last": last}


TEMPLATE_PATTERN = re.compile(r"{([^{}]+)}")


def _normalize_placeholder_key(raw: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", raw.strip())
    return cleaned.upper().strip("_")


def _add_aliases(context: dict) -> dict:
    enriched = {}
    for key, value in context.items():
        if not key:
            continue
        variants = {
            key,
            key.upper(),
            key.lower(),
            _normalize_placeholder_key(key),
        }
        for variant in variants:
            if variant:
                enriched[variant] = value
    return enriched


def _build_template_context(table: str, player_a: str, player_b: str) -> dict:
    p1 = _split_player_name(player_a)
    p2 = _split_player_name(player_b)
    context = {
        "TABLE": table or "",
        "TABLE_NAME": table or "",
        "PLAYER1_FULL": p1["full"],
        "PLAYER1_FULLNAME": p1["full"],
        "PLAYER1_FIRST": p1["first"],
        "PLAYER1_FIRSTNAME": p1["first"],
        "PLAYER1_NAME": p1["first"],
        "PLAYER1_SURNAME": p1["last"],
        "PLAYER1_LASTNAME": p1["last"],
        "PLAYER2_FULL": p2["full"],
        "PLAYER2_FULLNAME": p2["full"],
        "PLAYER2_FIRST": p2["first"],
        "PLAYER2_FIRSTNAME": p2["first"],
        "PLAYER2_NAME": p2["first"],
        "PLAYER2_SURNAME": p2["last"],
        "PLAYER2_LASTNAME": p2["last"],
        "TEAM_A": player_a or "",
        "TEAM_B": player_b or "",
        "NOTIFY_SOUND": notify_sound_name or "",
        "NOTIFY_SOUND_NAME": notify_sound_name or "",
        "NOTIFY_SOUND_PATH": str(notify_sound_path) if notify_sound_path else (notify_sound or ""),
    }
    return _add_aliases(context)


def _render_template(template: str, context: dict) -> str:
    def replacer(match):
        raw_key = match.group(1)
        key = _normalize_placeholder_key(raw_key)
        if not key:
            return match.group(0)
        return str(context.get(key, match.group(0)))

    return TEMPLATE_PATTERN.sub(replacer, template)


def format_spoken_text(table: str, player_a: str, player_b: str) -> str:
    context = _build_template_context(table, player_a, player_b)
    template = speech_template or default_template
    text = _render_template(template, context).strip()
    if text:
        return text
    fallback = _render_template(default_template, context).strip()
    return fallback or default_template


def _escape_for_powershell(value: str) -> str:
    return value.replace("`", "``").replace('"', '`"')


def _play_with_wmplayer(audio_path: Path) -> bool:
    escaped = _escape_for_powershell(str(audio_path.resolve()))
    script = (
        "$ErrorActionPreference='Stop';"
        "$player = New-Object -ComObject WMPlayer.OCX.7;"
        f"$player.URL = \"{escaped}\";"
        "$player.controls.play();"
        "$tries = 0;"
        "while (((-not $player.currentMedia) -or $player.currentMedia.duration -le 0) -and $tries -lt 200) "
        "{ Start-Sleep -Milliseconds 50; $tries++; }"
        "$duration = 750;"
        "if ($player.currentMedia -and $player.currentMedia.duration -gt 0) "
        "{ $duration = [int]($player.currentMedia.duration * 1000); }"
        "[System.Threading.Thread]::Sleep($duration);"
        "$player.controls.stop();"
        "$player.close();"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def _play_with_system_player(audio_path: Path) -> bool:
    commands = [
        ["ffplay", "-autoexit", "-nodisp", "-loglevel", "quiet", str(audio_path)],
        ["afplay", str(audio_path)],
        ["aplay", str(audio_path)],
        ["mpg123", str(audio_path)],
        ["cvlc", "--play-and-exit", str(audio_path)],
        ["play", str(audio_path)],
    ]
    for cmd in commands:
        if shutil.which(cmd[0]):
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            return True
    return False


def _play_audio_windows(audio_path: Path) -> bool:
    suffix = audio_path.suffix.lower()
    if suffix == ".wav":
        try:
            import winsound  # type: ignore

            winsound.PlaySound(str(audio_path), winsound.SND_FILENAME)
            return True
        except Exception:
            pass
    if _play_with_presentation_core(audio_path):
        return True
    return _play_with_wmplayer(audio_path)


def _play_with_presentation_core(audio_path: Path) -> bool:
    uri = audio_path.resolve().as_uri()
    escaped_uri = _escape_for_powershell(uri)
    script = (
        "$ErrorActionPreference='Stop';"
        "Add-Type -AssemblyName PresentationCore;"
        "$player = New-Object System.Windows.Media.MediaPlayer;"
        f"$player.Open([Uri]\"{escaped_uri}\");"
        "$player.Volume = 1.0;"
        "$sw = [System.Diagnostics.Stopwatch]::StartNew();"
        "while (-not $player.NaturalDuration.HasTimeSpan -and $sw.ElapsedMilliseconds -lt 5000) "
        "{ Start-Sleep -Milliseconds 50; }"
        "$duration = 750;"
        "if ($player.NaturalDuration.HasTimeSpan) "
        "{ $duration = [int]$player.NaturalDuration.TimeSpan.TotalMilliseconds; }"
        "Start-Sleep -Milliseconds $duration;"
        "$player.Stop();"
        "$player.Close();"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


_last_speech_finished = 0.0


def play_notification_sound():
    global _last_speech_finished
    if not notify_sound_path:
        return
    now = time.monotonic()
    since_last = None
    if _last_speech_finished:
        since_last = now - _last_speech_finished
    if notify_resume_after_seconds > 0 and since_last is not None and since_last < notify_resume_after_seconds:
        print(
            f"[INFO] Hinweiston übersprungen: letzte TTS vor {since_last:.1f}s "
            f"(< {notify_resume_after_seconds}s)."
        )
        return
    if not notify_sound_path.is_file():
        print(f"[WARN] Hinweiston nicht gefunden: {notify_sound_path}")
        return
    try:
        if os.name == "nt":
            played = _play_audio_windows(notify_sound_path)
        else:
            played = _play_with_system_player(notify_sound_path)
        if not played:
            print(f"[WARN] Konnte Hinweiston {notify_sound_path} nicht abspielen.")
            return
        if since_last is None:
            print(f"[INFO] Hinweiston '{notify_sound_name}' abgespielt (erste Ansage).")
        else:
            print(
                f"[INFO] Hinweiston '{notify_sound_name}' abgespielt "
                f"(Pause {since_last:.1f}s)."
            )
    except Exception as exc:
        print(f"[WARN] Hinweiston-Fehler: {exc}")


def _announce_text(text: str):
    global _last_speech_finished
    play_notification_sound()
    if text.strip():
        speak_text(text)
        _last_speech_finished = time.monotonic()
        print("[INFO] TTS beendet – Pause-Timer zurückgesetzt.")


# ==== ANKÜNDIGUNGSSYSTEM ====
def write_announcement_file(tischname: str, team_a: str, team_b: str, match_id: str):
    spoken_text = format_spoken_text(tischname, team_a, team_b)
    if not write_announcement_files:
        print(spoken_text)
        _announce_text(spoken_text)
        return

    try:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        fname = f"tisch_{safe_slug(tischname)}_{ts}_{safe_slug(match_id)}.txt"
        path = output_dir / fname
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(spoken_text + "\n")
        print(f"-> Neues Spiel auf Tisch {tischname} - Datei: {path}")
        print(f"   -> {spoken_text}")
    except Exception as e:
        print(f"[ERROR] Konnte Ankündigungsdatei nicht schreiben: {e}")
    finally:
        _announce_text(spoken_text)

def main():
    show_banner()  # Logo und CLS beim Start
    ensure_dirs()
    state = load_state()

    print(f"Starte Überwachung aller Tische. Polling alle {poll_interval}s.")
    print(f"Schreibe Ankündigungen: {'JA' if write_announcement_files else 'NEIN'}")
    if write_announcement_files:
        print(f"Zielordner: {output_dir.resolve()}")
    print("Beende mit STRG+C.\n")

    while True:
        courts = fetch_courts()
        if isinstance(courts, list):
            for court in courts:
                tischname, match_id, team_a, team_b, has_full = extract_match_info_from_court(court)

                if not tischname:
                    continue

                if not has_full:
                    if state.get(tischname) is not None:
                        print(f"[INFO] Tisch {tischname}: kein aktives Match → State reset")
                        state[tischname] = None
                        save_state(state)
                    continue

                key = f"{match_id}|{team_a}|{team_b}"
                last_key = state.get(tischname)

                if last_key != key:
                    write_announcement_file(tischname, team_a, team_b, match_id)
                    state[tischname] = key
                    save_state(state)
        else:
            print("[WARN] Konnte Court-Liste nicht laden oder Response-Format unerwartet.")

        time.sleep(poll_interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nÜberwachung beendet.")
    except Exception as e:
        print(f"[FATAL] {e}")
