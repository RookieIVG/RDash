# Changelog

Alle wesentlichen Änderungen am InfoDisplay. Format nach [Keep a Changelog](https://keepachangelog.com/de/),
Versionierung nach [Semantic Versioning](https://semver.org/lang/de/).
Neue Einträge werden mit `python tools/bump_version.py` automatisch erzeugt.

## [1.10.0] – 2026-10-28

### Geändert
- Liedwechsel schneller: Titel/Interpret werden vor dem Cover gesendet, Cover auf höchstens 40 KB verkleinert ([media] cover_max_kb)
- Cover wird in Stücken übertragen (neue Nachricht cover_chunk): ein neuer Titel muss nicht auf ein großes Cover warten, überholte Cover werden abgebrochen. Der Pi nimmt weiterhin auch ganze Cover an
- Verbindung bricht bei großen Nachrichten nicht mehr ab: Sendelimit richtet sich nach der Größe (Bluetooth mit ab 1 KB/s)
- Pi: Hintergrund-Überblendung über die Grafikeinheit (ruckelt nicht mehr beim Liedwechsel), effizienteres Einlesen großer Nachrichten
- README: Abschnitt „Bluetooth-Verbindung verbessern“ (WLAN/Bluetooth-Störungen, Energiesparen, Messen)

## [1.9.1] – 2026-10-28

### Geändert
- README: neuer Abschnitt 11 „Bedienung am Pi“ – Anzeige manuell starten, Uhrzeit von Hand stellen, Config ändern ohne SSH (Tastatur am Pi, LAN-Kabel direkt)

## [1.9.0] – 2026-10-28

### Hinzugefügt
- Pi übernimmt die Uhrzeit vom verbundenen PC (beim Verbinden und bei Abweichung > 2 s) – richtige Uhrzeit auch ohne Internet ([time] sync_from_pc, Dienst mit CAP_SYS_TIME)

## [1.8.0] – 2026-10-27

### Hinzugefügt
- Hintergrund passend zum Cover: dunkler Farbverlauf aus den Farben des Covers, weich übergeblendet; ohne Cover, Wiedergabe oder Verbindung schwarz ([ui] cover_background)
- Testsender: --cover rot|lila|grau|keins

## [1.7.0] – 2026-10-27

### Geändert
- Bildschirmschoner zeigt jetzt Uhr und Datum (wandern gemeinsam über den Bildschirm)

## [1.6.0] – 2026-10-27

### Geändert
- Ohne Verbindung zum PC: nur die Uhr als Bildschirmschoner, wandert über den Bildschirm und prallt an den Rändern ab – in allen Formaten ([ui] saver_speed)
- Hochformat in Dritteln: oben Uhr, Datum und Wetter, Mitte Schlagzeilen (sonst Termine) mit nächstem Termin als Leiste, unten Musik
- Wetter mit animierten Icons (Meteocons von Bas Milius, MIT-Lizenz, lokal eingebunden)

## [1.5.1] – 2026-10-25

### Behoben
- Config-Dateien mit BOM (z. B. per PowerShell 5 oder Editor „UTF-8 mit BOM“ gespeichert) werden jetzt gelesen

### Hinzugefügt
- ANLEITUNG-FIRMEN-PC.md: Umzug auf einen anderen PC (Firmen-PC) – IT-Voraussetzungen, Installation, Config übertragen, Bluetooth-Kopplung, alten PC abmelden, Test, Fehlersuche

## [1.5.0] – 2026-10-25

### Hinzugefügt
- Einstellung [ui] focus am Pi: Termine oder Schlagzeilen groß; das jeweils andere als Leiste unten (nächster Termin bzw. wechselnde Schlagzeile). Fehlt Inhalt, übernimmt automatisch der andere Bereich
- Schlagzeilen größer; Großansicht mit Quelle und Kurztext, blättert seitenweise ([ui] news_page_seconds)
- Sender: Kurztext aus RSS (description) und Atom (summary/content), HTML wird entfernt ([news] with_text)

## [1.4.0] – 2026-10-25

### Hinzugefügt
- Wetter (Open-Meteo) unter dem Datum – der Windows-PC ruft es ab und sendet es per Bluetooth ([weather] in der Sender-Config)
- Schlagzeilen aus RSS-/Atom-Feeds am unteren Bildschirmrand, wechselnd ([news] in der Sender-Config, [ui] news_seconds am Pi)
- Protokoll: neue Nachrichtentypen weather und news (Protokollversion bleibt 1); Testsender mit --no-web

## [1.3.0] – 2026-10-25

### Geändert
- Pi-Anzeige: ohne Termine bzw. ohne Kalender wird der Terminbereich ausgeblendet – keine Meldung mehr
- Kiosk: Mauszeiger wird per CSS ausgeblendet und beim Start mit wlrctl in die Ecke geschoben
- Testsender: Option --no-calendar

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
