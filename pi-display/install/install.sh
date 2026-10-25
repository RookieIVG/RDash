#!/usr/bin/env bash
# InfoDisplay – Installation auf dem Raspberry Pi (Raspberry Pi OS mit Desktop, Bookworm/Trixie)
# Aufruf:  sudo ./install.sh            Installation bzw. Update
#          sudo ./install.sh --uninstall
set -euo pipefail

APP_DIR=/opt/infodisplay
CONF_DIR=/etc/infodisplay
CONF_FILE=$CONF_DIR/config.ini
LOG_DIR=/var/log/infodisplay
SERVICE=infodisplay
SVC_USER=infodisplay
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"
KIOSK_USER="${SUDO_USER:-}"

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m%s\033[0m\n' "$1"; }

if [[ $EUID -ne 0 ]]; then
  echo "Bitte mit sudo ausführen: sudo $0" >&2
  exit 1
fi

# ------------------------------------------------------------------ Deinstallation
if [[ "${1:-}" == "--uninstall" ]]; then
  step "Entferne Dienst und Programmdateien"
  systemctl disable --now "$SERVICE" 2>/dev/null || true
  rm -f /etc/systemd/system/$SERVICE.service
  systemctl daemon-reload
  rm -rf "$APP_DIR"
  if [[ -n "$KIOSK_USER" ]]; then
    AUTOSTART="$(getent passwd "$KIOSK_USER" | cut -d: -f6)/.config/labwc/autostart"
    [[ -f "$AUTOSTART" ]] && sed -i '/infodisplay\/kiosk.sh/d' "$AUTOSTART"
  fi
  echo "Konfiguration ($CONF_DIR) und Logs ($LOG_DIR) bleiben erhalten."
  exit 0
fi

# ------------------------------------------------------------------ Pakete
step "Installiere benötigte Pakete"
apt-get update -qq
apt-get install -y -qq python3 bluez curl >/dev/null
# wlr-randr dreht den Bildschirm für das Hochformat ([ui] rotation)
apt-get install -y -qq wlr-randr >/dev/null 2>&1 || warn "wlr-randr nicht installierbar – Drehung nur über die Bildschirmkonfiguration des Desktops möglich."
if ! command -v chromium >/dev/null && ! command -v chromium-browser >/dev/null; then
  apt-get install -y -qq chromium >/dev/null || apt-get install -y -qq chromium-browser >/dev/null
fi
python3 -c 'import socket,sys; sys.exit(0 if hasattr(socket,"AF_BLUETOOTH") else 1)' \
  || { echo "Python ohne Bluetooth-Unterstützung – Abbruch" >&2; exit 1; }

# ------------------------------------------------------------------ Benutzer & Ordner
step "Lege Dienstbenutzer und Ordner an"
id "$SVC_USER" >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin "$SVC_USER"
getent group bluetooth >/dev/null && usermod -aG bluetooth "$SVC_USER"
install -d -m 755 "$APP_DIR"
install -d -m 750 -o root -g "$SVC_USER" "$CONF_DIR"
install -d -m 750 -o "$SVC_USER" -g "$SVC_USER" "$LOG_DIR"

# ------------------------------------------------------------------ Programm kopieren
step "Kopiere Programm nach $APP_DIR"
rm -rf "$APP_DIR/includes" "$APP_DIR/web"
cp -r "$SRC_DIR/receiver.py" "$SRC_DIR/includes" "$SRC_DIR/web" "$APP_DIR/"
install -m 755 "$SRC_DIR/install/kiosk.sh" "$APP_DIR/kiosk.sh"
[[ -f "$SRC_DIR/../VERSION" ]] && cp "$SRC_DIR/../VERSION" "$APP_DIR/VERSION"
find "$APP_DIR" -name '__pycache__' -prune -exec rm -rf {} +
chown -R root:root "$APP_DIR"
chmod -R u=rwX,go=rX "$APP_DIR"

# ------------------------------------------------------------------ Konfiguration (außerhalb Web-Root)
if [[ ! -f "$CONF_FILE" ]]; then
  step "Erzeuge Konfiguration mit neuem Token"
  TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  sed "s|^token = .*|token = $TOKEN|" "$SRC_DIR/config/config.example.ini" > "$CONF_FILE"
else
  step "Konfiguration bleibt unverändert ($CONF_FILE)"
fi
chown root:"$SVC_USER" "$CONF_FILE"
chmod 640 "$CONF_FILE"

# ------------------------------------------------------------------ Bluetooth
step "Aktiviere Bluetooth"
rfkill unblock bluetooth 2>/dev/null || true
systemctl enable --now bluetooth >/dev/null
bluetoothctl power on >/dev/null 2>&1 || true

# ------------------------------------------------------------------ Dienst
step "Richte systemd-Dienst ein"
install -m 644 "$SRC_DIR/install/infodisplay.service" /etc/systemd/system/$SERVICE.service
systemctl daemon-reload
systemctl enable "$SERVICE" >/dev/null
systemctl restart "$SERVICE"

# ------------------------------------------------------------------ Kiosk-Autostart
if [[ -n "$KIOSK_USER" && "$KIOSK_USER" != "root" ]]; then
  step "Richte Kiosk-Autostart für Benutzer '$KIOSK_USER' ein"
  HOME_DIR="$(getent passwd "$KIOSK_USER" | cut -d: -f6)"
  AUTOSTART_DIR="$HOME_DIR/.config/labwc"
  install -d -o "$KIOSK_USER" -g "$KIOSK_USER" "$AUTOSTART_DIR"
  touch "$AUTOSTART_DIR/autostart"
  grep -q 'infodisplay/kiosk.sh' "$AUTOSTART_DIR/autostart" \
    || echo "$APP_DIR/kiosk.sh &" >> "$AUTOSTART_DIR/autostart"
  chown "$KIOSK_USER":"$KIOSK_USER" "$AUTOSTART_DIR/autostart"
  if command -v raspi-config >/dev/null; then
    raspi-config nonint do_blanking 1 || true      # Bildschirm nicht abschalten
    raspi-config nonint do_boot_behaviour B4 || true  # Desktop mit Auto-Login
  fi
else
  warn "Kein Desktop-Benutzer erkannt – Kiosk-Autostart übersprungen (siehe README)."
fi

# ------------------------------------------------------------------ Zusammenfassung
BT_ADDR="$(bluetoothctl show 2>/dev/null | awk '/^Controller/ {print $2; exit}')"
TOKEN_NOW="$(awk -F' = ' '/^token/ {print $2; exit}' "$CONF_FILE")"
step "Fertig"
systemctl --no-pager --lines=0 status "$SERVICE" | head -3 || true
cat <<EOF

  Bluetooth-Adresse des Pi :  ${BT_ADDR:-unbekannt (bluetoothctl show)}
  RFCOMM-Kanal             :  $(awk -F' = ' '/^channel/ {print $2; exit}' "$CONF_FILE")
  Token                    :  $TOKEN_NOW

  -> Diese drei Werte in %APPDATA%\\InfoDisplay\\config.ini am Windows-PC eintragen.
  -> Danach Bluetooth koppeln (README, Schritt 3) und den Pi neu starten.

  Log:     sudo journalctl -u $SERVICE -f   bzw.  $LOG_DIR/infodisplay.log
EOF
