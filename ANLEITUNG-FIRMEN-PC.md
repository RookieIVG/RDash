# InfoDisplay auf dem Firmen-PC einrichten

Diese Anleitung führt Schritt für Schritt durch den Umzug des Senders auf einen neuen Windows-PC, zum Beispiel
vom privaten Laptop auf den Firmen-PC:

1. Vorab mit der IT klären
2. Paket auf den Firmen-PC bringen
3. Python installieren
4. Sender installieren
5. Config vom alten PC übertragen
6. Display (Raspberry Pi) an den Firmen-PC anlernen
7. Alten PC abmelden
8. Testen
9. Einstellungen für den Firmeneinsatz
10. Fehlersuche

Am **Raspberry Pi** ändert sich nichts außer der Bluetooth-Kopplung. Token, Kanal und Anzeige-Einstellungen
bleiben gleich.

> **Begriffe:** *Alter PC* = der PC, auf dem das InfoDisplay bisher läuft. *Firmen-PC* = der neue PC.
> Befehle für **PowerShell** stehen in `powershell`-Blöcken, Befehle für den **Pi** (per SSH) in `bash`-Blöcken.

---

## Checkliste (Kurzfassung)

- [ ] Mit der IT geklärt: Python, PowerShell-Skript, Bluetooth, Aufgabenplanung, ggf. Proxy (Abschnitt 1)
- [ ] ZIP auf dem Firmen-PC entpackt (Abschnitt 2)
- [ ] Python 3.13 (64 Bit) installiert (Abschnitt 3)
- [ ] `install.ps1` ausgeführt (Abschnitt 4)
- [ ] `config.ini` vom alten PC übernommen, Datei auf dem USB-Stick gelöscht (Abschnitt 5)
- [ ] Firmen-PC mit dem Pi gekoppelt (Abschnitt 6)
- [ ] Sender am alten PC deaktiviert (Abschnitt 7)
- [ ] Test erfolgreich: `--test`, Anzeige zeigt Musik/Termine/Wetter (Abschnitt 8)
- [ ] Datenschutz-Einstellungen geprüft (Abschnitt 9)

---

## 1. Vorab mit der IT klären

Auf verwalteten Firmen-PCs sind manche Dinge per Gruppenrichtlinie gesperrt. Diese Punkte am besten vorher klären:

| Was | Wofür | Wenn gesperrt |
|---|---|---|
| **Python 3.13 installieren** (nur für den eigenen Benutzer, ohne Admin) | Der Sender ist ein Python-Programm | IT installiert Python (z. B. über das Software-Center) – „py launcher“ mit installieren |
| **PowerShell-Skript ausführen** (`-ExecutionPolicy Bypass`) | Installation mit `install.ps1` | IT führt die Installation einmalig aus oder gibt das Skript frei |
| **Bluetooth koppeln** | Verbindung zum Pi | Ohne Bluetooth geht es nicht |
| **Aufgabenplanung für den eigenen Benutzer** | Automatischer Start bei der Anmeldung | Ersatz: Verknüpfung im Autostart-Ordner (Abschnitt 10) |
| **Internetzugriff von Python** (nur für Wetter/Schlagzeilen und die Paketinstallation) | `pypi.org`, `files.pythonhosted.org`, `api.open-meteo.com`, eure Feed-Adressen | Wetter/Schlagzeilen abschalten; Pakete installiert die IT |
| **Proxy-Adresse** (falls vorhanden) | pip und Wetter/Schlagzeilen | Adresse bei der IT erfragen (z. B. `http://proxy.firma.at:8080`) |
| **Outlook (Classic)** | Termine | Mit dem „neuen Outlook“ gibt es keine Termine (`[calendar] enabled = false`) |

> **Datenschutz:** Der Monitor ist für andere sichtbar. Termine aus dem Firmenkalender (Betreff, Ort) sollten ggf.
> ausgeblendet werden – siehe Abschnitt 9.

---

## 2. Paket auf den Firmen-PC bringen

