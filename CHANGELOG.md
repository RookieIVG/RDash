# Changelog

Alle wesentlichen Änderungen am InfoDisplay. Format nach [Keep a Changelog](https://keepachangelog.com/de/),
Versionierung nach [Semantic Versioning](https://semver.org/lang/de/).
Neue Einträge werden mit `python tools/bump_version.py` automatisch erzeugt.

## [1.2.2] – 2026-10-25

### Behoben
- Pi-Anzeige: Übersetzungs-Popup von Chromium abgeschaltet (translate=no, Chromium-Richtlinie TranslateEnabled=false, --lang=de-AT)

## [1.2.1] – 2026-10-25

### Behoben
- README: Projektordner am Pi einheitlich ~/infodisplay (auch bei git clone), Wechsel von scp auf git beschrieben

## [1.2.0] – 2026-10-25

### Geändert
- Pi-Anzeige: schlichtes Design – schwarzer Hintergrund, nur Uhr/Datum, Termine und Musik; Logo, Kopf-/Fußzeile und Hell/Dunkel-Umschalter entfernt (Config-Schlüssel title, default_theme, logo entfallen)
- Pi-Dienst gibt Bluetooth bei jedem Start per rfkill frei und schaltet es ein
- Windows-Installation beendet vor einem Update den laufenden Sender
- README: SSH von Windows 11, Bluetooth-Sperre (rfkill), Update auf neue Version, PC-Wechsel, Installation direkt von GitHub

## [1.1.0] – 2026-10-25

### Hinzugefügt
- Pi-Anzeige: Hochformat-Layout für 1080×1920 (Uhr/Datum oben, Termine, Musik unten), wählbar über [ui] layout
- Pi-Anzeige: Ruhemodus im Hochformat – ohne Verbindung nur Uhr und Datum zentriert
- Pi: Bildschirmdrehung über [ui] rotation (wlr-randr beim Kiosk-Start)

## [1.0.0] – 2026-10-25

### Hinzugefügt
- Windows-Sender: aktuelle Wiedergabe (Titel, Interpret, Album, Cover, Position) über die Windows-Medienschnittstelle
- Windows-Sender: nächste Termine aus Outlook (heute + konfigurierbare Folgetage), Datenschutzoptionen für Betreff und private Termine
- Übertragung per Bluetooth RFCOMM mit Token-Anmeldung, automatischem Wiederverbinden und Heartbeat
- Pi-Empfänger: RFCOMM-Server mit Allowlist, Rate-Limiting, Größen- und Inhaltsprüfung
- Pi-Anzeige: Web-Oberfläche im Firmendesign mit Dark/Light-Umschalter, Live-Aktualisierung per Server-Sent Events
- Einheitliche Fehlerseiten (404/500), zentrales Logging, systemd-Dienst und Kiosk-Autostart
- Installationsskripte für Windows (PowerShell) und Raspberry Pi (Bash), Testsender
