# InfoDisplay – Musik & Termine vom Windows-PC auf einem Raspberry-Pi-Bildschirm

**Version:** siehe `VERSION` · **Projektart:** Firmenprojekt KAGes · **Sprachen:** Python 3 (Sender & Empfänger), HTML/CSS/JavaScript (Anzeige)

Ein Windows-11-PC liest die **aktuell laufende Musik** (Titel, Interpret, Album, Cover, Fortschritt) und die
**nächsten Outlook-Termine** aus und schickt sie per **Bluetooth** an einen Raspberry Pi. Der Pi zeigt die Daten
zusammen mit **Uhrzeit und Datum** im Vollbild auf einem HDMI-Monitor an.

```
 Windows 11 PC                                   Raspberry Pi 4/5                     HDMI-Monitor
┌──────────────────────────┐   Bluetooth RFCOMM  ┌──────────────────────────────┐    ┌──────────────┐
│ sender.py                │ ──── JSON-Zeilen ──▶│ receiver.py (systemd-Dienst) │    │ Chromium     │
│  • Windows-Medien-API    │   Token-Anmeldung   │  • RFCOMM-Server, Prüfungen  │───▶│ Kiosk-Modus  │
│  • Outlook (COM)         │                     │  • Webserver 127.0.0.1:8080  │SSE │ index.html   │
└──────────────────────────┘                     └──────────────────────────────┘    └──────────────┘
```

---

## Inhalt

