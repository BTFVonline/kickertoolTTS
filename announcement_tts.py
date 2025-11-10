#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import time
import json
import yaml
import shutil
import subprocess
import threading
import atexit
from queue import Queue
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime
from pathlib import Path
from collections import deque
from extract_announcements_from_kickertool import (
    ensure_dirs, load_state, save_state, fetch_courts,
    extract_match_info_from_court, safe_slug, output_dir, BASE_DIR
)
from text_to_speech import prepare_tts_playback, set_tts_muted

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
speech_template_doubles = (announcement_cfg.get("speech_template_doubles") or "").strip()
notify_sound_raw = (announcement_cfg.get("notify_sound") or "").strip()
notify_sound = notify_sound_raw or None
resume_after_raw = announcement_cfg.get("notify_resume_after_seconds")
if resume_after_raw is None:
    resume_after_raw = announcement_cfg.get("notify_cooldown_seconds")
notify_resume_after_seconds = float(resume_after_raw or 0)
announcements_enabled = bool(announcement_cfg.get("enabled", True))
mute_enabled = bool(announcement_cfg.get("mute", False))
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

_UI_TTY = sys.stdout.isatty()
_console_lock = threading.Lock()
_announcements_state_lock = threading.Lock()
_mute_state_lock = threading.Lock()
_tts_preload_lock = threading.Lock()
_tts_preload_executor = ThreadPoolExecutor(max_workers=max(2, ((os.cpu_count() or 2) // 2) or 1))
_tts_preloaded_jobs: dict[str, Future] = {}
_announcement_queue: "Queue[tuple[str, str]]" = Queue()
_announcement_meta: dict[str, dict] = {}
_announcement_order: deque[str] = deque()
_current_announcement_key: str | None = None
_notify_skip_logged = False
_log_history: deque[str] = deque(maxlen=15)
_announcement_history: deque[tuple[str, str]] = deque(maxlen=20)  # (cache_key, text)
_show_logs_panel = False
history_file = BASE_DIR / "announcement_history.json"
set_tts_muted(mute_enabled)

def clear_screen():
    try:
        os.system("cls" if os.name == "nt" else "clear")
    except Exception:
        pass

def show_banner():
    if _UI_TTY:
        render_ui()
    else:
        clear_screen()
        print(ASCII_LOGO)
        print(" " * 36 + "Kickertool TTS\n")
        print("-" * 100)
        print("Konsole unterstützt kein Live-UI. Logs folgen im Scroll.")


def _is_announcements_enabled() -> bool:
    with _announcements_state_lock:
        return announcements_enabled


def _set_announcements_enabled(value: bool, source: str = "Config"):
    global announcements_enabled
    value = bool(value)
    with _announcements_state_lock:
        previous = announcements_enabled
        announcements_enabled = value
    if previous != value:
        state = "AKTIV" if value else "PAUSIERT"
        ui_log(f"Ansagen {state} (Quelle: {source}).")


def _toggle_announcements(source: str = "Konsole"):
    _set_announcements_enabled(not _is_announcements_enabled(), source=source)


def render_ui():
    if not _UI_TTY:
        return
    with _console_lock:
        clear_screen()
        width = shutil.get_terminal_size((120, 30)).columns
        width = max(60, width)
        print(ASCII_LOGO)
        print("Kickertool TTS".center(width))
        print("-" * width)
        status = "AKTIV" if _is_announcements_enabled() else "PAUSIERT"
        notify_state = "bereit" if notify_sound_path else "aus"
        mute_state = "stumm" if _is_muted() else "an"
        print(f"Ansagen: {status} | Ton: {mute_state} | Hinweiston: {notify_state} | Queue: {len(_announcement_order)}")
        pause_label = "[P]lay" if not _is_announcements_enabled() else "[P]ause"
        print(f"Befehle: {pause_label}, [M]ute, [R]eplay, [L]ogs")
        print("-" * width)
        print("Anstehende Durchsagen:")
        if not _announcement_order:
            print("  (keine)")
        else:
            for key in list(_announcement_order):
                meta = _announcement_meta.get(key)
                if not meta:
                    continue
                status_marker = "\u25B6" if meta.get("status") == "playing" else "\u2022"
                lines = meta["text"].splitlines() or [meta["text"]]
                if meta.get("status") == "playing" and _UI_TTY:
                    lines = [f"\x1b[32m{line}\x1b[0m" for line in lines]
                print(f"  {status_marker} {lines[0]}")
                for extra in lines[1:]:
                    print(f"    {extra}")
        print("-" * width)
        print("Letzte Durchsagen:")
        if not _announcement_history:
            print("  (keine)")
        else:
            for idx, (_, text) in enumerate(list(_announcement_history)[:5], start=1):
                lines = text.splitlines()
                primary = lines[0]
                if len(primary) > width - 6:
                    primary = primary[: width - 9] + "..."
                print(f"  {idx:>2}. {primary}")
        print("-" * width)
        if _show_logs_panel:
            print("Logs:")
            if not _log_history:
                print("  (keine)")
            else:
                for entry in _log_history:
                    print(f"  {entry}")
        else:
            print("Logs verborgen – 'logs' eingeben zum Anzeigen.")
        print("-" * width)


def ui_log(message: str, level: str = "INFO"):
    entry = f"[{level}] {message}"
    with _console_lock:
        _log_history.append(entry)
    if not _UI_TTY:
        print(entry)
    else:
        render_ui()


def _normalize_cache_key(cache_key: str | None, text: str) -> str:
    key = (cache_key or "").strip()
    if key:
        return key
    spoken = (text or "").strip()
    if spoken:
        return spoken
    return f"anon-{time.time_ns()}"


def _preload_tts_job(cache_key: str, text: str):
    spoken = (text or "").strip()
    if not spoken:
        return
    key = _normalize_cache_key(cache_key, spoken)
    with _tts_preload_lock:
        future = _tts_preloaded_jobs.get(key)
        if future and not future.done():
            return
        _tts_preloaded_jobs[key] = _tts_preload_executor.submit(prepare_tts_playback, spoken)


def _take_prepared_job(cache_key: str, text: str):
    key = _normalize_cache_key(cache_key, text)
    future: Future | None = None
    with _tts_preload_lock:
        future = _tts_preloaded_jobs.pop(key, None)
    job = None
    if future is not None:
        try:
            job = future.result()
        except Exception as exc:
            ui_log(f"Vorbereiten der TTS fehlgeschlagen: {exc}", level="WARN")
    if job is None:
        job = prepare_tts_playback(text)
    return job


def _queue_announcement(cache_key: str, text: str, *, record_history: bool = True):
    spoken = (text or "").strip()
    if not spoken:
        return
    _preload_tts_job(cache_key, spoken)
    _announcement_queue.put((cache_key, spoken))
    with _console_lock:
        _announcement_meta[cache_key] = {
            "text": spoken,
            "status": "queued",
            "record_history": record_history,
        }
        _announcement_order.append(cache_key)
    if not _is_announcements_enabled():
        ui_log("Ansagen pausiert – Durchsage wartet.")
    else:
        render_ui()


def _make_announcement_key(tischname: str | None, match_id: str | None, team_a: str | None, team_b: str | None) -> str:
    parts = [
        str(match_id or f"x{time.time_ns()}"),
        safe_slug(tischname or "tisch"),
        safe_slug(team_a or "team_a"),
        safe_slug(team_b or "team_b"),
        str(time.time_ns()),
    ]
    return "|".join(parts)


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


TEAM_DELIMITER_PATTERN = re.compile(r"\s*(?:/|&|\+|\bund\b)\s*", re.IGNORECASE)


def _split_team_members(name: str) -> list:
    if not (name or "").strip():
        return []
    raw = name.strip()
    if TEAM_DELIMITER_PATTERN.search(raw):
        return [part.strip() for part in TEAM_DELIMITER_PATTERN.split(raw) if part.strip()]
    return [raw]


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


def _add_member_placeholders(context: dict, prefix: str, members: list):
    prefix = prefix.upper()
    count = min(len(members), 2)
    for idx in range(count):
        info = _split_player_name(members[idx])
        slot = f"{prefix}_PLAYER{idx + 1}"
        context[f"{slot}_FULL"] = info["full"]
        context[f"{slot}_FULLNAME"] = info["full"]
        context[f"{slot}_FIRST"] = info["first"]
        context[f"{slot}_FIRSTNAME"] = info["first"]
        context[f"{slot}_NAME"] = info["first"]
        context[f"{slot}_SURNAME"] = info["last"]
        context[f"{slot}_LASTNAME"] = info["last"]
    for idx in range(count, 2):
        slot = f"{prefix}_PLAYER{idx + 1}"
        context[f"{slot}_FULL"] = ""
        context[f"{slot}_FULLNAME"] = ""
        context[f"{slot}_FIRST"] = ""
        context[f"{slot}_FIRSTNAME"] = ""
        context[f"{slot}_NAME"] = ""
        context[f"{slot}_SURNAME"] = ""
        context[f"{slot}_LASTNAME"] = ""


def _build_template_context(table: str, player_a: str, player_b: str) -> dict:
    team_a_members = _split_team_members(player_a)
    team_b_members = _split_team_members(player_b)
    primary_a = team_a_members[0] if team_a_members else (player_a or "")
    primary_b = team_b_members[0] if team_b_members else (player_b or "")
    p1 = _split_player_name(primary_a)
    p2 = _split_player_name(primary_b)
    is_doubles = max(len(team_a_members), len(team_b_members)) > 1
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
        "TEAM_A_MEMBER_COUNT": len(team_a_members),
        "TEAM_B_MEMBER_COUNT": len(team_b_members),
        "IS_DOUBLES": is_doubles,
        "IS_SINGLES": not is_doubles,
    }
    _add_member_placeholders(context, "TEAM_A", team_a_members)
    _add_member_placeholders(context, "TEAM_B", team_b_members)
    return _add_aliases(context)


def _render_template(template: str, context: dict) -> str:
    def replacer(match):
        raw_key = match.group(1)
        key = _normalize_placeholder_key(raw_key)
        if not key:
            return match.group(0)
        return str(context.get(key, match.group(0)))

    return TEMPLATE_PATTERN.sub(replacer, template)


def _select_template(context: dict) -> str:
    if context.get("IS_DOUBLES") and speech_template_doubles:
        return speech_template_doubles
    return speech_template or default_template


def format_spoken_text(table: str, player_a: str, player_b: str) -> str:
    context = _build_template_context(table, player_a, player_b)
    template = _select_template(context)
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
    global _last_speech_finished, _notify_skip_logged
    if _is_muted():
        return
    if not notify_sound_path:
        return
    now = time.monotonic()
    since_last = None
    if _last_speech_finished:
        since_last = now - _last_speech_finished
    if notify_resume_after_seconds > 0 and since_last is not None:
        if since_last < notify_resume_after_seconds:
            if not _notify_skip_logged:
                remaining = max(0.0, notify_resume_after_seconds - since_last)
                ui_log(f"Hinweiston wartet noch {remaining:.1f}s.")
                _notify_skip_logged = True
            return
        elif _notify_skip_logged:
            ui_log("Hinweiston wieder aktiv.")
            _notify_skip_logged = False
    if not notify_sound_path.is_file():
        ui_log(f"Hinweiston nicht gefunden: {notify_sound_path}", level="WARN")
        return
    try:
        if os.name == "nt":
            played = _play_audio_windows(notify_sound_path)
        else:
            played = _play_with_system_player(notify_sound_path)
        if not played:
            ui_log(f"Konnte Hinweiston {notify_sound_path} nicht abspielen.", level="WARN")
            return
        _notify_skip_logged = False
        if since_last is None:
            ui_log("Hinweiston abgespielt (erste Ansage).")
        else:
            ui_log(f"Hinweiston abgespielt (Pause {since_last:.1f}s).")
    except Exception as exc:
        ui_log(f"Hinweiston-Fehler: {exc}", level="WARN")


def _announce_text(cache_key: str, text: str):
    global _last_speech_finished
    spoken = (text or "").strip()
    if not spoken:
        return
    job = _take_prepared_job(cache_key, spoken)
    if job is None:
        ui_log("Konnte TTS nicht vorbereiten – Hinweiston übersprungen.", level="WARN")
        return
    play_notification_sound()
    job()
    _last_speech_finished = time.monotonic()
    with _console_lock:
        meta = _announcement_meta.get(cache_key, {})
        if meta.get("record_history", True):
            _announcement_history.appendleft((cache_key, text))
    _persist_history()


def _announcement_worker():
    global _current_announcement_key
    while True:
        cache_key, text = _announcement_queue.get()
        try:
            while not _is_announcements_enabled():
                time.sleep(0.25)
            with _console_lock:
                meta = _announcement_meta.get(cache_key)
                if meta:
                    meta["status"] = "playing"
                _current_announcement_key = cache_key
            render_ui()
            _announce_text(cache_key, text)
        except Exception as exc:
            ui_log(f"TTS-Worker-Fehler: {exc}", level="WARN")
        finally:
            with _console_lock:
                _announcement_meta.pop(cache_key, None)
                try:
                    _announcement_order.remove(cache_key)
                except ValueError:
                    pass
                if _current_announcement_key == cache_key:
                    _current_announcement_key = None
            render_ui()
            _announcement_queue.task_done()


_announcement_thread = threading.Thread(target=_announcement_worker, daemon=True, name="announcement-player")
_announcement_thread.start()


def _command_listener():
    while True:
        try:
            raw = sys.stdin.readline()
        except Exception:
            break
        if raw == "":
            time.sleep(0.25)
            continue
        raw_cmd = raw.strip()
        if not raw_cmd:
            continue
        parts = raw_cmd.split(maxsplit=1)
        base = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        if base in ("pause", "p"):
            _set_announcements_enabled(not _is_announcements_enabled(), "Konsole")
        elif base in ("mute", "m"):
            _toggle_mute("Konsole")
        elif base in ("logs", "l"):
            _toggle_logs_panel()
        elif base in ("replay", "r"):
            cmd_for_replay = f"replay {arg}".strip() if arg else "replay"
            _handle_replay_command(cmd_for_replay.lower())
        else:
            ui_log(f"Unbekannter Befehl '{raw_cmd}'. Verfügbar: p, mute, replay, logs.")


_command_thread = threading.Thread(target=_command_listener, daemon=True, name="command-listener")
_command_thread.start()


def _handle_replay_command(cmd: str):
    args = cmd.split()
    if len(args) == 1:
        _print_replay_list()
        return
    selection = args[1]
    if "-" in selection:
        start_str, end_str = selection.split("-", 1)
        try:
            start = int(start_str)
            end = int(end_str)
        except ValueError:
            ui_log("Ungültiger Bereich. Beispiel: replay 1-3", level="WARN")
            return
        if start < 1 or end < start:
            ui_log("Bereich außerhalb der verfügbaren Einträge.", level="WARN")
            return
        entries = list(_announcement_history)
        to_replay = entries[start - 1 : end]
    else:
        try:
            index = int(selection)
        except ValueError:
            ui_log("Ungültige Auswahl. Beispiel: replay 2 oder replay 1-3", level="WARN")
            return
        if index < 1 or index > len(_announcement_history):
            ui_log("Auswahl außerhalb der letzten Einträge.", level="WARN")
            return
        entries = list(_announcement_history)
        to_replay = [entries[index - 1]]

    for _, text in reversed(to_replay):
        replay_key = _make_announcement_key("replay", None, "", "")
        _queue_announcement(replay_key, text, record_history=False)
    ui_log(f"{len(to_replay)} Durchsage(n) erneut eingereiht.")


def _print_replay_list():
    if not _announcement_history:
        ui_log("Noch keine vergangenen Durchsagen vorhanden.", level="INFO")
        return
    lines = ["Letzte Durchsagen:"]
    entries = list(_announcement_history)[:10]
    for idx, (_, text) in enumerate(entries, start=1):
        snippet = text.replace("\n", " ")
        if len(snippet) > 90:
            snippet = snippet[:87] + "..."
        lines.append(f"{idx:>2}: {snippet}")
    ui_log("\n".join(lines))


def _toggle_logs_panel():
    global _show_logs_panel
    with _console_lock:
        _show_logs_panel = not _show_logs_panel
    ui_log(f"Log-Panel {'sichtbar' if _show_logs_panel else 'ausgeblendet'}")


def _is_muted() -> bool:
    with _mute_state_lock:
        return mute_enabled


def _set_muted(value: bool, source: str = "Config"):
    global mute_enabled
    value = bool(value)
    with _mute_state_lock:
        previous = mute_enabled
        mute_enabled = value
    if previous != value:
        set_tts_muted(value)
        state = "STUMM" if value else "AN"
        ui_log(f"Ton {state} (Quelle: {source}).")
    else:
        set_tts_muted(value)


def _toggle_mute(source: str = "Konsole"):
    _set_muted(not _is_muted(), source=source)


def _load_persisted_history():
    if not history_file.exists():
        return
    try:
        data = json.loads(history_file.read_text(encoding="utf-8"))
        if isinstance(data, list):
            for entry in data[:20]:
                key = entry.get("id") or f"history-{len(_announcement_history)+1}"
                text = entry.get("text") or ""
                if text:
                    _announcement_history.append((key, text))
    except Exception as exc:
        ui_log(f"Konnte History nicht laden: {exc}", level="WARN")


def _persist_history():
    try:
        history_file.parent.mkdir(parents=True, exist_ok=True)
        payload = [{"id": key, "text": text} for key, text in list(_announcement_history)]
        history_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        ui_log(f"Konnte History nicht speichern: {exc}", level="WARN")


_load_persisted_history()


# ==== ANKÜNDIGUNGSSYSTEM ====
def write_announcement_file(tischname: str, team_a: str, team_b: str, match_id: str):
    spoken_text = format_spoken_text(tischname, team_a, team_b)
    announcement_key = _make_announcement_key(tischname, match_id, team_a, team_b)
    if not write_announcement_files:
        ui_log(spoken_text)
        _queue_announcement(announcement_key, spoken_text)
        return

    try:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        fname = f"tisch_{safe_slug(tischname)}_{ts}_{safe_slug(match_id)}.txt"
        path = output_dir / fname
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(spoken_text + "\n")
        ui_log(f"Neues Spiel auf Tisch {tischname} – Datei: {path}")
        ui_log(f"   {spoken_text}")
    except Exception as e:
        ui_log(f"Konnte Ankündigungsdatei nicht schreiben: {e}", level="ERROR")
    finally:
        _queue_announcement(announcement_key, spoken_text)

def main():
    show_banner()  # Logo und CLS beim Start
    ensure_dirs()
    state = load_state()

    ui_log(f"Starte Überwachung aller Tische. Polling alle {poll_interval}s.")
    ui_log(f"Schreibe Ankündigungen: {'JA' if write_announcement_files else 'NEIN'}")
    if write_announcement_files:
        ui_log(f"Zielordner: {output_dir.resolve()}")
    ui_log("Beende mit STRG+C (CTRL+C).")

    while True:
        courts = fetch_courts()
        if isinstance(courts, list):
            for court in courts:
                tischname, match_id, team_a, team_b, has_full = extract_match_info_from_court(court)

                if not tischname:
                    continue

                if not has_full:
                    if state.get(tischname) is not None:
                        ui_log(f"Tisch {tischname}: kein aktives Match – State reset")
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
            ui_log("Konnte Court-Liste nicht laden oder Response-Format unerwartet.", level="WARN")

        time.sleep(poll_interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        ui_log("Überwachung beendet.")
    except Exception as e:
        ui_log(f"FATAL: {e}", level="FATAL")
