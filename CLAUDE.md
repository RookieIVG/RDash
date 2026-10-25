# InfoDisplay – Projektregeln für Claude Code

Firmenprojekt KAGes. Windows-11-PC sendet Musik- und Outlook-Kalenderinfos per Bluetooth (RFCOMM)
an einen Raspberry Pi 4/5, der sie im Chromium-Kiosk auf einem HDMI-Monitor anzeigt.
Vollständige Anleitung: `README.md`.

## Sprachen & Aufbau
- `windows-sender/` – Python 3.12+ (winrt 3.2.1, pywin32, Pillow), Einstieg `sender.py`
- `pi-display/` – Python 3 nur Standardbibliothek, Einstieg `receiver.py`; Web-Root `pi-display/web/` (HTML/CSS/JS, kein Build)
- `tools/` – `bump_version.py` (Version + Changelog), `fake_sender.py` (Testdaten)
- Protokoll: eine JSON-Nachricht pro Zeile, `v = 1`. Änderungen immer an **beiden** Seiten
  (`windows-sender/includes/protocol.py` und `pi-display/includes/protocol.py`) und im README-Abschnitt 11.

## Verbindliche Vorgaben
- UI-Sprache Deutsch; Code-Kommentare Deutsch; README Deutsch
- Design: Hauptfarbe RGB 0|126|54, Detailfarbe RGB 22|159|219, Schrift Tahoma (Regular/Bold)
- KAGes-Logo immer im Header sichtbar (`web/assets/img/logo.svg`, aktuell Platzhalter)
- Dark- und Light-Mode inkl. Umschalter; einheitliches Design für Header, Footer, Buttons
- Responsive: 24-Zoll-Monitor (1920×1080) und Mobilgeräte
- Icons: Bootstrap Icons (lokal unter `web/assets/vendor/bootstrap-icons/`, keine CDNs – CSP erlaubt nur `'self'`)
- Einheitliche Fehlerseiten 404/500 im Projektdesign
- Zentrales Logging über `includes/logger.py` (`get_logger("<modul>")`), nie `print` im Betrieb
- Zugangsdaten/Token nur in Config-Dateien außerhalb des Web-Roots (`/etc/infodisplay`, `%APPDATA%\InfoDisplay`), nie im Code
- Security: Token-Anmeldung, Rate-Limiting, strikte Eingabeprüfung; Texte im Browser nur per `textContent`
- Bestätigungsdialoge bei kritischen Aktionen einheitlich gestalten
- Datenbanken (falls je nötig): PDO/Prepared Statements, Migration UND Komplett-Installationsskript
- Versionierung SemVer in `VERSION`; jede Änderung mit `python tools/bump_version.py <major|minor|patch> "…"`
  (schreibt automatisch `CHANGELOG.md`)

## Testen ohne Hardware
```bash
# Pi-Empfänger lokal: Kopie von pi-display/config/config.example.ini mit
#   token = <mind. 16 Zeichen>, [bluetooth] enabled = false, [debug] tcp_test_port = 5099,
#   web_root = <absoluter Pfad zu pi-display/web>, [logging] file = <lokaler Pfad>
python pi-display/receiver.py --config <test.ini>
python tools/fake_sender.py --tcp 127.0.0.1:5099 --token <token> --seconds 120
# Anzeige: http://127.0.0.1:8080/
# Windows-Sender ohne Pi: python windows-sender/sender.py --test
```
