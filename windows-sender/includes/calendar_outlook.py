"""Liest die nächsten Termine aus dem Standardkalender von Outlook (Classic)
über COM. Muss in einem Thread laufen, in dem COM initialisiert ist.

Hinweis: Das „neue Outlook“ (olk.exe) bietet keine COM-Schnittstelle.
"""

from datetime import datetime, timedelta

from .logger import get_logger

log = get_logger("calendar")

OL_FOLDER_CALENDAR = 9
OL_PRIVATE = 2
MAX_SCAN = 2000
# Ersatzformat, falls das Datumsformat der Systemsprache nicht greift
_FALLBACK_FORMATS = ("%m/%d/%Y %I:%M %p",)


def _naive(value):
    """pywin32 liefert lokale Zeiten mit falscher Zeitzonenangabe -> als lokale Zeit behandeln."""
    return datetime(value.year, value.month, value.day, value.hour, value.minute, value.second)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M")


class OutlookCalendar:
    def __init__(self, cfg):
        self.cfg = cfg
        self._warned_not_running = False

    def _get_outlook(self):
        import win32com.client  # noqa: WPS433 – nur unter Windows verfügbar
        try:
            return win32com.client.GetActiveObject("Outlook.Application")
        except Exception:
            if self.cfg.start_outlook:
                return win32com.client.Dispatch("Outlook.Application")
            if not self._warned_not_running:
                log.info("Outlook läuft nicht – Kalender wird übersprungen")
                self._warned_not_running = True
            return None

    def _restricted(self, items, start, end):
        formats = (self.cfg.restrict_date_format,) + tuple(f for f in _FALLBACK_FORMATS
                                                           if f != self.cfg.restrict_date_format)
        for fmt in formats:
            flt = f"[Start] < '{end.strftime(fmt)}' AND [End] > '{start.strftime(fmt)}'"
            try:
                result = items.Restrict(flt)
                first = result.GetFirst()
                # Plausibilitätsprüfung: erster Treffer muss im Zeitraum liegen
                if first is None or (_naive(first.End) > start and _naive(first.Start) < end):
                    return result
                log.debug("Filterformat %s liefert unplausible Treffer", fmt)
            except Exception as exc:
                log.debug("Filterformat %s abgelehnt: %s", fmt, exc)
        log.warning("Kein passendes Datumsformat für Outlook-Filter – prüfe calendar.restrict_date_format")
        return None

    def fetch(self):
        """Liefert eine Liste von Terminen oder None, wenn Outlook nicht verfügbar ist."""
        outlook = self._get_outlook()
        if outlook is None:
            return None
        self._warned_not_running = False

        now = datetime.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=self.cfg.days_ahead + 1)

        folder = outlook.GetNamespace("MAPI").GetDefaultFolder(OL_FOLDER_CALENDAR)
        items = folder.Items
        items.Sort("[Start]")                 # Reihenfolge laut Microsoft: erst sortieren,
        items.IncludeRecurrences = True       # dann Serientermine einbeziehen
        restricted = self._restricted(items, start, end)
        if restricted is None:
            return []

        events = []
        scanned = 0
        item = restricted.GetFirst()
        while item is not None and scanned < MAX_SCAN:
            scanned += 1
            try:
                ev_start, ev_end = _naive(item.Start), _naive(item.End)
                if ev_start >= end:
                    break
                if ev_end > now:
                    private = int(getattr(item, "Sensitivity", 0)) == OL_PRIVATE
                    subject = (item.Subject or "").strip() or "(ohne Betreff)"
                    location = (item.Location or "").strip()
                    if self.cfg.hide_subjects:
                        subject, location = "Termin", ""
                    elif private and self.cfg.hide_private:
                        subject, location = "Privater Termin", ""
                    events.append({
                        "subject": subject[:200],
                        "location": location[:120],
                        "start": _iso(ev_start),
                        "end": _iso(ev_end),
                        "all_day": bool(item.AllDayEvent),
                    })
            except Exception as exc:  # einzelne defekte Einträge überspringen
                log.debug("Termin übersprungen: %s", exc)
            item = restricted.GetNext()

        events.sort(key=lambda e: (e["start"], not e["all_day"]))
        return events[: self.cfg.max_events]
