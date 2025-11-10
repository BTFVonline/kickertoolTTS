# Kickertool TTS

Ein kleines Helferlein, das neue Matches aus der Tournament-API abholt und per Text-to-Speech (Piper oder pyttsx3) ansagt. Optional werden die Texte als Dateien gespeichert und es kann vor jeder Ansage ein Hinweiston abgespielt werden.

## Voraussetzungen

- Python 3.10+
- Abhängigkeiten per `pip install -r requirements.txt` bzw. vorhandenes `.venv` verwenden
- Piper-Modell (z. B. `voices/de_DE-thorsten-medium.onnx`) oder ein funktionierendes pyttsx3-Setup

## Schnellstart

1. `config.yaml.example` nach `config.yaml` kopieren und API-Daten (`api_token`, `tournament_id`) eintragen.
2. Gewünschten TTS-Provider und Optionen konfigurieren (Piper-Modellpfad, pyttsx3-Stimme, etc.).
3. Optional einen Hinweiston (WAV) angeben – relative Pfade beziehen sich auf das Projektverzeichnis.
4. Skript starten:

   ```bash
   python announcement_tts.py
   ```

5. Das Tool pollt die Courts, merkt sich bereits angesagte Matches und ruft neue Spiele automatisch aus.

## Konfiguration

| Abschnitt        | Beschreibung                                                                 |
| ---------------- | ----------------------------------------------------------------------------- |
| `api_token`      | Bearer Token für die Tournament-API.                                          |
| `tournament_id`  | Turnier-ID (z. B. `tio:abcd...`).                                             |
| `poll_interval`  | Abfrageintervall in Sekunden.                                                 |
| `tts`            | Einstellungen für Piper oder pyttsx3 (Geschwindigkeit, Lautstärke, Modell …). |
| `files`          | `save_audio` behält WAV-Dateien, `write_announcement_files` erstellt Textdateien unter `data/<tournament>/announcements`. |
| `announcement`   | Optionen für Hinweiston und Ansagetext (siehe unten).                         |

### Announcement-Optionen

- `notify_sound`: Pfad zu einer WAV-Datei (mp3 wird derzeit nicht unterstützt). Wird relativ zu `config.yaml` aufgelöst.
- `notify_resume_after_seconds`: Mindestzeit ohne TTS, bevor der Sound erneut abgespielt wird.
- `enabled`: Bestimmt, ob beim Start automatisch Ansagen abgespielt werden (Konsole: `p` schaltet zwischen Pause/Play).
- `mute`: Schaltet die TTS-Ausgabe beim Start stumm (Konsole: `mute`).
- `speech_template`: Vorlage für klassische Eins-gegen-Eins-Matches.
- `speech_template_doubles`: Optionale Vorlage für Doppel (2 vs 2). Wird automatisch verwendet, sobald eines der Teams mehr als einen Spieler enthält (Trennung mit `/`, `&`, `+` oder dem Wort „und“).

### Verfügbare Platzhalter für `speech_template`

Alle Platzhalter sind **nicht** case-sensitiv. Zusätzlich werden Varianten mit Sonderzeichen/Leerzeichen automatisch in Großbuchstaben mit Unterstrichen normalisiert. Beispiel: `{player1 surname}` → `{PLAYER1_SURNAME}`.

| Platzhalter                 | Inhalt                                                                              |
| --------------------------- | ----------------------------------------------------------------------------------- |
| `{TABLE}`, `{TABLE_NAME}`   | Anzeigename des Tisches.                                                            |
| `{PLAYER1_*}`               | Bezieht sich auf den ersten Spieler von Team A (voller Name, Vorname, Nachname – siehe Tabelle unten). |
| `{PLAYER2_*}`               | Entspricht `{PLAYER1_*}` für Team B.                                                |
| `{TEAM_A}`, `{TEAM_B}`      | Originaltext der Team-Namen (so wie aus der API geliefert).                        |
| `{TEAM_A_MEMBER_COUNT}` / `{TEAM_B_MEMBER_COUNT}` | Anzahl der erkannten Spieler (max. 2) pro Team.                        |
| `{IS_DOUBLES}`, `{IS_SINGLES}` | Boolescher Status, ob ein Doppel erkannt wurde.                                   |
| `{TEAM_A_PLAYER1_*}`, `{TEAM_A_PLAYER2_*}` | Daten für Spieler 1 bzw. 2 innerhalb von Team A (FULL, FIRST, SURNAME, …). |
| `{TEAM_B_PLAYER1_*}`, `{TEAM_B_PLAYER2_*}` | Entsprechende Daten für Team B.                                           |
| `{NOTIFY_SOUND}`, `{NOTIFY_SOUND_NAME}` | Dateiname des Hinweistons.                                                 |
| `{NOTIFY_SOUND_PATH}`       | Absoluter Pfad zum Hinweiston (leer, wenn keiner konfiguriert ist).                |

