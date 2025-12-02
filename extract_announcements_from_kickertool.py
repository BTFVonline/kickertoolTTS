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

def _entry_to_team_name(entry):
    """
    Normalize a team entry from the Tournament API to a readable team name.
    MonsterDYP liefert hier z.B. verschachtelte Listen von Spieler-Objekten,
    waehrend klassische Formate ein Dict mit "name" enthalten.
    """
    if not entry:
        return None

    # Klassisches Format: {"name": "..."}
    if isinstance(entry, dict):
        for key in ("name", "teamName", "playerName", "displayName"):
            value = entry.get(key)
            if value:
                value = str(value).strip()
                if value:
                    return value
        return None

    # MonsterDYP: Liste von Spielern -> Namen zusammenfassen
    if isinstance(entry, list):
        parts = []
        for member in entry:
            if isinstance(member, dict):
                name = (
                    member.get("name")
                    or member.get("teamName")
                    or member.get("playerName")
                    or member.get("displayName")
                )
                if name:
                    text = str(name).strip()
                    if text:
                        parts.append(text)
            elif member is not None:
                text = str(member).strip()
                if text:
                    parts.append(text)
        if parts:
            return " & ".join(parts)
        return None

    # Fallback: direkte String-Repraesentation
    if isinstance(entry, str):
        text = entry.strip()
        return text or None
    return str(entry)

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

    tischname_raw = court_obj.get("name", "")
    tischname = str(tischname_raw).strip() or None

    current_match = court_obj.get("currentMatch")
    if not isinstance(current_match, dict):
        return tischname, None, None, None, False

    match_id = current_match.get("id")
    entries = current_match.get("entries") or []
    if not isinstance(entries, list):
        entries = [entries]
    team_a = _entry_to_team_name(entries[0]) if len(entries) >= 1 else None
    team_b = _entry_to_team_name(entries[1]) if len(entries) >= 2 else None

    has_full = bool(tischname and match_id and team_a and team_b)
    return tischname, (str(match_id) if match_id else None), team_a, team_b, has_full
