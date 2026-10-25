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

# ------------------------------------------------------------------ Bildschirm drehen ([ui] rotation)
# Die Config ist für den Desktop-Benutzer nicht lesbar – der Wert kommt daher vom lokalen Dienst.
ROTATION="$(curl -fsS --max-time 2 "${HEALTH%/healthz}/api/state" 2>/dev/null \
  | python3 -c 'import json,sys; print(int(json.load(sys.stdin).get("ui",{}).get("rotation",0)))' 2>/dev/null || echo 0)"

rotate_display() {
  local transform output
  case "$ROTATION" in
    90|180|270) transform="$ROTATION" ;;
    *) transform="normal" ;;
  esac
  command -v wlr-randr >/dev/null || { echo "wlr-randr fehlt – Drehung übersprungen" >&2; return; }
  # Ausgang: INFODISPLAY_OUTPUT (z. B. HDMI-A-1) oder der erste angeschlossene Bildschirm
  output="${INFODISPLAY_OUTPUT:-$(wlr-randr 2>/dev/null | awk '/^[^ ]/ {print $1; exit}')}"
  [ -n "$output" ] || { echo "Kein Bildschirm gefunden – Drehung übersprungen" >&2; return; }
  wlr-randr --output "$output" --transform "$transform"
}

if [ "$ROTATION" != "0" ]; then
  rotate_display
  # kanshi (Bildschirmkonfiguration des Desktops) kann beim Sitzungsstart nachziehen – einmal wiederholen
  sleep 3
  rotate_display
  sleep 1
fi

BROWSER="$(command -v chromium || command -v chromium-browser)"
if [ -z "$BROWSER" ]; then
  echo "Chromium nicht gefunden" >&2
  exit 1
fi

"$BROWSER" \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-features=Translate,TranslateUI \
  --lang=de-AT \
  --check-for-update-interval=31536000 \
  --password-store=basic \
  --no-first-run \
  --start-fullscreen \
  "$URL" &
BROWSER_PID=$!

# ------------------------------------------------------------------ Mauszeiger ausblenden
# Die Seite blendet den Zeiger per CSS aus, Chromium übernimmt das aber erst nach einer Mausbewegung.
# wlrctl erzeugt diese Bewegung und schiebt den Zeiger zusätzlich in die Ecke unten rechts.
if command -v wlrctl >/dev/null; then
  for _ in 1 2 3; do
    sleep 5
    wlrctl pointer move 10000 10000 2>/dev/null || break
  done
else
  echo "wlrctl fehlt – Mauszeiger wird erst nach einer Mausbewegung ausgeblendet" >&2
fi

wait "$BROWSER_PID"