Variante A – direkt aus dem Internet: <https://github.com/RookieIVG/RDash/archive/refs/heads/main.zip>
herunterladen (entpackt heißt der Ordner `RDash-main`).

Variante B – mitgebrachtes Paket `infodisplay-<Version>.zip` (z. B. per USB-Stick oder OneDrive).

Entpacken nach **`C:\Tools\infodisplay`** (Ordner ggf. anlegen). Danach muss es diese Datei geben:
`C:\Tools\infodisplay\windows-sender\install.ps1`

> Liegt der Ordner unter `RDash-main` oder `infodisplay\infodisplay`, den inneren Ordner nach `C:\Tools\infodisplay`
> verschieben.

Falls Windows die Dateien als „aus dem Internet“ markiert hat, einmalig in PowerShell:
```powershell
Get-ChildItem C:\Tools\infodisplay -Recurse | Unblock-File
```

---

## 3. Python installieren

1. <https://www.python.org/downloads/windows/> → **Python 3.13 – Windows installer (64-bit)**.
2. Im Installer:
   - Haken bei **„Add python.exe to PATH“**
   - Haken bei **„Use admin privileges when installing py.exe“ entfernen**, falls keine Admin-Rechte vorhanden
   - **„Install Now“** (installiert nur für deinen Benutzer)
3. Prüfen in einer **neuen** PowerShell:
   ```powershell
   py -3.13 --version        # -> Python 3.13.x
   ```
   Geht `py` nicht, dann `python --version` – das Installationsskript probiert beides.

---

## 4. Sender installieren

PowerShell **als normaler Benutzer** öffnen (nicht „Als Administrator“, sonst landet alles beim falschen Benutzer).

**Nur hinter einem Proxy** vorher setzen (Adresse von der IT):
```powershell
$env:HTTPS_PROXY = "http://proxy.firma.at:8080"
$env:HTTP_PROXY  = "http://proxy.firma.at:8080"
```

Installation:
```powershell
cd C:\Tools\infodisplay\windows-sender
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Das Skript legt an:

| Was | Wo |
|---|---|
| Programm + Python-Umgebung | `%LOCALAPPDATA%\InfoDisplay\app` und `...\venv` |
| Konfiguration (nur für dich lesbar) | `%APPDATA%\InfoDisplay\config.ini` |
| Autostart | Aufgabe **„InfoDisplay Sender“** in der Aufgabenplanung (bei Anmeldung) |
| Log | `%LOCALAPPDATA%\InfoDisplay\logs\sender.log` |

Am Ende öffnet sich Notepad mit einer **leeren Beispiel-Config** – **schließen, ohne zu speichern**.
Die richtige Config kommt im nächsten Schritt vom alten PC.

> Fehler „Paketinstallation fehlgeschlagen“ → Proxy fehlt oder die Firma prüft SSL-Verbindungen. Siehe Abschnitt 10.

---

## 5. Config vom alten PC übertragen

In der Config stehen Bluetooth-Adresse des Pi, Kanal, **Token** und deine Einstellungen (Wetter, Feeds, …).
Der Pi muss dadurch **nicht** neu eingerichtet werden.

### 5.1 Am alten PC: Config sichern

USB-Stick anstecken (hier Laufwerk `E:` – ggf. anpassen) und in PowerShell:
```powershell
Copy-Item "$env:APPDATA\InfoDisplay\config.ini" "E:\infodisplay-config.ini"
```
Alternativ die Datei über OneDrive/Firmenlaufwerk übertragen. **Nicht per E-Mail verschicken** – sie enthält den
geheimen Token.

### 5.2 Am Firmen-PC: Config übernehmen

```powershell
$quelle = "E:\infodisplay-config.ini"
$ziel   = "$env:APPDATA\InfoDisplay\config.ini"
[IO.File]::WriteAllText($ziel, [IO.File]::ReadAllText($quelle))
```
Dieser Befehl schreibt den Inhalt in die bestehende Datei. So bleibt deren Zugriffsschutz (nur dein Benutzer)
erhalten. Bitte nicht die Datei im Explorer darüberkopieren.

Danach die Kopie auf dem Stick **löschen**:
```powershell
Remove-Item "E:\infodisplay-config.ini"
```

### 5.3 Am Firmen-PC: Config prüfen und anpassen

```powershell
notepad "$env:APPDATA\InfoDisplay\config.ini"
```

| Abschnitt | Was prüfen |
|---|---|
| `[link]` | `pi_mac`, `channel`, `token` – bleiben **unverändert** |
| `[internet]` | Firmen-Proxy eintragen, falls nötig: `proxy = http://proxy.firma.at:8080` |
| `[calendar]` | Firmen-Outlook (Classic)? `enabled = true`. Datenschutz: siehe Abschnitt 9 |
| `[media]` | `preferred_apps` ggf. anpassen (z. B. leer lassen) |
| `[weather]`, `[news]` | bleiben wie bisher – nur sinnvoll, wenn der Firmen-PC ins Internet darf |