1. [Voraussetzungen](#1-voraussetzungen)
2. [Raspberry Pi vorbereiten](#2-raspberry-pi-vorbereiten)
3. [Empfänger auf dem Pi installieren](#3-empfänger-auf-dem-pi-installieren)
4. [Bluetooth koppeln](#4-bluetooth-koppeln)
5. [Sender auf Windows installieren](#5-sender-auf-windows-installieren)
6. [Inbetriebnahme und Test](#6-inbetriebnahme-und-test)
7. [Logo und Schriftart](#7-logo-und-schriftart)
8. [Konfiguration](#8-konfiguration)
9. [Sicherheitskonzept](#9-sicherheitskonzept)
10. [Fehlersuche](#10-fehlersuche)
11. [Nachrichtenprotokoll](#11-nachrichtenprotokoll)
12. [Versionierung und Changelog](#12-versionierung-und-changelog)
13. [Ordnerstruktur](#13-ordnerstruktur)

---

## 1. Voraussetzungen

| Komponente | Anforderung |
|---|---|
| Raspberry Pi | Pi 4 oder Pi 5 mit eingebautem Bluetooth, Raspberry Pi OS **mit Desktop** (64 Bit, Bookworm oder Trixie) |
| Monitor | HDMI-Monitor (optimiert für 24 Zoll Full HD, funktioniert auch kleiner) |
| Windows-PC | Windows 11 mit Bluetooth, **Python 3.12 oder 3.13 (64 Bit)** von python.org |
| Kalender | **Outlook (Classic)** – das „neue Outlook“ hat keine COM-Schnittstelle, dann `[calendar] enabled = false` |
| Netzwerk | Nur für die Installation (apt/pip). Im Betrieb läuft alles über Bluetooth. |

> **Firmenumgebung:** Auf verwalteten Arbeitsplätzen kann Bluetooth oder das Ausführen von PowerShell-Skripten
> per Gruppenrichtlinie eingeschränkt sein. Vorab prüfen, ob Kopplung und Autostart erlaubt sind. Termine sind auf
> dem Monitor für andere sichtbar – bei Bedarf `hide_subjects = true` setzen (siehe Abschnitt 8).

---

## 2. Raspberry Pi vorbereiten

1. Mit dem **Raspberry Pi Imager** „Raspberry Pi OS (64-bit)“ (mit Desktop) auf die SD-Karte schreiben.
   In den Imager-Einstellungen Benutzer, WLAN/LAN, Zeitzone **Europe/Vienna** und SSH aktivieren.
2. Pi starten, per SSH anmelden und aktualisieren:
   ```bash
   sudo apt update && sudo apt full-upgrade -y
   sudo reboot
   ```
3. Prüfen, ob Bluetooth vorhanden ist:
   ```bash
   bluetoothctl show
   ```
   Die Zeile `Controller XX:XX:XX:XX:XX:XX` zeigt die **Bluetooth-Adresse des Pi** – die brauchst du später.

---

## 3. Empfänger auf dem Pi installieren

1. Ordner `pi-display` und die Datei `VERSION` auf den Pi kopieren (vom Windows-PC aus, im entpackten Projektordner):
   ```powershell
   scp -r .\pi-display .\VERSION benutzer@<pi-ip>:~/infodisplay/
   ```
2. Auf dem Pi installieren – **als normaler Desktop-Benutzer mit sudo** (nicht als root anmelden),
   damit der Kiosk-Autostart für diesen Benutzer eingerichtet wird:
   ```bash
   cd ~/infodisplay/pi-display/install
   chmod +x install.sh
   sudo ./install.sh
   ```
3. Das Skript erledigt:
   - Pakete `python3`, `bluez`, `chromium`, `curl`
   - Dienstbenutzer `infodisplay`, Programm nach `/opt/infodisplay`
   - Konfiguration nach `/etc/infodisplay/config.ini` mit **neu erzeugtem Token** (Rechte 640)
   - systemd-Dienst `infodisplay` (startet automatisch)
   - Kiosk-Autostart (`~/.config/labwc/autostart`), Bildschirm-Abschaltung deaktiviert, Desktop-Autologin
4. Am Ende werden **Bluetooth-Adresse, Kanal und Token** angezeigt – notieren. Später nachsehen mit:
   ```bash
   sudo grep -E '^(channel|token)' /etc/infodisplay/config.ini
   bluetoothctl show | head -1
   ```
5. Kurzer Funktionstest auf dem Pi:
   ```bash
   systemctl status infodisplay
   curl http://127.0.0.1:8080/healthz      # -> {"status":"ok"}
   ```

---

## 4. Bluetooth koppeln

Die Kopplung ist **einmalig** nötig. Pi und PC müssen in Reichweite sein.

**Auf dem Pi** (SSH-Sitzung offen lassen, bis die Kopplung abgeschlossen ist):

```bash
bluetoothctl
```
In der `bluetoothctl`-Konsole nacheinander:
```
power on
agent KeyboardDisplay
default-agent
pairable on
discoverable on
```

**Auf dem Windows-PC:**

1. *Einstellungen → Bluetooth und Geräte → Gerät hinzufügen → Bluetooth*
2. Den Pi auswählen (Name = Hostname des Pi, z. B. `raspberrypi`).
3. Windows zeigt einen **PIN**. Im `bluetoothctl` auf dem Pi erscheint `Confirm passkey 123456 (yes/no)` →
   prüfen, dass die Zahl gleich ist, und **`yes`** eingeben. Auf Windows **„Verbinden“** bestätigen.
4. Ggf. fragt der Pi `Authorize service ...` → **`yes`**.

**Zurück auf dem Pi** – den PC als vertrauenswürdig markieren (Adresse steht in der Ausgabe von `devices`):

```
devices
trust AA:BB:CC:DD:EE:FF        # Adresse des Windows-PCs
discoverable off
quit
```

> Optional: Adresse des PCs in `/etc/infodisplay/config.ini` unter `allowed_macs` eintragen, dann akzeptiert der
> Pi nur noch diesen PC (`sudo systemctl restart infodisplay`).

Windows zeigt den Pi danach als „Gekoppelt“ (nicht „Verbunden“) – das ist korrekt. Die eigentliche Verbindung
baut der Sender selbst auf.

---

## 5. Sender auf Windows installieren

1. **Python 3.13 (64 Bit)** von <https://www.python.org/downloads/windows/> installieren
   (Haken bei „Add python.exe to PATH“ und „py launcher“).
2. Den Projektordner entpacken, z. B. nach `C:\Tools\infodisplay`.
3. PowerShell **als normaler Benutzer** (nicht als Administrator) öffnen:
   ```powershell
   cd C:\Tools\infodisplay\windows-sender
   powershell -ExecutionPolicy Bypass -File .\install.ps1
   ```
   Hinter einem Proxy vorher setzen: `$env:HTTPS_PROXY = "http://proxy:port"`.
4. Das Skript legt an:
   - Programm: `%LOCALAPPDATA%\InfoDisplay\app` (+ `venv`)
   - Konfiguration: `%APPDATA%\InfoDisplay\config.ini` (nur für deinen Benutzer lesbar)
   - Aufgabe **„InfoDisplay Sender“** in der Aufgabenplanung (Start bei Anmeldung, Neustart bei Absturz)
5. Notepad öffnet die Konfiguration. Eintragen:
   ```ini
   [link]
   pi_mac  = B8:27:EB:12:34:56      ; Bluetooth-Adresse des Pi (Schritt 3)
   channel = 22
   token   = <Token vom Pi>
   ```
   Speichern.
6. Erst testen, ob Musik und Kalender gelesen werden (Musik z. B. in Spotify starten):
   ```powershell
   & "$env:LOCALAPPDATA\InfoDisplay\venv\Scripts\python.exe" "$env:LOCALAPPDATA\InfoDisplay\app\sender.py" --test
   ```
   Es erscheinen `MEDIEN`, `COVER` und `KALENDER` als JSON.
7. Sender starten:
   ```powershell
   Start-ScheduledTask -TaskName "InfoDisplay Sender"
   ```

**Update:** neue Version entpacken und `install.ps1` erneut ausführen (Konfiguration bleibt erhalten).
**Deinstallation:** `.\install.ps1 -Uninstall`

---

## 6. Inbetriebnahme und Test

1. Pi neu starten: `sudo reboot` – nach dem Hochfahren öffnet sich die Anzeige im Vollbild.
2. Auf dem PC Musik abspielen. Innerhalb von 1–2 Sekunden erscheinen Titel und Cover,
   oben rechts steht **„Verbunden – <PC-Name>“**.
3. Termine erscheinen spätestens nach 5 Minuten (bzw. sofort nach dem Verbinden).

**Anzeige ohne Windows testen** (z. B. vor der Kopplung): in `/etc/infodisplay/config.ini`
`[debug] tcp_test_port = 5099` setzen, Dienst neu starten und auf dem Pi:
```bash
python3 ~/infodisplay/tools/fake_sender.py --tcp 127.0.0.1:5099 --token <TOKEN> --seconds 120
```
(Ordner `tools` dafür ebenfalls auf den Pi kopieren.) Danach `tcp_test_port = 0` zurücksetzen!

---

## 7. Logo und Schriftart

**Logo:** `web/assets/img/logo.svg` ist ein **Platzhalter**. Das offizielle KAGes-Logo (SVG oder PNG) aus der
Unternehmenskommunikation unter demselben Namen ablegen – oder in der config `[ui] logo = assets/img/kages.png`
setzen. Danach `sudo ./install.sh` erneut ausführen (oder Datei direkt nach `/opt/infodisplay/web/assets/img/` kopieren).

**Schrift Tahoma:** Tahoma ist eine Microsoft-Schrift und auf dem Pi nicht vorhanden (Ersatz: DejaVu Sans).
Mit gültiger Windows-Lizenz die Dateien `tahoma.ttf` und `tahomabd.ttf` aus `C:\Windows\Fonts` auf den Pi kopieren:
```bash
sudo mkdir -p /usr/local/share/fonts/tahoma
sudo cp tahoma.ttf tahomabd.ttf /usr/local/share/fonts/tahoma/
sudo fc-cache -f
```

**Design:** Hauptfarbe RGB 0|126|54, Detailfarbe RGB 22|159|219, Icons: Bootstrap Icons (lokal eingebunden,
keine Internetverbindung nötig). Hell/Dunkel über den Mond/Sonne-Knopf oben rechts oder `[ui] default_theme`.

---

## 8. Konfiguration

### Pi – `/etc/infodisplay/config.ini`

| Abschnitt | Schlüssel | Standard | Bedeutung |
|---|---|---|---|
| bluetooth | `channel` | 22 | RFCOMM-Kanal (1–30), gleich wie am PC |
| bluetooth | `allowed_macs` | leer | Nur diese PCs zulassen (kommagetrennt) |
| bluetooth | `token` | automatisch | Gemeinsamer geheimer Schlüssel |
| security | `msg_rate_per_sec` / `msg_burst` | 10 / 40 | Rate-Limit Bluetooth-Nachrichten |
| security | `idle_timeout` | 120 | Trennen nach x s ohne Lebenszeichen |
| security | `http_rate_per_sec` | 20 | Rate-Limit Webserver |
| web | `host` / `port` | 127.0.0.1 / 8080 | Webserver nur lokal |
| ui | `title` | Info-Display | Überschrift im Header |
| ui | `default_theme` | auto | `auto`, `light` oder `dark` |
| ui | `show_seconds` | true | Sekunden in der Uhr |
| debug | `tcp_test_port` | 0 | TCP-Testzugang (nur zum Testen) |
| logging | `file` / `level` | /var/log/infodisplay/… / INFO | Zentrales Log |

Nach Änderungen: `sudo systemctl restart infodisplay`

### Windows – `%APPDATA%\InfoDisplay\config.ini`

| Abschnitt | Schlüssel | Standard | Bedeutung |
|---|---|---|---|
| link | `pi_mac` | – | Bluetooth-Adresse des Pi |
| link | `channel` / `token` | 22 / – | wie am Pi |
| media | `poll_interval` | 1.0 | Abfrage in Sekunden |
| media | `preferred_apps` | leer | z. B. `spotify` – nur diese App anzeigen |
| media | `send_cover` / `cover_max_px` | true / 400 | Cover übertragen und verkleinern |
| calendar | `enabled` | true | Outlook-Termine lesen |
| calendar | `start_outlook` | false | Outlook bei Bedarf selbst starten |
| calendar | `days_ahead` / `max_events` | 1 / 10 | Zeitraum und Anzahl |
| calendar | `hide_subjects` | false | **Datenschutz:** nur „Termin“ statt Betreff/Ort |
| calendar | `hide_private` | true | Private Termine als „Privater Termin“ |
| calendar | `restrict_date_format` | `%d.%m.%Y %H:%M` | Datumsformat für Outlook-Filter (Systemsprache) |
| logging | `file` / `level` | `%LOCALAPPDATA%\InfoDisplay\logs\sender.log` / INFO | Zentrales Log |

Nach Änderungen: Aufgabe neu starten
(`Stop-ScheduledTask "InfoDisplay Sender"; Start-ScheduledTask "InfoDisplay Sender"`).

---

## 9. Sicherheitskonzept

| Maßnahme | Umsetzung |
|---|---|
| Kopplung | Bluetooth-Kopplung mit Zahlenvergleich, PC als „trusted“ |
| Anmeldung | Gemeinsamer Token (32 Byte zufällig), Vergleich zeitkonstant (`hmac.compare_digest`) |
| Geräte-Allowlist | Optional `allowed_macs` |
| Rate-Limiting | Verbindungsversuche pro Gerät, Nachrichten pro Verbindung, HTTP-Anfragen pro IP, max. SSE-Clients |
| Eingabeprüfung | Max. Nachrichtengröße, Typ-/Längenprüfung, Steuerzeichen entfernt, Cover nur JPEG/PNG (Magic Bytes) |
| Ausgabe | Anzeige setzt Texte nur per `textContent` (kein HTML), strikte Content-Security-Policy |
| Webserver | Nur `127.0.0.1`, nur lesende GET-Endpunkte, Pfadprüfung gegen Directory Traversal, Security-Header |
| Konfiguration | Zugangsdaten außerhalb des Web-Roots: `/etc/infodisplay` (640) bzw. `%APPDATA%` (nur Benutzer) |
| Dienst | Eigener Systembenutzer ohne Login, systemd-Härtung (`ProtectSystem=strict`, `NoNewPrivileges`, …) |
| Logging | Zentrales, rotierendes Log; abgelehnte Anmeldungen und Verstöße werden protokolliert |

*Nicht zutreffend:* Prepared Statements/PDO (keine Datenbank), Sessions und CSRF-Tokens (keine Anmeldung im
Browser, keine schreibenden Endpunkte). Die Bluetooth-Verbindung ist durch die Kopplung verschlüsselt.

---

## 10. Fehlersuche

| Problem | Lösung |
|---|---|
| Sender-Log: `TimeoutError` / `Verbindung abgelehnt` | Pi an? `systemctl status infodisplay`. Kanal gleich? Kopplung vorhanden (Windows-Einstellungen)? |
| `Anmeldung abgelehnt: auth` | Token am PC stimmt nicht mit `/etc/infodisplay/config.ini` überein |
| Pi-Log: `bluetooth-Server konnte nicht starten: Address already in use` | Anderen Kanal wählen (z. B. 23) – an beiden Seiten |
| Status „Keine Verbindung“, PC zeigt „Gekoppelt“ | Normal bis der Sender läuft. Aufgabe „InfoDisplay Sender“ in der Aufgabenplanung prüfen |
| Musik wird nicht erkannt | Nicht jede App meldet sich bei Windows. Test mit `--test`; ggf. `preferred_apps` leeren |
| Kein Cover | Manche Apps (z. B. Browser) liefern kein Cover → Platzhalter wird angezeigt |
| Keine Termine | Läuft Outlook (Classic)? `start_outlook = true` setzen. Log auf „Datumsformat“ prüfen |
| Kopplung schlägt fehl | Auf dem Pi `bluetoothctl` → `remove <PC-MAC>`, in Windows Gerät entfernen, Schritt 4 wiederholen |
| Schwarzer Bildschirm | `curl 127.0.0.1:8080/healthz`; Autostart: `cat ~/.config/labwc/autostart` |

**Logs:**
- Pi: `sudo journalctl -u infodisplay -f` oder `/var/log/infodisplay/infodisplay.log`
- Windows: `%LOCALAPPDATA%\InfoDisplay\logs\sender.log` (für Details `level = DEBUG`)

---

## 11. Nachrichtenprotokoll

Eine JSON-Nachricht pro Zeile (UTF-8, abgeschlossen mit `\n`), Protokollversion `v = 1`.

| Richtung | Typ | Inhalt |
|---|---|---|
| PC → Pi | `hello` | `v`, `token`, `client`, `app_version` – muss die erste Nachricht sein |
| Pi → PC | `welcome` / `error` | `server_version` bzw. `reason` (`auth`, `protocol_version`) |
| PC → Pi | `media` | `active`, `status` (playing/paused/stopped), `title`, `artist`, `album`, `source_app`, `position_ms`, `duration_ms`, `cover_id` |
| PC → Pi | `cover` | `id` (Hash), `mime`, `b64` – nur bei Titelwechsel |
| PC → Pi | `calendar` | `events[]` mit `subject`, `location`, `start`, `end` (lokal, `YYYY-MM-DDTHH:MM`), `all_day` |
| PC → Pi | `ping` | Lebenszeichen alle 20 s |
| PC → Pi | `bye` | Sender beendet sich |

Weitere Datenquellen (z. B. Systemwerte, Benachrichtigungen) lassen sich als neuer Nachrichtentyp ergänzen:
Sender-Modul in `windows-sender/includes`, Prüfung in `pi-display/includes/protocol.py`, Anzeige in `app.js`.

---

## 12. Versionierung und Changelog

Versionen nach **Semantic Versioning** (`MAJOR.MINOR.PATCH`) in der Datei `VERSION`.
Version und Changelog werden gemeinsam erhöht:

```bash
python tools/bump_version.py patch "Cover wird bei Titelwechsel zuverlässiger geladen"
python tools/bump_version.py minor "Anzeige der CPU-Auslastung"
python tools/bump_version.py major "Protokoll v2"
```

Die Versionsnummer erscheint in der Fußzeile der Anzeige und in beiden Logs.

---

## 13. Ordnerstruktur

```
infodisplay/
├── VERSION                     Versionsnummer (SemVer)
├── CHANGELOG.md                Änderungsprotokoll
├── README.md                   diese Anleitung
├── tools/
│   ├── bump_version.py         Version + Changelog automatisch fortschreiben
│   └── fake_sender.py          Testsender mit Beispieldaten
├── windows-sender/
│   ├── sender.py               Hauptprogramm
│   ├── install.ps1             Installation/Deinstallation, Autostart
│   ├── requirements.txt
│   ├── config/config.example.ini
│   └── includes/               config, logger, protocol, link_client, media, calendar_outlook
└── pi-display/
    ├── receiver.py             Hauptprogramm (Dienst)
    ├── config/config.example.ini
    ├── includes/               config, logger, protocol, state, link_server, web_server, ratelimit
    ├── install/                install.sh, infodisplay.service, kiosk.sh
    └── web/                    Web-Root: index.html, 404.html, 500.html
        └── assets/             css/, js/, img/, vendor/bootstrap-icons/
```
