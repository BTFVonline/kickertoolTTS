# Kickertool TTS

Ein kleines Helferlein, das neue Matches aus der Tournament-API abholt und per Text-to-Speech (Piper oder pyttsx3) ansagt. Optional werden die Texte als Dateien gespeichert und es kann vor jeder Ansage ein Hinweiston abgespielt werden.

## Voraussetzungen

- Python 3.10+
- Abhängigkeiten per `pip install -r requirements.txt` bzw. vorhandenes `.venv` verwenden
- Piper-Modell (z. B. `voices/de_DE-thorsten-medium.onnx`) oder ein funktionierendes pyttsx3-Setup

## Schnellstart

1. `config.yaml.example` nach `config.yaml` kopieren und API-Daten (`api_token`, `tournament_id`) eintragen.
2. Gewünschten TTS-Provider und Optionen konfigurieren (Piper-Modellpfad, pyttsx3-Stimme, etc.).
3. Optional einen Hinweiston (mp3/wav) angeben – relative Pfade beziehen sich auf das Projektverzeichnis.
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

- `notify_sound`: Pfad zu mp3/wav. Wird relativ zu `config.yaml` aufgelöst.
- `notify_resume_after_seconds`: Mindestzeit ohne TTS, bevor der Sound erneut abgespielt wird.
- `speech_template`: Frei formulierbarer Text mit Platzhaltern (Tabelle siehe unten).

### Verfügbare Platzhalter für `speech_template`

Alle Platzhalter sind **nicht** case-sensitiv. Zusätzlich werden Varianten mit Sonderzeichen/Leerzeichen automatisch in Großbuchstaben mit Unterstrichen normalisiert. Beispiel: `{player1 surname}` → `{PLAYER1_SURNAME}`.

| Platzhalter                 | Inhalt                                                                              |
| --------------------------- | ----------------------------------------------------------------------------------- |
| `{TABLE}`, `{TABLE_NAME}`   | Anzeigename des Tisches.                                                            |
| `{PLAYER1_FULL}`            | Originalname Team A (unverändert).                                                  |
| `{PLAYER1_FULLNAME}`        | Alias für `{PLAYER1_FULL}`.                                                         |
| `{PLAYER1_FIRST}`, `{PLAYER1_FIRSTNAME}`, `{PLAYER1_NAME}` | Erster Name bzw. Vorname von Team A (heuristisch aufgeteilt).     |
| `{PLAYER1_SURNAME}`, `{PLAYER1_LASTNAME}` | Nachname von Team A (heuristisch).                                  |
| `{PLAYER2_FULL}`, `{PLAYER2_FULLNAME}`    | Originalname Team B.                                                   |
| `{PLAYER2_FIRST}`, `{PLAYER2_FIRSTNAME}`, `{PLAYER2_NAME}` | Vorname von Team B.                                             |
| `{PLAYER2_SURNAME}`, `{PLAYER2_LASTNAME}` | Nachname von Team B.                                                  |
| `{TEAM_A}`                  | Voller Roh-Name Team A.                                                             |
| `{TEAM_B}`                  | Voller Roh-Name Team B.                                                             |
| `{NOTIFY_SOUND}`            | Dateiname des Hinweistons.                                                          |
| `{NOTIFY_SOUND_NAME}`       | Alias für `{NOTIFY_SOUND}`.                                                         |
| `{NOTIFY_SOUND_PATH}`       | Absoluter Pfad zum Hinweiston (leer, wenn keiner konfiguriert ist).                |

> **Hinweis:** Fehlende Platzhalter bleiben unverändert (z. B. `{UNKNOWN_TAG}`), sodass Tippfehler sofort auffallen.

## Logging & Verhalten

- Bei neuen Matches wird der frei konfigurierbare Text gesprochen; optional erfolgt vorher ein Hinweiston.
- Der Hinweiston wird nur erneut abgespielt, wenn seit der letzten abgeschlossenen TTS-Ausgabe mindestens `notify_resume_after_seconds` vergangen sind. In der Konsole wird protokolliert, ob der Ton gespielt oder übersprungen wurde.
- Sobald `write_announcement_files` aktiv ist, legt das Skript unter `data/<tournament>/announcements` eine Textdatei pro Ansage an.

## Nützliche Kommandos

| Kommando                                | Zweck                                                    |
| --------------------------------------- | -------------------------------------------------------- |
| `python announcement_tts.py`            | Startet die Dauerschleife zur Match-Ansage.              |
| `python text_to_speech.py -t "Text"`    | Liest einen beliebigen Text gemäß der TTS-Config vor.    |
| `python announcement_tts.py --help`     | Listet optionale CLI-Parameter auf.                      |

## Fehlerbehebung

- Keine Stimme zu hören? Sicherstellen, dass Piper/pyttsx3 korrekt installiert ist und das Piper-Modell existiert.
- Hinweiston bleibt stumm? Pfad prüfen und darauf achten, dass genügend Pause (`notify_resume_after_seconds`) verstrichen ist; siehe Konsole für Erklärungen.
- Zu viele Ansagen? `poll_interval` erhöhen oder das Skript per `CTRL+C` stoppen.