Speichern (Notepad speichert automatisch als UTF-8 – passt).

### 5.4 Ohne alten PC: Config neu ausfüllen

Ist der alte PC nicht mehr verfügbar, die Werte am Pi nachsehen (per SSH):
```bash
sudo grep -E '^(channel|token)' /etc/infodisplay/config.ini
bluetoothctl show | head -1          # Bluetooth-Adresse des Pi -> pi_mac
```
und in `%APPDATA%\InfoDisplay\config.ini` unter `[link]` eintragen (`pi_mac`, `channel`, `token`).

---

## 6. Display (Raspberry Pi) an den Firmen-PC anlernen

Die Kopplung ist **einmalig** nötig. Pi und Firmen-PC müssen in Reichweite sein (wenige Meter).

### 6.1 Am Pi: Kopplung erlauben

Per SSH anmelden (vom alten PC oder vom Firmen-PC: `ssh admin@RDash.local` bzw. mit IP – siehe README 2.1)
und **die SSH-Sitzung offen lassen**:
```bash
bluetoothctl
```
In der `bluetoothctl`-Konsole nacheinander eingeben:
```
power on
agent KeyboardDisplay
default-agent
pairable on
discoverable on
```

### 6.2 Am Firmen-PC: Pi hinzufügen

1. *Einstellungen → Bluetooth und Geräte* → Bluetooth **Ein**.
2. Erscheint der Pi später nicht in der Liste: *Bluetooth und Geräte → Geräte →* ganz unten
   **„Bluetooth-Geräteerkennung“ auf „Erweitert“** stellen.
3. **„Gerät hinzufügen“ → „Bluetooth“** → den Pi auswählen (Name = Hostname, z. B. `RDash`).
4. Windows zeigt eine **6-stellige PIN**. Am Pi erscheint gleichzeitig
   `Confirm passkey 123456 (yes/no)` → prüfen, dass die Zahl gleich ist, am Pi **`yes`** eingeben,
   am PC **„Verbinden“** klicken.
5. Fragt der Pi `Authorize service …` → **`yes`**.

Windows zeigt den Pi danach als **„Gekoppelt“** (nicht „Verbunden“) – das ist richtig.

### 6.3 Am Pi: Firmen-PC als vertrauenswürdig markieren

Noch in der `bluetoothctl`-Konsole:
```
devices
```
Die Zeile mit dem Namen des Firmen-PCs suchen, z. B. `Device CC:6B:1E:8B:D0:F4 LAPTOP-FIRMA`, dann:
```
trust CC:6B:1E:8B:D0:F4
discoverable off
quit
```

### 6.4 Nur falls `allowed_macs` verwendet wird

```bash
sudo grep allowed_macs /etc/infodisplay/config.ini
```
Ist dort eine Adresse eingetragen, die des Firmen-PCs **ergänzen** (kommagetrennt) oder die alte ersetzen:
```bash
sudo nano /etc/infodisplay/config.ini      # allowed_macs = CC:6B:1E:8B:D0:F4
sudo systemctl restart infodisplay
```
Ist der Wert leer, nichts tun.

