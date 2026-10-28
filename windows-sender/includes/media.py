"""Liest die aktuell laufende Wiedergabe über die Windows-Medienschnittstelle
(System Media Transport Controls). Damit werden u. a. Spotify, Windows
Media Player, VLC sowie Musik/Videos in Edge, Chrome und Firefox erkannt.
"""

import base64
import hashlib
import io
from datetime import datetime, timezone

from .logger import get_logger

log = get_logger("media")

try:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    )
    from winrt.windows.storage.streams import Buffer, InputStreamOptions
    WINRT_AVAILABLE = True
except ImportError:  # z. B. beim Testen unter Linux
    WINRT_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Werte von GlobalSystemMediaTransportControlsSessionPlaybackStatus
_STATUS = {0: "stopped", 1: "stopped", 2: "stopped", 3: "stopped", 4: "playing", 5: "paused"}

# Bekannte App-IDs -> lesbarer Name
_APP_NAMES = {
    "spotify": "Spotify",
    "msedge": "Microsoft Edge",
    "chrome": "Google Chrome",
    "firefox": "Firefox",
    "zunemusic": "Medienwiedergabe",
    "vlc": "VLC",
    "foobar2000": "foobar2000",
    "itunes": "iTunes",
    "applemusic": "Apple Music",
    "teams": "Microsoft Teams",
    "amazonmusic": "Amazon Music",
    "tidal": "TIDAL",
    "deezer": "Deezer",
}

MAX_THUMBNAIL_BYTES = 5 * 1024 * 1024
MAX_COVER_ATTEMPTS = 5


def app_display_name(app_id):
    """Macht aus 'Spotify.exe' oder 'Microsoft.ZuneMusic_8wek...!App' einen lesbaren Namen."""
    lowered = (app_id or "").lower()
    for key, name in _APP_NAMES.items():
        if key in lowered:
            return name
    base = (app_id or "").split("!")[0].split("_")[0]
    base = base.rsplit("\\", 1)[-1]
    if base.lower().endswith(".exe"):
        base = base[:-4]
    return base or "Unbekannt"


def _ms(td):
    try:
        return max(0, int(td.total_seconds() * 1000))
    except (AttributeError, TypeError):
        return 0


def prepare_cover(raw, max_px, max_bytes=40 * 1024):
    """Verkleinert das Cover auf max_px und liefert (bytes, mime) oder None.

    Ziel ist eine kleine Datei (max_bytes): Bluetooth schafft je nach Umgebung nur 10–100 KB/s,
    ein großes Cover würde den Liedwechsel spürbar verzögern. Erst wird die JPEG-Qualität
    gesenkt, reicht das nicht, auch die Größe.
    """
    if PIL_AVAILABLE:
        try:
            img = Image.open(io.BytesIO(raw))
            img = img.convert("RGB")
            img.thumbnail((max_px, max_px))
            data = b""
            for _ in range(4):
                for quality in (82, 72, 62):
                    out = io.BytesIO()
                    img.save(out, format="JPEG", quality=quality, optimize=True)
                    data = out.getvalue()
                    if len(data) <= max_bytes:
                        return data, "image/jpeg"
                img.thumbnail((int(img.width * 0.8), int(img.height * 0.8)))
            return data, "image/jpeg"
        except Exception as exc:  # defektes Bild
            log.debug("Cover konnte nicht verkleinert werden: %s", exc)
    if raw[:3] == b"\xff\xd8\xff":
        mime = "image/jpeg"
    elif raw[:8] == b"\x89PNG\r\n\x1a\n":
        mime = "image/png"
    else:
        return None
    if len(raw) > 512 * 1024:
        return None
    return raw, mime


