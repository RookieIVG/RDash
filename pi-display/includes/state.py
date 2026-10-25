"""Thread-sicherer Zustand der Anzeige (letzte Medien-, Cover- und Kalenderdaten).

Jede Änderung erhöht die Versionsnummer; der Webserver wartet darauf und
schickt den neuen Stand per Server-Sent Events an den Browser.
"""

import threading
import time


def now_ms():
    return int(time.time() * 1000)


class DisplayState:
    def __init__(self, app_info, ui):
        self._cond = threading.Condition()
        self.version = 0
        self._app = app_info
        self._ui = ui
        self._media = {"active": False}
        self._media_anchor_ms = None
        self._cover = None                 # (id, mime, bytes)
        self._calendar = None
        self._calendar_received_ms = None
        self._weather = None
        self._news = None
        self._link = {"connected": False, "client": None, "address": None,
                      "since_ms": None, "last_message_ms": None}

    def _changed(self):
        self.version += 1
        self._cond.notify_all()

    # ------------------------------------------------------------ Schreiben
    def set_link(self, connected, client=None, address=None):
        with self._cond:
            stamp = now_ms()
            if connected:
                self._link = {"connected": True, "client": client, "address": address,
                              "since_ms": stamp, "last_message_ms": stamp}
            else:
                self._link.update({"connected": False, "since_ms": stamp})
            self._changed()

    def touch(self):
        """Lebenszeichen (Ping) – ändert nur den Zeitstempel."""
        with self._cond:
            self._link["last_message_ms"] = now_ms()
            self._changed()

    def set_media(self, media):
        with self._cond:
            self._media = media
            self._media_anchor_ms = now_ms()   # Position gilt ab Empfangszeit
            self._link["last_message_ms"] = self._media_anchor_ms
            self._changed()

    def set_cover(self, cover_id, mime, data):
        with self._cond:
            self._cover = (cover_id, mime, data)
            self._link["last_message_ms"] = now_ms()
            self._changed()

    def set_calendar(self, events):
        with self._cond:
            self._calendar = events
            self._calendar_received_ms = now_ms()
            self._link["last_message_ms"] = self._calendar_received_ms
            self._changed()

    def set_weather(self, weather):
        with self._cond:
            self._weather = dict(weather, received_ms=now_ms())
            self._link["last_message_ms"] = self._weather["received_ms"]
            self._changed()

    def set_news(self, items):
        with self._cond:
            self._news = {"items": list(items), "received_ms": now_ms()}
            self._link["last_message_ms"] = self._news["received_ms"]
            self._changed()

    # ------------------------------------------------------------ Lesen
    def get_cover(self):
        with self._cond:
            return self._cover

    def snapshot(self):
        with self._cond:
            media = dict(self._media)
            cover_ready = bool(self._cover and media.get("cover_id") == self._cover[0])
            media["cover_url"] = f"/api/cover?id={self._cover[0]}" if cover_ready else None
            media["anchor_ms"] = self._media_anchor_ms
            return {
                "version": self.version,
                "server_now_ms": now_ms(),
                "app": self._app,
                "ui": self._ui,
                "link": dict(self._link),
                "media": media,
                "calendar": {
                    "events": list(self._calendar) if self._calendar is not None else None,
                    "received_ms": self._calendar_received_ms,
                },
                "weather": dict(self._weather) if self._weather else None,
                "news": {"items": list(self._news["items"]), "received_ms": self._news["received_ms"]}
                        if self._news else None,
            }

    def wait_for_change(self, since_version, timeout):
        """Blockiert, bis sich die Version ändert oder timeout abläuft."""
        with self._cond:
            if self.version == since_version:
                self._cond.wait(timeout)
            return self.version

    def wake_all(self):
        with self._cond:
            self._cond.notify_all()