**Namens-Platzhalter (`*_FULL`, `*_FIRST`, `*_SURNAME`, …)**  
- `FULL` / `FULLNAME`: Originaltext ohne Änderungen.  
- `FIRST` / `FIRSTNAME` / `NAME`: Erster Name (bei „Nachname, Vorname“-Notation wird automatisch gedreht).  
- `SURNAME` / `LASTNAME`: Letzter Name.

> **Doppel-Erkennung:** Team-Namen werden auftrennt, sobald sie Trennzeichen wie `/`, `&`, `+` oder das Wort „und“ enthalten. Es werden maximal zwei Spieler pro Team ausgewertet; zusätzliche Einträge werden ignoriert.

> **Hinweis:** Fehlende Platzhalter bleiben unverändert (z. B. `{UNKNOWN_TAG}`), sodass Tippfehler sofort auffallen.

## Logging & Verhalten

- Bei neuen Matches wird der frei konfigurierbare Text gesprochen; optional erfolgt vorher ein Hinweiston.
- Das System bereitet jede Ansage in einem Hintergrundthread vor und reiht sie in eine Wiedergabe-Queue. Dadurch können weitere Ansagen schon während der aktuellen Ausgabe synthetisiert werden.
- Der Hinweiston wird nur erneut abgespielt, wenn seit der letzten abgeschlossenen TTS-Ausgabe mindestens `notify_resume_after_seconds` vergangen sind. In der Konsole wird protokolliert, ob der Ton gespielt oder übersprungen wurde.
- Über die Konsole kannst du jederzeit `p`, `mute`, `replay` oder `logs` eingeben. `p` toggelt zwischen Pause/Play, `replay` listet die letzten Durchsagen auf (mit `replay 3` bzw. `replay 2-4` kannst du einzelne oder mehrere alte Meldungen erneut einreihen), `logs` blendet den Log-Bereich ein/aus. Die Queue der nächsten Ansagen wird live eingeblendet; die aktuell gesprochene Zeile ist farblich markiert (falls das Terminal ANSI-Farben unterstützt).
- Die letzten Ansagen werden auf der Festplatte gespeichert, sodass sie nach einem Neustart weiterhin im Replay-Menü und im Dashboard sichtbar sind.
- Sobald `write_announcement_files` aktiv ist, legt das Skript unter `data/<tournament>/announcements` eine Textdatei pro Ansage an.

## Nützliche Kommandos

| Kommando                                | Zweck                                                    |
| --------------------------------------- | -------------------------------------------------------- |
| `python announcement_tts.py`            | Startet die Dauerschleife zur Match-Ansage.              |
| `python text_to_speech.py -t "Text"`    | Liest einen beliebigen Text gemäß der TTS-Config vor.    |
| `python announcement_tts.py --help`     | Listet optionale CLI-Parameter auf.                      |
| `replay`, `replay 3`, `replay 1-4`      | (Im laufenden Programm) letzte Ansagen anzeigen bzw. erneut abspielen. |
| `p`, `mute`, `logs`                     | (Im laufenden Programm) Pause/Play toggeln, Ton stumm schalten, Log-Bereich toggeln. |

## Fehlerbehebung

- Keine Stimme zu hören? Sicherstellen, dass Piper/pyttsx3 korrekt installiert ist und das Piper-Modell existiert.
- Hinweiston bleibt stumm? Pfad prüfen und darauf achten, dass genügend Pause (`notify_resume_after_seconds`) verstrichen ist; siehe Konsole für Erklärungen.
- Zu viele Ansagen? `poll_interval` erhöhen oder das Skript per `CTRL+C` stoppen.
