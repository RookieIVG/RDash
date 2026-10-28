"""Systemzeit des Pi nach der Uhr des Windows-PCs stellen.

Der Raspberry Pi hat keine batteriegepufferte Uhr und im Betrieb kein Internet (kein NTP).
Nach einem Neustart läuft er deshalb mit der Zeit vom letzten Herunterfahren. Der PC schickt
in jeder Nachricht seinen Zeitstempel (sent_at_ms, UTC) – weicht die Pi-Uhr davon ab, wird
sie gestellt. Nur von angemeldeten Sendern (Token) und nur mit plausiblen Werten.

Benötigt die Berechtigung CAP_SYS_TIME (siehe infodisplay.service).
"""

import time

from .logger import get_logger

log = get_logger("clock")

MIN_MS = 1_704_067_200_000      # 01.01.2024 – ältere Zeitstempel sind sicher falsch
MAX_MS = 4_102_444_800_000      # 01.01.2100


class ClockSync:
    def __init__(self, enabled=True, threshold_s=2.0):
        self.enabled = enabled
        self.threshold_s = threshold_s
        self._failed = False

    def offer(self, sent_at_ms):
        """Zeitstempel vom PC prüfen und die Systemzeit bei Abweichung stellen. Liefert True, wenn gestellt."""
        if not self.enabled or self._failed:
            return False
        if isinstance(sent_at_ms, bool) or not isinstance(sent_at_ms, int) or not MIN_MS <= sent_at_ms <= MAX_MS:
            return False
        diff = sent_at_ms / 1000 - time.time()
        if abs(diff) < self.threshold_s:
            return False
        try:
            time.clock_settime(time.CLOCK_REALTIME, sent_at_ms / 1000)
        except (OSError, AttributeError) as exc:
            # einmal melden, dann nicht mehr versuchen (sonst Log-Flut alle 20 s)
            self._failed = True
            log.warning("Systemzeit kann nicht gestellt werden (%s) – Dienst braucht CAP_SYS_TIME, "
                        "install.sh erneut ausführen. Abweichung zum PC: %+.0f s", exc, diff)
            return False
        log.info("Systemzeit vom PC übernommen (Abweichung war %+.1f s)", diff)
        return True