class MediaWatcher:
    def __init__(self, cfg):
        if not WINRT_AVAILABLE:
            raise RuntimeError("winrt-Pakete fehlen – bitte requirements.txt installieren")
        self.cfg = cfg
        self._manager = None
        self._track_key = None
        self._cover_id = None
        self._cover_attempts = 0

    async def _get_manager(self):
        if self._manager is None:
            self._manager = await MediaManager.request_async()
        return self._manager

    def reset(self):
        """Nach Fehlern neu verbinden (z. B. wenn der Explorer neu gestartet wurde)."""
        self._manager = None

    def _pick_session(self, manager):
        sessions = list(manager.get_sessions() or [])
        if self.cfg.preferred_apps:
            preferred = [s for s in sessions
                         if any(p in (s.source_app_user_model_id or "").lower() for p in self.cfg.preferred_apps)]
            if preferred:
                sessions = preferred
        playing = [s for s in sessions if int(s.get_playback_info().playback_status) == 4]
        if playing:
            return playing[0]
        if not self.cfg.preferred_apps:
            current = manager.get_current_session()
            if current is not None:
                return current
        return sessions[0] if sessions else None

    async def _read_thumbnail(self, ref):
        stream = await ref.open_read_async()
        try:
            size = int(stream.size)
            if size <= 0 or size > MAX_THUMBNAIL_BYTES:
                return None
            buf = Buffer(size)
            result = await stream.read_async(buf, size, InputStreamOptions.READ_AHEAD)
            return bytes(memoryview(result)[: int(result.length)])
        finally:
            try:
                stream.close()
            except Exception:
                pass

    async def read(self):
        """Liefert (media_dict, cover_dict|None)."""
        manager = await self._get_manager()
        session = self._pick_session(manager)
        if session is None:
            self._track_key = None
            self._cover_id = None
            return {"active": False}, None

        props = await session.try_get_media_properties_async()
        info = session.get_playback_info()
        timeline = session.get_timeline_properties()

        status = _STATUS.get(int(info.playback_status), "stopped")
        title = (props.title or "").strip() if props else ""
        artist = (props.artist or "").strip() if props else ""
        album = (props.album_title or "").strip() if props else ""
        app_id = session.source_app_user_model_id or ""

        duration = _ms(timeline.end_time) - _ms(timeline.start_time)
        position = _ms(timeline.position) - _ms(timeline.start_time)
        if status == "playing" and duration > 0:
            # Windows aktualisiert die Position nur gelegentlich -> hochrechnen
            last = timeline.last_updated_time
            if isinstance(last, datetime) and last.year > 1970:
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                elapsed = (datetime.now(timezone.utc) - last).total_seconds() * 1000
                rate = 1.0
                try:
                    if info.playback_rate is not None:
                        rate = float(info.playback_rate) or 1.0
                except (TypeError, ValueError):
                    pass
                if 0 < elapsed < duration:
                    position += int(elapsed * rate)
        position = max(0, min(position, duration)) if duration > 0 else 0

        media = {
            "active": bool(title or artist),
            "status": status,
            "title": title,
            "artist": artist,
            "album": album,
            "source_app": app_display_name(app_id),
            "position_ms": position,
            "duration_ms": max(0, duration),
        }

        # Cover nur bei Titelwechsel lesen (Windows liefert es oft verzögert)
        cover = None
        key = f"{app_id}|{title}|{artist}|{album}"
        if key != self._track_key:
            self._track_key = key
            self._cover_id = None
            self._cover_attempts = 0
        if (self.cfg.send_cover and self._cover_id is None and props is not None
                and props.thumbnail is not None and self._cover_attempts < MAX_COVER_ATTEMPTS):
            self._cover_attempts += 1
            try:
                raw = await self._read_thumbnail(props.thumbnail)
                prepared = prepare_cover(raw, self.cfg.cover_max_px, self.cfg.cover_max_kb * 1024) if raw else None
                if prepared:
                    data, mime = prepared
                    self._cover_id = hashlib.sha1(data).hexdigest()[:16]
                    cover = {"id": self._cover_id, "mime": mime, "b64": base64.b64encode(data).decode("ascii")}
                    log.debug("Cover gelesen (%d Bytes, %s)", len(data), mime)
            except Exception as exc:
                log.debug("Cover nicht lesbar (Versuch %d): %s", self._cover_attempts, exc)

        media["cover_id"] = self._cover_id
        return media, cover
