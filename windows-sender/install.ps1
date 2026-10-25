<#
.SYNOPSIS
    Installiert den InfoDisplay-Sender für den aktuellen Benutzer.

.DESCRIPTION
    - kopiert das Programm nach %LOCALAPPDATA%\InfoDisplay\app
    - legt eine virtuelle Python-Umgebung an und installiert die Pakete
    - legt die Konfiguration unter %APPDATA%\InfoDisplay\config.ini an (falls nicht vorhanden)
    - richtet eine Aufgabe in der Aufgabenplanung ein (Start bei Anmeldung)

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\install.ps1
    powershell -ExecutionPolicy Bypass -File .\install.ps1 -Uninstall
#>
param(
    [switch]$Uninstall,
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$TaskName = "InfoDisplay Sender"
$AppRoot  = Join-Path $env:LOCALAPPDATA "InfoDisplay"
$AppDir   = Join-Path $AppRoot "app"
$VenvDir  = Join-Path $AppRoot "venv"
$ConfDir  = Join-Path $env:APPDATA "InfoDisplay"
$ConfFile = Join-Path $ConfDir "config.ini"
$Src      = $PSScriptRoot

function Write-Step($text) { Write-Host "==> $text" -ForegroundColor Cyan }

# ---------------------------------------------------------------- Deinstallation
if ($Uninstall) {
    Write-Step "Entferne Aufgabe '$TaskName'"
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Step "Entferne Programmdateien ($AppDir, $VenvDir)"
    Remove-Item -Recurse -Force $AppDir, $VenvDir -ErrorAction SilentlyContinue
    Write-Host "Fertig. Konfiguration und Logs bleiben erhalten: $ConfDir, $AppRoot\logs" -ForegroundColor Green
    exit 0
}

# ---------------------------------------------------------------- Python suchen
Write-Step "Suche Python 3.12+ (64 Bit)"
$candidates = @()
if ($Python) { $candidates += ,@($Python) }
$candidates += ,@("py", "-3.13"), ,@("py", "-3.12"), ,@("py", "-3.14"), ,@("py", "-3"), ,@("python")
$PyCmd = $null
foreach ($c in $candidates) {
    try {
        $exe = $c[0]; $pyArgs = @($c | Select-Object -Skip 1)
        $out = & $exe @pyArgs -c "import sys,struct;print('%d.%d %d' % (sys.version_info[0], sys.version_info[1], struct.calcsize('P')*8))" 2>$null
        if ($LASTEXITCODE -eq 0 -and $out -match "^(\d+)\.(\d+) (\d+)$") {
            if ([int]$Matches[1] -eq 3 -and [int]$Matches[2] -ge 12 -and [int]$Matches[3] -eq 64) { $PyCmd = $c; break }
        }
    } catch { }
}
if (-not $PyCmd) {
    throw "Kein passendes Python gefunden. Bitte Python 3.12 oder 3.13 (64 Bit) von python.org installieren."
}
Write-Host "    gefunden: $($PyCmd -join ' ')"

# ---------------------------------------------------------------- Laufenden Sender beenden (Update)
# Sonst sind python(w).exe in der venv gesperrt und das Update schlägt fehl
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Write-Step "Beende laufenden Sender"
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

# ---------------------------------------------------------------- Dateien kopieren
Write-Step "Kopiere Programm nach $AppDir"
New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
Copy-Item -Force (Join-Path $Src "sender.py"), (Join-Path $Src "requirements.txt") $AppDir
Copy-Item -Recurse -Force (Join-Path $Src "includes") $AppDir
$versionFile = Join-Path $Src "..\VERSION"
if (Test-Path $versionFile) { Copy-Item -Force $versionFile $AppDir }

# ---------------------------------------------------------------- venv + Pakete
Write-Step "Lege virtuelle Umgebung an und installiere Pakete"
$exe = $PyCmd[0]; $pyArgs = @($PyCmd | Select-Object -Skip 1)
& $exe @pyArgs -m venv $VenvDir
if ($LASTEXITCODE -ne 0) { throw "venv konnte nicht angelegt werden" }
$VenvPy  = Join-Path $VenvDir "Scripts\python.exe"
$VenvPyw = Join-Path $VenvDir "Scripts\pythonw.exe"
& $VenvPy -m pip install --upgrade pip --quiet
& $VenvPy -m pip install -r (Join-Path $AppDir "requirements.txt") --quiet
if ($LASTEXITCODE -ne 0) { throw "Paketinstallation fehlgeschlagen (Proxy? -> pip config / HTTPS_PROXY setzen)" }

# ---------------------------------------------------------------- Konfiguration
New-Item -ItemType Directory -Force -Path $ConfDir | Out-Null
if (-not (Test-Path $ConfFile)) {
    Write-Step "Lege Konfiguration an: $ConfFile"
    Copy-Item (Join-Path $Src "config\config.example.ini") $ConfFile
    $acl = Get-Acl $ConfFile
    $acl.SetAccessRuleProtection($true, $false)
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($env:USERNAME, "FullControl", "Allow")
    $acl.AddAccessRule($rule)
    Set-Acl $ConfFile $acl
    $configNew = $true
} else {
    Write-Step "Konfiguration bleibt unverändert: $ConfFile"
    $configNew = $false
}

# ---------------------------------------------------------------- Aufgabenplanung
Write-Step "Richte Autostart in der Aufgabenplanung ein"
$action    = New-ScheduledTaskAction -Execute $VenvPyw -Argument "`"$AppDir\sender.py`" --config `"$ConfFile`"" -WorkingDirectory $AppDir
$trigger   = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
             -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
             -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Principal $principal -Description "Sendet Musik- und Kalenderinfos per Bluetooth an das InfoDisplay" -Force | Out-Null

if ($configNew) {
    Write-Host ""
    Write-Host "Bitte jetzt pi_mac und token in der Konfiguration eintragen." -ForegroundColor Yellow
    Write-Host "Danach starten mit:  Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Yellow
    Start-Process notepad.exe $ConfFile
} else {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Sender gestartet." -ForegroundColor Green
}
Write-Host ""
Write-Host "Test ohne Pi:  & '$VenvPy' '$AppDir\sender.py' --test --config '$ConfFile'"
Write-Host "Log:           $AppRoot\logs\sender.log"
