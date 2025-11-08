import os
import re
import json
import shutil
import requests
import yaml
from pathlib import Path

# ==== CONFIG LADEN ====
CONFIG_PATH = Path("config.yaml")
if not CONFIG_PATH.exists():
    raise FileNotFoundError("config.yaml fehlt! Bitte anlegen.")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f) or {}

api_token = CONFIG["api_token"]
tournament_id = str(CONFIG["tournament_id"])

def safe_slug(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"[^A-Za-z0-9äöüÄÖÜß\-]+", "_", s)
    return s[:64].strip("_") or "x"

# Pfade pro Turnier in data/<tournament>/...
BASE_DIR = Path("data") / safe_slug(tournament_id)
output_dir = BASE_DIR / "announcements"
state_file = BASE_DIR / "seen_matches.json"

headers = {'Authorization': api_token}
courts_url = (
    f'https://api.tournament.io/v1/public/tournaments/{tournament_id}/courts?includeMatchDetails=true'
)


def ensure_dirs():
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        Path("voices").mkdir(parents=True, exist_ok=True)
        BASE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"[ERROR] Konnte Verzeichnisse nicht anlegen: {e}")


def load_state():
    if state_file.exists():
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}


def save_state(state):
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] Konnte State nicht speichern: {e}")


def fetch_courts():
    try:
        r = requests.get(courts_url, headers=headers, timeout=15)
        if r.status_code != 200:
            print(f"[HTTP {r.status_code}] {r.text[:200]}")
            return None
        return r.json()
    except Exception as e:
        print(f"[ERROR] Laden der Courts: {e}")
        return None


def extract_match_info_from_court(court_obj):
    """Gibt (tischname, match_id, team_a, team_b, has_full_match) zurück."""
    if not isinstance(court_obj, dict):
        return None, None, None, None, False

    tischname = str(court_obj.get("name", "")).strip() or None
    current_match = court_obj.get("currentMatch") or {}
    match_id = current_match.get("id")
    entries = current_match.get("entries") or []
    team_a = entries[0].get("name") if len(entries) >= 1 else None
    team_b = entries[1].get("name") if len(entries) >= 2 else None

    has_full = bool(tischname and match_id and team_a and team_b)
    return tischname, (str(match_id) if match_id else None), team_a, team_b, has_full