---

## 7. Alten PC abmelden

**Wichtig:** Der Pi nimmt immer nur **einen** Sender an. Laufen alter PC und Firmen-PC gleichzeitig, verdrängen sie
sich ständig gegenseitig. Deshalb am alten PC eine der beiden Varianten:

**Variante A – alter PC soll später wieder senden können** (z. B. Homeoffice/Firma im Wechsel):
```powershell
Disable-ScheduledTask -TaskName "InfoDisplay Sender"
Stop-ScheduledTask    -TaskName "InfoDisplay Sender"
```
Später wieder einschalten (und dafür am anderen PC deaktivieren):
```powershell
Enable-ScheduledTask -TaskName "InfoDisplay Sender"
Start-ScheduledTask  -TaskName "InfoDisplay Sender"
```

**Variante B – alter PC wird nicht mehr verwendet:**
```powershell
cd C:\Tools\infodisplay\windows-sender      # bzw. wo das Paket am alten PC liegt
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Uninstall
```
Dann unter *Einstellungen → Bluetooth und Geräte* den Pi entfernen und am Pi die alte Kopplung löschen:
```bash
bluetoothctl devices                        # Adresse des alten PCs suchen
bluetoothctl remove AA:BB:CC:DD:EE:FF
```
Wird der alte PC weitergegeben, zusätzlich einen **neuen Token** erzeugen (README Abschnitt 10, Schritt 5) und
ihn in die Config des Firmen-PCs eintragen.

---

## 8. Testen

**1. Daten am Firmen-PC lesen** (ohne zu senden):
```powershell
& "$env:LOCALAPPDATA\InfoDisplay\venv\Scripts\python.exe" "$env:LOCALAPPDATA\InfoDisplay\app\sender.py" --test
```
Erwartet: `MEDIEN` (Musik vorher z. B. in Spotify starten), `KALENDER` (Outlook muss laufen), sowie `WETTER` und
`SCHLAGZEILEN`, falls eingeschaltet.

**2. Sender starten:**
```powershell
Start-ScheduledTask -TaskName "InfoDisplay Sender"
```

**3. Am Pi prüfen** (nach ca. 10 Sekunden):
```bash
sudo journalctl -u infodisplay -n 5 --no-pager      # -> "Sender 'LAPTOP-FIRMA' verbunden über bluetooth"
curl -s http://127.0.0.1:8080/api/state | python3 -c "
import json,sys; d=json.load(sys.stdin)
print('Verbunden:', d['link']['connected'], d['link']['client'])
print('Wetter   :', bool(d.get('weather')))
print('Schlagzeilen:', len((d.get('news') or {}).get('items', [])))"
```

**4. Auf dem Monitor:** Musik, Termine, Wetter und Schlagzeilen erscheinen innerhalb weniger Sekunden.

**5. Neustart-Test:** Firmen-PC ab- und wieder anmelden – der Sender startet automatisch und verbindet sich neu.

---

## 9. Einstellungen für den Firmeneinsatz

In `%APPDATA%\InfoDisplay\config.ini` am Firmen-PC, danach Sender neu starten:
```powershell
Stop-ScheduledTask "InfoDisplay Sender"; Start-ScheduledTask "InfoDisplay Sender"
```

| Einstellung | Empfehlung | Wirkung |
|---|---|---|
| `[calendar] hide_subjects` | `true`, wenn andere den Monitor sehen | Statt Betreff/Ort steht nur „Termin“ |
| `[calendar] hide_private` | `true` (Standard) | Private Termine nur als „Privater Termin“ |
| `[calendar] days_ahead` | `0` oder `1` | Nur heute bzw. heute + morgen |
| `[calendar] start_outlook` | `false` | Outlook wird nicht selbst gestartet |
| `[media] preferred_apps` | z. B. `spotify` | Nur diese App anzeigen (keine Teams-/Browser-Töne) |
| `[internet] proxy` | Proxy der Firma | Für Wetter/Schlagzeilen |
| `[news] feeds` | z. B. Intranet-Feed (falls vorhanden) | Eigene Schlagzeilen |

