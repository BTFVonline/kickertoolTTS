#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import yaml
from datetime import datetime
from pathlib import Path
from extract_announcements_from_kickertool import (
    ensure_dirs, load_state, save_state, fetch_courts, extract_match_info_from_court, safe_slug
)
from text_to_speech import speak_text

# ==== CONFIG LADEN ====
CONFIG_PATH = Path("config.yaml")
if not CONFIG_PATH.exists():
    raise FileNotFoundError("config.yaml fehlt! Bitte anlegen.")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

poll_interval = CONFIG.get("poll_interval", 1)
write_announcement_files = CONFIG.get("files", {}).get("write_announcement_files", False)

output_dir = Path("announcements")
state_file = Path("seen_matches.json")
# ========================


def write_announcement_file(tischname: str, team_a: str, team_b: str, match_id: str):
    if not write_announcement_files:
        print(f"Tisch {tischname}: {team_a} gegen {team_b}")
        speak_text(f"Tisch {tischname}: {team_a} gegen {team_b}")
        return

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    fname = f"tisch_{safe_slug(tischname)}_{ts}_{safe_slug(match_id)}.txt"
    path = output_dir / fname
    line = f"Tisch {tischname}: {team_a} gegen {team_b}\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(line)
    print(f"✔ Neues Spiel auf Tisch {tischname} → Datei: {path.name}")
    print(f"   → {line.strip()}")
    speak_text(line.strip())


def main():
    ensure_dirs()
    state = load_state()
    print(f"Starte Überwachung aller Tische. Polling alle {poll_interval}s.")
    print(f"Ausgabeordner: {output_dir.resolve()}")
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
