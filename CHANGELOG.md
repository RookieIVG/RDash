# Changelog

Alle wesentlichen Änderungen am InfoDisplay. Format nach [Keep a Changelog](https://keepachangelog.com/de/),
Versionierung nach [Semantic Versioning](https://semver.org/lang/de/).
Neue Einträge werden mit `python tools/bump_version.py` automatisch erzeugt.

## [1.0.0] – 2026-10-25

### Hinzugefügt
- Windows-Sender: aktuelle Wiedergabe (Titel, Interpret, Album, Cover, Position) über die Windows-Medienschnittstelle
- Windows-Sender: nächste Termine aus Outlook (heute + konfigurierbare Folgetage), Datenschutzoptionen für Betreff und private Termine
- Übertragung per Bluetooth RFCOMM mit Token-Anmeldung, automatischem Wiederverbinden und Heartbeat
- Pi-Empfänger: RFCOMM-Server mit Allowlist, Rate-Limiting, Größen- und Inhaltsprüfung
- Pi-Anzeige: Web-Oberfläche im Firmendesign mit Dark/Light-Umschalter, Live-Aktualisierung per Server-Sent Events
- Einheitliche Fehlerseiten (404/500), zentrales Logging, systemd-Dienst und Kiosk-Autostart
- Installationsskripte für Windows (PowerShell) und Raspberry Pi (Bash), Testsender