**Energiesparen:** Geht der Firmen-PC in den Standby, trennt sich die Verbindung; nach dem Aufwachen verbindet sich
der Sender selbst neu. Solange keine Verbindung besteht, zeigt das Display nur Uhr und Datum als Bildschirmschoner.

---

## 10. Fehlersuche am Firmen-PC

| Problem | Lösung |
|---|---|
| `install.ps1` startet nicht („Ausführung von Skripts ist deaktiviert“ / „nicht digital signiert“) | `Unblock-File` (Abschnitt 2) und den Befehl genau wie angegeben mit `-ExecutionPolicy Bypass` ausführen. Hilft das nicht, ist es per Richtlinie gesperrt → IT |
| „Kein passendes Python gefunden“ | Python 3.13 **64 Bit** installieren, PowerShell neu öffnen. Notfalls Pfad angeben: `.\install.ps1 -Python "C:\Pfad\zu\python.exe"` |
| „Paketinstallation fehlgeschlagen“ | Proxy setzen (Abschnitt 4). Bei `CERTIFICATE_VERIFY_FAILED` prüft die Firma SSL-Verbindungen → IT fragen, ob `pypi.org` und `files.pythonhosted.org` freigegeben werden können |
| Pi taucht beim Koppeln nicht auf | Am Pi `discoverable on`; am PC „Bluetooth-Geräteerkennung: Erweitert“ (Abschnitt 6.2); Abstand verringern |
| Kopplung schlägt fehl | Am PC den Pi entfernen, am Pi `bluetoothctl remove <PC-Adresse>`, Abschnitt 6 wiederholen |
| Pi-Log: `Verbindung von nicht freigegebenem Gerät … abgelehnt` | Adresse des Firmen-PCs in `allowed_macs` ergänzen (Abschnitt 6.4) |
| Sender-Log: `Anmeldung abgelehnt: auth` | Token falsch → Config neu übertragen (Abschnitt 5) oder Token am Pi nachsehen (5.4) |
| Sender-Log: `Konfiguration fehlerhaft` | Die Meldung nennt den Eintrag. Häufig: `pi_mac` falsch geschrieben (`AA:BB:CC:DD:EE:FF`) |
| Anzeige springt zwischen zwei PCs hin und her | Alter PC sendet noch → Abschnitt 7 |
| Keine Termine | Outlook (Classic) muss laufen; im „neuen Outlook“ gibt es keine Termine |
| Kein Wetter / keine Schlagzeilen | `--test` ausführen: „timed out“ / „407“ → Proxy fehlt bzw. verlangt Anmeldung (IT). Nutzt die Firma eine automatische Proxy-Konfiguration (PAC), den Proxy in `[internet] proxy` fest eintragen |
| Aufgabenplanung gesperrt | Autostart per Verknüpfung (siehe unten) |

**Autostart ohne Aufgabenplanung** (nur falls die Aufgabe nicht angelegt werden darf):
```powershell
$lnk = "$([Environment]::GetFolderPath('Startup'))\InfoDisplay Sender.lnk"
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$s.TargetPath = "$env:LOCALAPPDATA\InfoDisplay\venv\Scripts\pythonw.exe"
$s.Arguments = "`"$env:LOCALAPPDATA\InfoDisplay\app\sender.py`""
$s.WorkingDirectory = "$env:LOCALAPPDATA\InfoDisplay\app"
$s.Save()
```
Der Sender startet dann bei jeder Anmeldung (ohne automatischen Neustart nach einem Absturz).

**Logs:**
- Firmen-PC: `%LOCALAPPDATA%\InfoDisplay\logs\sender.log` (für Details `[logging] level = DEBUG`)
- Pi: `sudo journalctl -u infodisplay -f`

Weitere Details stehen in der `README.md` (Abschnitte 5, 8, 10, 11 und 13).
