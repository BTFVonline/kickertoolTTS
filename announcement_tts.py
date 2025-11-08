#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import yaml
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


# ==== ANKÜNDIGUNGSSYSTEM ====
def write_announcement_file(tischname: str, team_a: str, team_b: str, match_id: str):
    line = f"Tisch {tischname}: {team_a} gegen {team_b}"
    if not write_announcement_files:
        print(line)
        speak_text(line)
        return

    try:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        fname = f"tisch_{safe_slug(tischname)}_{ts}_{safe_slug(match_id)}.txt"
        path = output_dir / fname
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(line + "\n")
        print(f"✔ Neues Spiel auf Tisch {tischname} → Datei: {path}")
        print(f"   → {line}")
    except Exception as e:
        print(f"[ERROR] Konnte Ankündigungsdatei nicht schreiben: {e}")
    finally:
        speak_text(line)


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
