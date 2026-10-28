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
7. [Anzeige: Design und Hochformat](#7-anzeige-design-und-hochformat)
8. [Konfiguration](#8-konfiguration)
9. [Update auf eine neue Version](#9-update-auf-eine-neue-version)
10. [PC wechseln (neuen Sender einrichten)](#10-pc-wechseln-neuen-sender-einrichten)
11. [Bedienung am Pi (Anzeige starten, Uhrzeit, ohne SSH)](#11-bedienung-am-pi-anzeige-starten-uhrzeit-ohne-ssh)
12. [Sicherheitskonzept](#12-sicherheitskonzept)
13. [Fehlersuche](#13-fehlersuche)
14. [Nachrichtenprotokoll](#14-nachrichtenprotokoll)
15. [Versionierung und Changelog](#15-versionierung-und-changelog)
16. [Ordnerstruktur](#16-ordnerstruktur)

**Umzug auf einen anderen PC (z. B. Firmen-PC):** eigene Schritt-für-Schritt-Anleitung in
[`ANLEITUNG-FIRMEN-PC.md`](ANLEITUNG-FIRMEN-PC.md) – inkl. Übertragung der Config und Bluetooth-Kopplung.

**Download:** <https://github.com/RookieIVG/RDash> – aktueller Stand als ZIP:
<https://github.com/RookieIVG/RDash/archive/refs/heads/main.zip> (entpackt heißt der Ordner `RDash-main`).

---

## 1. Voraussetzungen

| Komponente | Anforderung |
|---|---|
| Raspberry Pi | Pi 4 oder Pi 5 mit eingebautem Bluetooth, Raspberry Pi OS **mit Desktop** (64 Bit, Bookworm oder Trixie) |
| Monitor | HDMI-Monitor (optimiert für 24 Zoll Full HD, funktioniert auch kleiner) |
| Windows-PC | Windows 11 mit Bluetooth, **Python 3.12 oder 3.13 (64 Bit)** von python.org |
| Kalender | **Outlook (Classic)** – das „neue Outlook“ hat keine COM-Schnittstelle, dann `[calendar] enabled = false` |
| Netzwerk | Pi: nur für die Installation/Updates (apt, git). Im Betrieb läuft alles über Bluetooth – der Pi braucht **kein** Internet. Wetter und Schlagzeilen (optional) holt der PC und schickt sie per Bluetooth weiter. |

> **Firmenumgebung:** Auf verwalteten Arbeitsplätzen kann Bluetooth oder das Ausführen von PowerShell-Skripten
> per Gruppenrichtlinie eingeschränkt sein. Vorab prüfen, ob Kopplung und Autostart erlaubt sind. Termine sind auf
> dem Monitor für andere sichtbar – bei Bedarf `hide_subjects = true` setzen (siehe Abschnitt 8).

---

## 2. Raspberry Pi vorbereiten

1. Mit dem **Raspberry Pi Imager** „Raspberry Pi OS (64-bit)“ (mit Desktop) auf die SD-Karte schreiben.
   In den Imager-Einstellungen Benutzer, WLAN/LAN, Zeitzone **Europe/Vienna** und SSH aktivieren.
2. Pi starten, per SSH anmelden (siehe 2.1) und aktualisieren:
   ```bash
   sudo apt update && sudo apt full-upgrade -y
   sudo reboot
   ```
3. Prüfen, ob Bluetooth vorhanden ist:
   ```bash
   bluetoothctl show
   ```
   Die Zeile `Controller XX:XX:XX:XX:XX:XX` zeigt die **Bluetooth-Adresse des Pi** – die brauchst du später.
   Steht bei `Powered: no` und `bluetoothctl power on` meldet `Failed to set power on: org.bluez.Error.Failed`,
   ist Bluetooth gesperrt → siehe 2.2.

### 2.1 Per SSH von Windows 11 verbinden

Windows 11 hat SSH eingebaut – einfach **PowerShell** oder **Terminal** öffnen.

**SSH am Pi einschalten** (falls nicht schon im Imager unter *Dienste → SSH aktivieren* gesetzt):
am Pi selbst (Tastatur/Monitor) ein Terminal öffnen und
```bash
sudo systemctl enable --now ssh
```
(oder `sudo raspi-config` → *Interface Options* → *SSH* → *Yes*).

**Adresse des Pi:** meist `raspberrypi.local` (bzw. der im Imager vergebene Hostname). Sonst am Pi
`hostname -I` eingeben oder in der Geräteliste des Routers nachsehen (z. B. `192.168.1.50`).

**Verbinden:**
```powershell
ssh benutzer@raspberrypi.local
# oder mit IP:
ssh benutzer@192.168.1.50
```
Beim ersten Mal die Frage `Are you sure you want to continue connecting` mit `yes` bestätigen, dann das Passwort
eingeben (beim Tippen erscheinen keine Zeichen – das ist normal). Beenden mit `exit`.

**Dateien kopieren** (vom PC zum Pi):
```powershell
scp -r .\ordner benutzer@raspberrypi.local:~/ziel/
```

**Optional – Anmeldung ohne Passwort (SSH-Schlüssel)**, einmalig in PowerShell:
```powershell
ssh-keygen -t ed25519            # Enter drücken, optional eine Passphrase vergeben
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh benutzer@raspberrypi.local "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
```
Kurzname: in `%USERPROFILE%\.ssh\config` eintragen
```
Host pi
    HostName raspberrypi.local
    User benutzer
```
→ danach genügt `ssh pi` bzw. `scp datei pi:~/`.

| SSH-Meldung | Lösung |
|---|---|
| `Could not resolve hostname raspberrypi.local` | IP-Adresse statt `.local` verwenden (in Firmennetzen klappt `.local` oft nicht) |
| `Connection refused` | SSH am Pi nicht aktiv → siehe oben |
| `Connection timed out` | Pi und PC nicht im selben Netz oder Firewall sperrt Port 22 (ggf. IT fragen) |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | Pi wurde neu aufgesetzt: `ssh-keygen -R raspberrypi.local` (bzw. IP), dann neu verbinden |
| `Permission denied` | Benutzername/Passwort falsch – es gilt der im Imager angelegte Benutzer |

### 2.2 Bluetooth gesperrt („Failed to set power on“)

```bash
rfkill list
```
Steht bei `hci0: Bluetooth` die Zeile **`Soft blocked: yes`**, ist Bluetooth per Software gesperrt. Freigeben:
```bash
sudo rfkill unblock bluetooth
bluetoothctl power on            # -> Changing power on succeeded
sudo systemctl restart infodisplay   # nur falls schon installiert
```
Der InfoDisplay-Dienst gibt Bluetooth ab Version 1.2.0 bei jedem Start selbst frei. Wird es trotzdem wieder
gesperrt, am Pi-Desktop über das Bluetooth-Symbol oben rechts „Bluetooth einschalten“ wählen.

Hilft das nicht:
```bash
sudo systemctl restart bluetooth
bluetoothctl list                         # leer = kein Adapter erkannt
grep -n -i "bt" /boot/firmware/config.txt # steht dort dtoverlay=disable-bt -> Zeile mit # auskommentieren, Neustart
sudo btmgmt power on                      # genauere Fehlermeldung
```

---

## 3. Empfänger auf dem Pi installieren

1. Projekt auf den Pi holen – **Variante A (empfohlen): direkt am Pi von GitHub**:
   ```bash
   sudo apt install -y git
   git clone https://github.com/RookieIVG/RDash.git ~/infodisplay
   ```
   **Variante B: vom Windows-PC kopieren** (im entpackten Projektordner, siehe 2.1):
   ```powershell
   scp -r .\pi-display .\VERSION .\tools benutzer@raspberrypi.local:~/infodisplay/
   ```
2. Auf dem Pi installieren – **als normaler Desktop-Benutzer mit sudo** (nicht als root anmelden),
   damit der Kiosk-Autostart für diesen Benutzer eingerichtet wird:
   ```bash
   cd ~/infodisplay/pi-display/install
   chmod +x install.sh
   sudo ./install.sh
   ```
3. Das Skript erledigt:
   - Pakete `python3`, `bluez`, `chromium`, `curl`, `wlr-randr`, `wlrctl`
   - Dienstbenutzer `infodisplay`, Programm nach `/opt/infodisplay`
   - Konfiguration nach `/etc/infodisplay/config.ini` mit **neu erzeugtem Token** (Rechte 640)
   - systemd-Dienst `infodisplay` (startet automatisch)
   - Kiosk-Autostart (`~/.config/labwc/autostart`), Bildschirm-Abschaltung deaktiviert, Desktop-Autologin
   - Chromium-Richtlinie `/etc/chromium/policies/managed/infodisplay.json` (kein Übersetzungs-Popup)
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
   pi_mac  = B8:27:EB:12:34:56      ; Bluetooth-Adresse des Pi (Abschnitt 3)
   channel = 22
   token   = <Token vom Pi>
   ```
   Speichern.
6. Erst testen, ob Musik und Kalender gelesen werden (Musik z. B. in Spotify starten):
   ```powershell
   & "$env:LOCALAPPDATA\InfoDisplay\venv\Scripts\python.exe" "$env:LOCALAPPDATA\InfoDisplay\app\sender.py" --test
   ```
   Es erscheinen `MEDIEN`, `COVER` und `KALENDER` (sowie `WETTER` und `SCHLAGZEILEN`, falls eingeschaltet) als JSON.
7. Sender starten:
   ```powershell
   Start-ScheduledTask -TaskName "InfoDisplay Sender"
   ```

**Update:** siehe Abschnitt 9. **PC wechseln:** siehe Abschnitt 10.
**Deinstallation:** `.\install.ps1 -Uninstall`

---

## 6. Inbetriebnahme und Test

1. Pi neu starten: `sudo reboot` – nach dem Hochfahren öffnet sich die Anzeige im Vollbild.
2. Auf dem PC Musik abspielen. Innerhalb von 1–2 Sekunden erscheinen Titel und Cover.
   Ohne Verbindung zeigt die Anzeige nur Uhr und Datum, die als Bildschirmschoner langsam über den Bildschirm wandern.
3. Termine erscheinen spätestens nach 5 Minuten (bzw. sofort nach dem Verbinden).

**Anzeige ohne Windows testen** (z. B. vor der Kopplung): in `/etc/infodisplay/config.ini`
`[debug] tcp_test_port = 5099` setzen, Dienst neu starten und auf dem Pi:
```bash
python3 ~/infodisplay/tools/fake_sender.py --tcp 127.0.0.1:5099 --token <TOKEN> --seconds 120
```
Mit `--no-calendar` sendet der Testsender keine Termine (wie ein PC ohne Outlook), mit `--no-web` kein Wetter und keine Schlagzeilen.
Mit `--cover rot|lila|grau|keins` wählt er ein anderes Testcover (Standard: `gruen`).
(Bei Variante B den Ordner `tools` mitkopieren.) Danach `tcp_test_port = 0` zurücksetzen!

---

## 7. Anzeige: Design und Hochformat

**Design:** bewusst schlicht – schwarzer Hintergrund, weiße Schrift, keine Kopf- oder Fußzeile, kein Logo.
Läuft Musik mit Cover, wird der Hintergrund zu einem dunklen Farbverlauf in den Farben des Covers (weich übergeblendet,
ausschaltbar mit `[ui] cover_background = false`). Ohne Cover, ohne Wiedergabe und ohne Verbindung bleibt er schwarz.
Angezeigt werden Uhrzeit/Datum, Wetter, Termine, Schlagzeilen und die aktuelle Musik. Icons: Bootstrap Icons,
Wetter: animierte [Meteocons](https://github.com/basmilius/weather-icons) von Bas Milius (MIT-Lizenz) – beides
lokal eingebunden, keine Internetverbindung nötig. Schrift: Systemschrift des Pi (DejaVu Sans).

| Format | Anordnung |
|---|---|
| Querformat (1920×1080) | Musik links, Uhr/Datum/Wetter und Termine bzw. Schlagzeilen rechts (`[ui] focus`), Leiste unten |
| Hochformat (1080×1920) | drei gleich hohe Bereiche: **oben** Uhr, Datum, Wetter · **Mitte** Schlagzeilen (gibt es keine: Termine), darunter der nächste Termin als Leiste · **unten** Musik |
| Keine Verbindung zum PC | **Bildschirmschoner:** nur Uhr und Datum, sie wandern langsam schräg über den Bildschirm und prallt an den Rändern ab (Tempo: `[ui] saver_speed`) – in beiden Formaten |
| Keine Termine / kein Kalender | Der Terminbereich wird ganz ausgeblendet (keine Meldung) |
| Hintergrund | Musik mit Cover: dunkler Farbverlauf passend zum Cover · sonst schwarz |

### Wetter und Schlagzeilen

Der Pi hat im Betrieb kein Internet – deshalb ruft der **Windows-PC** Wetter und Schlagzeilen ab und schickt sie
per Bluetooth an den Pi. Beides ist standardmäßig aus und wird in `%APPDATA%\InfoDisplay\config.ini` am PC
eingeschaltet:

```ini
[weather]
enabled   = true
place     = Graz            ; angezeigter Name
latitude  = 47.07           ; Koordinaten (Google Maps: Rechtsklick auf den Ort -> Zahlen anklicken)
longitude = 15.44

[news]
enabled = true
; RSS-/Atom-Feeds, kommagetrennt (nur die Überschriften werden angezeigt)
feeds = https://rss.orf.at/news.xml, https://rss.orf.at/steiermark.xml
max_headlines = 10

[internet]
proxy =                     ; leer = Proxy aus den Windows-Einstellungen
```
Danach den Sender neu starten (`Stop-ScheduledTask "InfoDisplay Sender"; Start-ScheduledTask "InfoDisplay Sender"`).
Prüfen, ob der PC die Daten bekommt: `sender.py --test` (Abschnitt 5, Schritt 6) zeigt `WETTER` und `SCHLAGZEILEN`.

| Anzeige | Wo |
|---|---|
| Wetter | unter dem Datum: Symbol, Temperatur, Beschreibung, Tiefst-/Höchstwert, Ort (Daten: [Open-Meteo](https://open-meteo.com), kostenlos, ohne Anmeldung) |
| Schlagzeilen | je nach `[ui] focus` am Pi: als Leiste unten (eine nach der anderen) oder groß als Liste mit Kurztext – siehe unten |

Wetter und Schlagzeilen werden alle 15 Minuten aktualisiert und nur angezeigt, solange der PC verbunden ist
(und die Daten nicht älter als 3 Stunden sind). Ohne Verbindung zeigt der Bildschirmschoner nur Uhr und Datum.

#### Kalender oder Schlagzeilen groß? (`[ui] focus` am Pi, nur Querformat)

Im Hochformat ist die Aufteilung fest (Mitte = Schlagzeilen, sonst Termine); `focus` gilt nur im Querformat.

| `focus` | Großer Bereich | Leiste unten |
|---|---|---|
| `calendar` (Standard) | Termine | Schlagzeilen, eine nach der anderen (Wechsel alle `news_seconds` s) |
| `news` | Schlagzeilen mit Quelle und Kurztext, so viele wie Platz haben – blättert alle `news_page_seconds` s weiter | laufender bzw. nächster Termin („Jetzt bis 11:45 · Jour fixe“, „+2 weitere“) |

Fehlt der Inhalt für den großen Bereich, übernimmt automatisch der andere (z. B. `focus = calendar`, aber heute
keine Termine → Schlagzeilen groß). Einstellen in `/etc/infodisplay/config.ini`:
```ini
[ui]
focus = news
news_page_seconds = 30
```
danach `sudo systemctl restart infodisplay`.

Den Kurztext liefert der Feed (RSS: `description`, Atom: `summary`/`content`). Abschalten am PC mit
`[news] with_text = false`.

**Unterstützte Feed-Formate:** RSS 2.0, RSS 1.0 (RDF) und Atom.

**Feed-Adressen finden:** Viele Nachrichtenseiten nennen ihren RSS-Feed im Seitenfuß („RSS“). Beispiele:
`https://rss.orf.at/news.xml` (ORF News), `https://rss.orf.at/steiermark.xml` (ORF Steiermark),
`https://www.derstandard.at/rss` (Der Standard). Nur `http`/`https` ist erlaubt.

### Hochformat einrichten

Einrichten in `/etc/infodisplay/config.ini`:
```ini
[ui]
layout   = auto     ; erkennt das Hochformat selbst, "portrait" erzwingt es
rotation = 90       ; steht das Bild auf dem Kopf: 270
```
Danach `sudo systemctl restart infodisplay` und `sudo reboot`. Die Drehung setzt `kiosk.sh` beim Start der
Anzeige mit `wlr-randr` (wird von `install.sh` installiert). Gibt es mehrere Bildschirme, den Ausgang in
`~/.config/labwc/autostart` vorgeben: `INFODISPLAY_OUTPUT=HDMI-A-1 /opt/infodisplay/kiosk.sh &`.
Alternativ lässt sich die Drehung auch am Pi-Desktop unter *Einstellungen → Bildschirmkonfiguration* einstellen –
dann `rotation = 0` lassen.

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
| ui | `show_seconds` | true | Sekunden in der Uhr |
| ui | `focus` | calendar | Querformat: was groß angezeigt wird, `calendar` oder `news` (Abschnitt 7) |
| ui | `saver_speed` | 40 | Bildschirmschoner ohne Verbindung: Tempo der Uhr in Pixel pro Sekunde |
| ui | `cover_background` | true | Hintergrund als Farbverlauf passend zum Cover (`false` = immer schwarz) |
| ui | `news_seconds` | 12 | Leiste unten: Sekunden bis zur nächsten Schlagzeile |
| ui | `news_page_seconds` | 30 | Schlagzeilen groß: Sekunden bis zum Weiterblättern |
| ui | `layout` | auto | `auto` (nach Bildschirmform), `landscape` oder `portrait` – siehe Abschnitt 7 |
| ui | `rotation` | 0 | Bildschirm drehen: `0`, `90`, `180`, `270` (Hochformat: `90` oder `270`) |
| time | `sync_from_pc` | true | Systemzeit des Pi nach der Uhr des PCs stellen (Pi hat ohne Internet keine genaue Zeit) |
| debug | `tcp_test_port` | 0 | TCP-Testzugang (nur zum Testen) |
| logging | `file` / `level` | /var/log/infodisplay/… / INFO | Zentrales Log |

Nach Änderungen: `sudo systemctl restart infodisplay` (ohne SSH-Zugang: Abschnitt 11.3)

### Windows – `%APPDATA%\InfoDisplay\config.ini`

| Abschnitt | Schlüssel | Standard | Bedeutung |
|---|---|---|---|
| link | `pi_mac` | – | Bluetooth-Adresse des Pi |
| link | `channel` / `token` | 22 / – | wie am Pi |
| media | `poll_interval` | 1.0 | Abfrage in Sekunden |
| media | `preferred_apps` | leer | z. B. `spotify` – nur diese App anzeigen |
| media | `send_cover` / `cover_max_px` | true / 400 | Cover übertragen und verkleinern |
| media | `cover_max_kb` | 40 | Höchstgröße des Covers in KB – kleiner = schnellerer Liedwechsel über Bluetooth |
| calendar | `enabled` | true | Outlook-Termine lesen |
| calendar | `start_outlook` | false | Outlook bei Bedarf selbst starten |
| calendar | `days_ahead` / `max_events` | 1 / 10 | Zeitraum und Anzahl |
| calendar | `hide_subjects` | false | **Datenschutz:** nur „Termin“ statt Betreff/Ort |
| calendar | `hide_private` | true | Private Termine als „Privater Termin“ |
| calendar | `restrict_date_format` | `%d.%m.%Y %H:%M` | Datumsformat für Outlook-Filter (Systemsprache) |
| weather | `enabled` | false | Wetter abrufen (Open-Meteo) |
| weather | `place` / `latitude` / `longitude` | Graz / 47.07 / 15.44 | Ort |
| weather | `refresh_minutes` | 15 | Aktualisierung |
| news | `enabled` | false | Schlagzeilen abrufen |
| news | `feeds` | ORF News | RSS-/Atom-Adressen, kommagetrennt |
| news | `max_headlines` / `refresh_minutes` | 10 / 15 | Anzahl (abwechselnd aus allen Feeds), Aktualisierung |
| news | `with_text` | true | Kurztext der Meldung mitsenden (sichtbar bei `focus = news`) |
| internet | `proxy` / `timeout` | leer / 15 | Proxy (leer = Windows-Einstellung), Zeitlimit je Abruf |
| internet | `strict_tls` | false | `true` = zusätzlich strenge Zertifikatsprüfung von Python 3.13 (scheitert an Firmen-Firewalls) |
| logging | `file` / `level` | `%LOCALAPPDATA%\InfoDisplay\logs\sender.log` / INFO | Zentrales Log |

Nach Änderungen: Aufgabe neu starten
(`Stop-ScheduledTask "InfoDisplay Sender"; Start-ScheduledTask "InfoDisplay Sender"`).

---

## 9. Update auf eine neue Version

Bei einem Update bleiben die Konfigurationen erhalten (`/etc/infodisplay/config.ini` am Pi,
`%APPDATA%\InfoDisplay\config.ini` am PC) – Token und Kopplung müssen **nicht** neu eingerichtet werden.
Welche Version installiert ist: `cat /opt/infodisplay/VERSION` (Pi) bzw. `CHANGELOG.md` für die Änderungen.

### Pi

Variante A (Projekt mit `git clone` geholt):
```bash
cd ~/infodisplay
git pull
cd pi-display/install
sudo ./install.sh
sudo reboot
```
Variante B (ohne git): neue ZIP am PC entpacken, Ordner wie in Abschnitt 3 per `scp` nach `~/infodisplay/` kopieren
(alte Dateien werden überschrieben), dann wie oben `sudo ./install.sh` und `sudo reboot`.

**Von Variante B auf A wechseln:** Meldet `git pull` den Fehler `fatal: not a git repository`, wurde der Ordner
per `scp` angelegt. Einmalig neu holen (die Konfiguration liegt in `/etc/infodisplay` und bleibt erhalten):
```bash
rm -rf ~/infodisplay
git clone https://github.com/RookieIVG/RDash.git ~/infodisplay
cd ~/infodisplay/pi-display/install
sudo ./install.sh
sudo reboot
```

Variante C (**USB-Stick, ohne Internet am Pi**) – siehe 9.1.

`install.sh` kopiert das Programm neu nach `/opt/infodisplay`, aktualisiert den Dienst und startet ihn neu.
Der Neustart des Pi sorgt dafür, dass auch die Anzeige im Browser die neue Version lädt. Ohne Internet installiert
`install.sh` nur dann Pakete nach, wenn etwas fehlt – bei einem Update ist normalerweise alles schon vorhanden.

### 9.1 Pi per USB-Stick aktualisieren (ohne Internet)

Es gibt eigene Pakete für Pi und PC: `infodisplay-pi-<Version>.zip` (nur Pi) und `infodisplay-pc-<Version>.zip`
(nur PC). Erzeugt werden sie mit `tools/make_packages.sh`.

**1. Am PC:** `infodisplay-pi-<Version>.zip` auf einen USB-Stick kopieren (nicht entpacken). Jeder normale Stick
(FAT32/exFAT) geht.

**2. Am Pi:** Stick anstecken und ein Terminal öffnen – direkt am Pi: **Alt+F4** (Anzeige schließen), dann
**Strg+Alt+T**; oder per SSH. Der Pi-Desktop bindet den Stick automatisch unter `/media/<benutzer>/<Stickname>` ein:
```bash
ls /media/$USER/*/infodisplay-pi-*.zip
```
Erscheint dort nichts (z. B. kein Desktop angemeldet), den Stick von Hand einbinden:
```bash
lsblk                                   # Stick suchen, meist sda1
sudo mkdir -p /mnt/usb && sudo mount /dev/sda1 /mnt/usb
ls /mnt/usb/infodisplay-pi-*.zip        # in den Befehlen unten dann /mnt/usb statt /media/$USER/* verwenden
```

**3. Entpacken** (ersetzt die alten Programmdateien in `~/infodisplay`; die Config in `/etc/infodisplay` bleibt):
```bash
ZIP=$(ls /media/$USER/*/infodisplay-pi-*.zip | sort -V | tail -1); echo "$ZIP"
rm -rf ~/infodisplay
python3 -m zipfile -e "$ZIP" ~/
cat ~/infodisplay/VERSION               # zeigt die neue Version
```

**4. Installieren:**
```bash
cd ~/infodisplay/pi-display/install
chmod +x install.sh
sudo ./install.sh
```

**5. Stick abmelden und neu starten:**
```bash
cd ~ && sync
sudo umount /media/$USER/* 2>/dev/null; sudo umount /mnt/usb 2>/dev/null; true
sudo reboot
```
Nach dem Neustart: `cat /opt/infodisplay/VERSION` zeigt die installierte Version.

> War `~/infodisplay` vorher ein `git clone`, ist es danach ein normaler Ordner. Spätere Updates wieder per USB-Stick
> – oder bei vorhandenem Internet erneut wie unter „Von Variante B auf A wechseln“.

> Neue Einstellungen einer Version stehen in `pi-display/config/config.example.ini` und im `CHANGELOG.md`.
> Sie werden **nicht** automatisch in die bestehende Config übernommen – bei Bedarf von Hand in
> `/etc/infodisplay/config.ini` ergänzen (fehlende Einträge verwenden den Standardwert).

### Windows-PC

1. Neue ZIP herunterladen (Link oben) und entpacken, z. B. nach `C:\Tools\infodisplay` (alten Ordner ersetzen).
2. PowerShell als normaler Benutzer:
   ```powershell
   cd C:\Tools\infodisplay\windows-sender
   powershell -ExecutionPolicy Bypass -File .\install.ps1
   ```
   Das Skript beendet den laufenden Sender, aktualisiert Programm und Pakete und startet ihn wieder.

Pi und PC sollten auf derselben Version laufen (Protokollversion `v = 1` muss gleich sein).

---

## 10. PC wechseln (neuen Sender einrichten)

> Ausführliche Anleitung mit Config-Übertragung und Hinweisen für Firmen-PCs: [`ANLEITUNG-FIRMEN-PC.md`](ANLEITUNG-FIRMEN-PC.md).

Wenn ein anderer Windows-PC die Daten senden soll (neuer Arbeitsplatz, Tausch-PC):

**1. Neuen PC am Pi koppeln** – wie Abschnitt 4 (Bluetooth koppeln), mit dem neuen PC.

**2. Sender am neuen PC installieren** – wie Abschnitt 5. In die Config dieselben Werte wie bisher eintragen:
`pi_mac`, `channel` und `token` (am Pi nachsehen):
```bash
sudo grep -E '^(channel|token)' /etc/infodisplay/config.ini
bluetoothctl show | head -1
```

**3. Allowlist anpassen** (nur falls `allowed_macs` gesetzt ist): in `/etc/infodisplay/config.ini` die
Bluetooth-Adresse des neuen PCs eintragen bzw. die alte ersetzen, dann `sudo systemctl restart infodisplay`.
Die Adresse des neuen PCs zeigt `bluetoothctl devices` am Pi.

**4. Alten PC entfernen:**
- Am alten PC: `.\install.ps1 -Uninstall` im Ordner `windows-sender` und unter *Einstellungen → Bluetooth und
  Geräte* den Pi entfernen.
- Am Pi die alte Kopplung löschen:
  ```bash
  bluetoothctl devices                 # Adresse des alten PCs suchen
  bluetoothctl remove AA:BB:CC:DD:EE:FF
  ```

**5. Optional – neuen Token erzeugen** (empfohlen, wenn der alte PC weitergegeben wird oder der Token
bekannt geworden ist):
```bash
NEU=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
sudo sed -i "s|^token = .*|token = $NEU|" /etc/infodisplay/config.ini
sudo systemctl restart infodisplay
echo "$NEU"
```
Den neuen Token in `%APPDATA%\InfoDisplay\config.ini` am neuen PC eintragen und den Sender neu starten
(`Stop-ScheduledTask "InfoDisplay Sender"; Start-ScheduledTask "InfoDisplay Sender"`).

> **Wichtig:** Der Pi nimmt immer nur **einen** Sender an – meldet sich ein zweiter an, ersetzt er den ersten.
> Läuft der Sender am alten PC weiter, verdrängen sich beide PCs ständig gegenseitig. Deshalb Schritt 4 nicht
> auslassen (oder den alten PC über `allowed_macs` bzw. einen neuen Token aussperren).

---

## 11. Bedienung am Pi (Anzeige starten, Uhrzeit, ohne SSH)

### 11.1 Anzeige manuell starten

Die Anzeige besteht aus zwei Teilen: dem **Dienst** `infodisplay` (empfängt die Daten, liefert die Seite) und dem
**Browser im Vollbild** (Kiosk), der die Seite zeigt.

**Dienst:**
```bash
sudo systemctl start infodisplay      # starten
sudo systemctl restart infodisplay    # neu starten (z. B. nach Config-Änderung)
systemctl status infodisplay          # läuft er? -> "active (running)"
curl http://127.0.0.1:8080/healthz    # -> {"status":"ok"}
```

**Vollbild-Anzeige – direkt am Pi** (Terminal am Desktop: **Strg+Alt+T**):
```bash
pkill chromium; /opt/infodisplay/kiosk.sh &
```
`pkill chromium` beendet einen bereits laufenden Browser, damit nicht zwei Fenster offen sind. Beenden der
Vollbild-Anzeige: **Alt+F4**.

**Vollbild-Anzeige – per SSH** (als dein normaler Benutzer, z. B. `admin`, nicht mit `sudo`):
```bash
pkill chromium
WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/$(id -u) nohup /opt/infodisplay/kiosk.sh >/dev/null 2>&1 &
```
Bleibt der Monitor leer: `ls /run/user/$(id -u)/` zeigt den Namen des Bildschirms – steht dort z. B. `wayland-1`,
diesen statt `wayland-0` verwenden.

**Am einfachsten:** `sudo reboot` – danach starten Dienst und Anzeige automatisch.

**Zum Testen ohne Vollbild:** Chromium am Pi-Desktop normal öffnen und `http://127.0.0.1:8080/` aufrufen,
**F11** schaltet Vollbild ein/aus.

| Wenn nichts erscheint | Befehl |
|---|---|
| Läuft der Dienst? Fehlermeldung? | `sudo journalctl -u infodisplay -n 30 --no-pager` |
| Ist der Autostart eingetragen? | `cat ~/.config/labwc/autostart` → muss `/opt/infodisplay/kiosk.sh &` enthalten |
| Ist Chromium installiert? | `command -v chromium chromium-browser` |

Fehlt der Autostart-Eintrag: `sudo ./install.sh` im Ordner `~/infodisplay/pi-display/install` erneut ausführen –
als normaler Benutzer mit `sudo`, nicht als root angemeldet.

### 11.2 Uhrzeit von Hand stellen

Normalerweise nicht nötig: Sobald der PC verbunden ist, stellt der Pi seine Uhr nach der PC-Zeit
(`[time] sync_from_pc`). Von Hand stellen nur, bevor der PC das erste Mal verbunden ist oder beim Testen ohne PC.

**1. Zeitzone prüfen** – `Time zone` muss `Europe/Vienna` sein:
```bash
timedatectl
sudo timedatectl set-timezone Europe/Vienna     # falls nicht
```
Liegt die Uhr genau 1 oder 2 Stunden daneben, war es nur die Zeitzone.

**2. Uhrzeit stellen** (Ortszeit):
```bash
sudo date -s "2026-10-28 14:30:00"
```
Die Anzeige übernimmt die neue Zeit sofort. (`sudo timedatectl set-time …` funktioniert nur, wenn die automatische
Zeitsynchronisation aus ist – sonst Meldung „Automatic time synchronization is enabled“. `date -s` geht immer.)

**3. Für den nächsten Start merken:**
```bash
sudo fake-hwclock save 2>/dev/null; sudo hwclock -w 2>/dev/null; true
```
Der Pi hat ohne Batterie keine laufende Uhr: Nach dem Ausschalten startet er mit der zuletzt gespeicherten Zeit,
bis sich der PC verbindet. Dauerhaft hilft nur eine Uhr mit Batterie (Pi 5: RTC-Batterie, Pi 4: RTC-Modul).

### 11.3 Config ändern ohne SSH

Die Einstellungen stehen in `/etc/infodisplay/config.ini` (die Datei `config.example.ini` im Projektordner ist nur
die Vorlage).

**A – direkt am Pi mit Tastatur** (geht immer):
1. USB-Tastatur (und ggf. Maus) an den Pi anstecken.
2. **Alt+F4** schließt die Vollbild-Anzeige, der Desktop erscheint.
3. Terminal öffnen: **Strg+Alt+T** (oder Himbeer-Menü → *Zubehör → Terminal*).
4. Bearbeiten:
   ```bash
   sudo nano /etc/infodisplay/config.ini
   ```
   Speichern: **Strg+O**, **Enter** · Beenden: **Strg+X**
5. `sudo reboot` – danach startet die Anzeige wieder automatisch.

Bleibt der Bildschirm nach Alt+F4 schwarz: **Strg+Alt+F2** wechselt zu einer Textkonsole – dort mit Benutzer und
Passwort anmelden und Schritt 4 und 5 ausführen.

**B – LAN-Kabel direkt zwischen Laptop und Pi** (kein WLAN/Firmennetz nötig): Netzwerkkabel direkt verbinden,
ca. eine Minute warten, dann in PowerShell meist:
```powershell
ssh admin@RDash.local
```
(Benutzer und Hostname wie bei deinem Pi.) Klappt das nicht, Weg A verwenden.

---

## 12. Sicherheitskonzept

| Maßnahme | Umsetzung |
|---|---|
| Kopplung | Bluetooth-Kopplung mit Zahlenvergleich, PC als „trusted“ |
| Anmeldung | Gemeinsamer Token (32 Byte zufällig), Vergleich zeitkonstant (`hmac.compare_digest`) |
| Geräte-Allowlist | Optional `allowed_macs` |
| Rate-Limiting | Verbindungsversuche pro Gerät, Nachrichten pro Verbindung, HTTP-Anfragen pro IP, max. SSE-Clients |
| Eingabeprüfung | Max. Nachrichtengröße, Typ-/Längenprüfung, Steuerzeichen entfernt, Cover nur JPEG/PNG (Magic Bytes) |
| Ausgabe | Anzeige setzt Texte nur per `textContent` (kein HTML), strikte Content-Security-Policy |
| Internet | Nur der PC greift aufs Internet zu (Wetter/Feeds, nur `http`/`https`, max. 2 MB, Zeitlimit, XML ohne externe Entitäten/Entity-Bomben). Zertifikate werden immer geprüft (Kette bis zu einer vertrauenswürdigen Stelle im Windows-Zertifikatsspeicher, Servername). Der Pi bleibt offline und prüft auch diese Daten (Typ, Länge, Wertebereich) |
| Webserver | Nur `127.0.0.1`, nur lesende GET-Endpunkte, Pfadprüfung gegen Directory Traversal, Security-Header |
| Konfiguration | Zugangsdaten außerhalb des Web-Roots: `/etc/infodisplay` (640) bzw. `%APPDATA%` (nur Benutzer) |
| Dienst | Eigener Systembenutzer ohne Login, systemd-Härtung (`ProtectSystem=strict`, `NoNewPrivileges`, …); einzige Sonderberechtigung `CAP_SYS_TIME` (Uhr stellen, nur mit Zeitstempeln angemeldeter Sender, nur Werte ab 2024) |
| Logging | Zentrales, rotierendes Log; abgelehnte Anmeldungen und Verstöße werden protokolliert |

*Nicht zutreffend:* Prepared Statements/PDO (keine Datenbank), Sessions und CSRF-Tokens (keine Anmeldung im
Browser, keine schreibenden Endpunkte). Die Bluetooth-Verbindung ist durch die Kopplung verschlüsselt.

---

## 13. Fehlersuche

| Problem | Lösung |
|---|---|
| Sender-Log: `TimeoutError` / `Verbindung abgelehnt` | Pi an? `systemctl status infodisplay`. Kanal gleich? Kopplung vorhanden (Windows-Einstellungen)? |
| `Anmeldung abgelehnt: auth` | Token am PC stimmt nicht mit `/etc/infodisplay/config.ini` überein |
| Pi-Log: `bluetooth-Server konnte nicht starten: Address already in use` | Anderen Kanal wählen (z. B. 23) – an beiden Seiten |
| Status „Keine Verbindung“, PC zeigt „Gekoppelt“ | Normal bis der Sender läuft. Aufgabe „InfoDisplay Sender“ in der Aufgabenplanung prüfen |
| Musik wird nicht erkannt | Nicht jede App meldet sich bei Windows. Test mit `--test`; ggf. `preferred_apps` leeren |
| Kein Cover | Manche Apps (z. B. Browser) liefern kein Cover → Platzhalter wird angezeigt |
| Keine Termine | Läuft Outlook (Classic)? `start_outlook = true` setzen. Log auf „Datumsformat“ prüfen |
| `Failed to set power on: org.bluez.Error.Failed` | Bluetooth per rfkill gesperrt → Abschnitt 2.2 |
| Kopplung schlägt fehl | Auf dem Pi `bluetoothctl` → `remove <PC-MAC>`, in Windows Gerät entfernen, Schritt 4 wiederholen |
| Hochformat-Bild verdreht oder nicht gedreht | `rotation` auf `270` statt `90` setzen; Ausgangsname prüfen: `wlr-randr` in einem Terminal am Pi-Desktop |
| Popup „Übersetzen? Deutsch / Englisch“ oben rechts | Ab 1.2.2 abgeschaltet: Update einspielen (Abschnitt 9) und Pi neu starten. Prüfen: `cat /etc/chromium/policies/managed/infodisplay.json` |
| `CERTIFICATE_VERIFY_FAILED … Missing Authority Key Identifier` | Firmen-Firewall prüft verschlüsselte Verbindungen (TLS-Inspection); ihre Zertifikate erfüllen die strenge Zusatzprüfung von Python 3.13 nicht. Ab Version 1.10.2 behoben (`[internet] strict_tls = false`, Standard) – Sender aktualisieren |
| `CERTIFICATE_VERIFY_FAILED … unable to get local issuer certificate` | Die Zertifizierungsstelle der Firma fehlt im Windows-Zertifikatsspeicher des PCs → IT fragen. Zertifikatsprüfung **nicht** abschalten |
| Kein Wetter / keine Schlagzeilen | Am PC `sender.py --test` ausführen: Fehlermeldungen zeigen, ob Proxy (`[internet] proxy`) oder Feed-Adresse falsch ist. Sender-Log auf „Feed nicht lesbar“ / „Wetter nicht abrufbar“ prüfen. Pi und PC müssen ab Version 1.4.0 laufen |
| Mauszeiger sichtbar | Ab 1.3.0 wird er beim Start ausgeblendet und in die Ecke geschoben (`wlrctl`, wird von `install.sh` installiert). Sonst Maus einmal bewegen oder abstecken – im Betrieb wird keine Maus gebraucht |
| Falsche Uhrzeit (Pi ohne Internet) | Der Pi hat keine Uhr mit Batterie und stellt sich ohne Internet nicht selbst. Ab 1.9.0 übernimmt er die Zeit vom PC, sobald dieser verbunden ist (Log: „Systemzeit vom PC übernommen“). Bis dahin – z. B. direkt nach dem Einschalten – kann sie falsch sein. Von Hand stellen: Abschnitt 11.2. Abhilfe dafür: Pi 5 mit RTC-Batterie bzw. RTC-Modul beim Pi 4 |
| Uhrzeit genau 1 oder 2 Stunden falsch | Zeitzone des Pi falsch: `timedatectl` prüfen, setzen mit `sudo timedatectl set-timezone Europe/Vienna` |
| Log: „Systemzeit kann nicht gestellt werden“ | Dienst ohne Berechtigung (alte Dienstdatei) → `sudo ./install.sh` erneut ausführen |
| Liedwechsel hängt / Verbindung bricht ab | Siehe „Bluetooth-Verbindung verbessern“ unten |
| Schwarzer Bildschirm / Anzeige weg | `curl 127.0.0.1:8080/healthz`; Autostart: `cat ~/.config/labwc/autostart`; Anzeige von Hand starten: Abschnitt 11.1 |

### Bluetooth-Verbindung verbessern (Liedwechsel hängt, Verbindung bricht ab)

Beim Liedwechsel wird das Cover übertragen – mit Abstand die größte Nachricht. Bluetooth schafft je nach Umgebung
nur 10–100 KB/s. Ab Version 1.10.0 kommt der Titel deshalb **zuerst** (sofort sichtbar), das Cover folgt in kleinen
Stücken – ein neuer Titel drängt sich dazwischen, ein überholtes Cover wird abgebrochen; das
Cover wird auf höchstens `cover_max_kb` (40 KB) verkleinert, und große Nachrichten brechen die Verbindung nicht
mehr ab, nur weil sie länger brauchen. Ist es trotzdem zäh, liegt es an der Funkstrecke:

| Ursache | Abhilfe |
|---|---|
| **WLAN und Bluetooth am Pi teilen sich die Antenne** (2,4 GHz) | Pi per LAN-Kabel anbinden oder WLAN im **5-GHz**-Band nutzen. Wird WLAN am Pi nicht gebraucht: `sudo nmcli radio wifi off` (wieder an: `… wifi on`) |
| **Energiesparen am PC** schaltet Bluetooth zeitweise ab | Geräte-Manager → *Bluetooth* → Adapter → Eigenschaften → *Energieverwaltung* → Haken bei „Computer kann das Gerät ausschalten, um Energie zu sparen“ entfernen |
| Abstand / Hindernisse (Metallschrank, Wand) | Pi und PC näher zusammen, Sichtverbindung |
| USB-3-Geräte (Docking, Festplatte) neben dem Bluetooth-Adapter stören 2,4 GHz | USB-3-Geräte weiter weg bzw. Bluetooth-Stick an einem Verlängerungskabel |
| Sehr schlechte Strecke | Cover kleiner: `[media] cover_max_kb = 20` · notfalls ohne Cover: `send_cover = false` |

**Messen:** am PC `[logging] level = DEBUG` setzen und Sender neu starten – im Log steht dann z. B.
`cover gesendet: 38.5 KB in 1.2 s`. Daraus ergibt sich die Übertragungsrate (hier ca. 32 KB/s).
Am Pi zeigt `sudo journalctl -u infodisplay -f`, wann und warum Verbindungen enden.

**Logs:**
- Pi: `sudo journalctl -u infodisplay -f` oder `/var/log/infodisplay/infodisplay.log`
- Windows: `%LOCALAPPDATA%\InfoDisplay\logs\sender.log` (für Details `level = DEBUG`)

---

## 14. Nachrichtenprotokoll

Eine JSON-Nachricht pro Zeile (UTF-8, abgeschlossen mit `\n`), Protokollversion `v = 1`.

| Richtung | Typ | Inhalt |
|---|---|---|
| PC → Pi | `hello` | `v`, `token`, `client`, `app_version` – muss die erste Nachricht sein |
| PC → Pi | *(alle)* | `sent_at_ms` – Uhrzeit des PCs (ms seit 1970, UTC); der Pi stellt danach seine Uhr (bei `hello` und `ping`) |
| Pi → PC | `welcome` / `error` | `server_version` bzw. `reason` (`auth`, `protocol_version`) |
| PC → Pi | `media` | `active`, `status` (playing/paused/stopped), `title`, `artist`, `album`, `source_app`, `position_ms`, `duration_ms`, `cover_id` |
| PC → Pi | `cover_chunk` | `id`, `mime`, `index`, `total`, `b64` (Teil) – Cover in Stücken à 4096 Zeichen, nur bei Titelwechsel; dazwischen dürfen andere Nachrichten kommen, ein überholtes Cover wird abgebrochen |
| PC → Pi | `cover` | `id` (Hash), `mime`, `b64` – ganzes Cover in einer Nachricht (Sender bis 1.9.x, wird weiter angenommen) |
| PC → Pi | `calendar` | `events[]` mit `subject`, `location`, `start`, `end` (lokal, `YYYY-MM-DDTHH:MM`), `all_day` |
| PC → Pi | `weather` | `place`, `temp`, `code` (WMO-Wettercode), `is_day`, `t_max`, `t_min` – optional, alle 15 min |
| PC → Pi | `news` | `items[]` mit `title`, `source`, `text` (Kurztext, optional) – max. 30, alle 15 min |
| PC → Pi | `ping` | Lebenszeichen alle 20 s |
| PC → Pi | `bye` | Sender beendet sich |

Weitere Datenquellen (z. B. Systemwerte, Benachrichtigungen) lassen sich als neuer Nachrichtentyp ergänzen:
Sender-Modul in `windows-sender/includes`, Prüfung in `pi-display/includes/protocol.py`, Anzeige in `app.js`.

---

## 15. Versionierung und Changelog

Versionen nach **Semantic Versioning** (`MAJOR.MINOR.PATCH`) in der Datei `VERSION`.
Version und Changelog werden gemeinsam erhöht:

```bash
python tools/bump_version.py patch "Cover wird bei Titelwechsel zuverlässiger geladen"
python tools/bump_version.py minor "Anzeige der CPU-Auslastung"
python tools/bump_version.py major "Protokoll v2"
```

Die Versionsnummer steht in beiden Logs, am Pi in `/opt/infodisplay/VERSION` und unter `http://127.0.0.1:8080/api/state`.

---

## 16. Ordnerstruktur

```
infodisplay/
├── VERSION                     Versionsnummer (SemVer)
├── CHANGELOG.md                Änderungsprotokoll
├── README.md                   diese Anleitung
├── ANLEITUNG-FIRMEN-PC.md      Umzug auf einen anderen PC (Firmen-PC), Config übertragen, Kopplung
├── tools/
│   ├── bump_version.py         Version + Changelog automatisch fortschreiben
│   ├── make_packages.sh        Pakete erzeugen: komplett, nur Pi, nur PC
│   └── fake_sender.py          Testsender mit Beispieldaten
├── windows-sender/
│   ├── sender.py               Hauptprogramm
│   ├── install.ps1             Installation/Deinstallation, Autostart
│   ├── requirements.txt
│   ├── config/config.example.ini
│   └── includes/               config, logger, protocol, link_client, media, calendar_outlook, web_feeds
└── pi-display/
    ├── receiver.py             Hauptprogramm (Dienst)
    ├── config/config.example.ini
    ├── includes/               config, logger, protocol, state, link_server, web_server, ratelimit
    ├── install/                install.sh, infodisplay.service, kiosk.sh
    └── web/                    Web-Root: index.html, 404.html, 500.html
        └── assets/             css/, js/, img/, vendor/bootstrap-icons/, vendor/meteocons/ (Wetter-Icons)
```
