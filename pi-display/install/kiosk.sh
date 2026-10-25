#!/usr/bin/env bash
# InfoDisplay – startet Chromium im Kiosk-Modus, sobald der lokale Dienst antwortet.
# Wird über den Autostart der Desktop-Sitzung (labwc) aufgerufen.

URL="${INFODISPLAY_URL:-http://127.0.0.1:8080/?kiosk=1}"
HEALTH="${INFODISPLAY_HEALTH:-http://127.0.0.1:8080/healthz}"

# Bildschirmschoner/Blanking ist per raspi-config deaktiviert; zusätzlich kurz warten
for _ in $(seq 1 60); do
  if curl -fsS --max-time 2 "$HEALTH" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

BROWSER="$(command -v chromium || command -v chromium-browser)"
if [ -z "$BROWSER" ]; then
  echo "Chromium nicht gefunden" >&2
  exit 1
fi

exec "$BROWSER" \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-features=Translate,TranslateUI \
  --check-for-update-interval=31536000 \
  --password-store=basic \
  --no-first-run \
  --start-fullscreen \
  "$URL"
