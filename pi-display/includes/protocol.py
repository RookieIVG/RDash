"""Prüfung und Bereinigung eingehender Nachrichten vom Windows-Sender.

Alles, was über Bluetooth ankommt, gilt als nicht vertrauenswürdig:
Typen, Längen und Wertebereiche werden streng geprüft.
"""

import base64
import binascii
import json
import re
import unicodedata

PROTOCOL_VERSION = 1
MAX_TEXT = 300
MAX_EVENTS = 50
MAX_COVER_BYTES = 2 * 1024 * 1024
MAX_HEADLINES = 30
_ISO_LOCAL = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$")
_HEX_ID = re.compile(r"^[0-9a-f]{8,64}$")
_STATUSES = {"playing", "paused", "stopped"}


class ProtocolError(ValueError):
    """Nachricht ungültig."""


def encode(message):
    return json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"


def decode(line):
    try:
        message = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"kein gültiges JSON: {exc}") from exc
    if not isinstance(message, dict) or not isinstance(message.get("type"), str):
        raise ProtocolError("Nachricht ohne Typ")
    return message


def clean_text(value, maxlen=MAX_TEXT):
    if value is None:
        return ""
    text = str(value)
    # Steuerzeichen entfernen (Darstellung erfolgt zusätzlich nur per textContent)
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C" or ch == " ")
    return text.strip()[:maxlen]


def _int(value, low, high, default=0):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def parse_media(data):
    if not isinstance(data, dict):
        raise ProtocolError("media.data fehlt")
    if not data.get("active"):
        return {"active": False}
    status = data.get("status")
    cover_id = data.get("cover_id")
    duration = _int(data.get("duration_ms"), 0, 24 * 3600 * 1000)
    return {
        "active": True,
        "status": status if status in _STATUSES else "stopped",
        "title": clean_text(data.get("title")),
        "artist": clean_text(data.get("artist")),
        "album": clean_text(data.get("album")),
        "source_app": clean_text(data.get("source_app"), 60),
        "position_ms": _int(data.get("position_ms"), 0, duration or 0),
        "duration_ms": duration,
        "cover_id": cover_id if isinstance(cover_id, str) and _HEX_ID.match(cover_id) else None,
    }


def parse_cover(data):
    if not isinstance(data, dict):
        raise ProtocolError("cover.data fehlt")
    cover_id = data.get("id")
    if not isinstance(cover_id, str) or not _HEX_ID.match(cover_id):
        raise ProtocolError("ungültige Cover-ID")
    b64 = data.get("b64")
    if not isinstance(b64, str) or len(b64) > MAX_COVER_BYTES * 4 // 3 + 4:
        raise ProtocolError("Cover fehlt oder zu groß")
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ProtocolError("Cover nicht dekodierbar") from exc
    if raw[:3] == b"\xff\xd8\xff":
        mime = "image/jpeg"
    elif raw[:8] == b"\x89PNG\r\n\x1a\n":
        mime = "image/png"
    else:
        raise ProtocolError("Cover ist kein JPEG/PNG")
    return cover_id, mime, raw


def _num(value, low, high):
    """Zahl im Bereich oder None (z. B. fehlender Wetterwert)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value or not low <= value <= high:   # NaN oder außerhalb
        return None
    return round(float(value), 1)


def parse_weather(data):
    if not isinstance(data, dict):
        raise ProtocolError("weather.data fehlt")
    temp = _num(data.get("temp"), -80, 70)
    if temp is None:
        raise ProtocolError("weather.temp fehlt oder ungültig")
    return {
        "place": clean_text(data.get("place"), 40),
        "temp": temp,
        "code": _int(data.get("code"), 0, 99),
        "is_day": bool(data.get("is_day", True)),
        "t_max": _num(data.get("t_max"), -80, 70),
        "t_min": _num(data.get("t_min"), -80, 70),
    }


def parse_news(data):
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ProtocolError("news.items fehlt")
    items = []
    for item in data["items"][:MAX_HEADLINES]:
        if not isinstance(item, dict):
            continue
        title = clean_text(item.get("title"), 200)
        if title:
            items.append({"title": title, "source": clean_text(item.get("source"), 40),
                          "text": clean_text(item.get("text"), 400)})
    return items


def parse_calendar(data):
    if not isinstance(data, dict) or not isinstance(data.get("events"), list):
        raise ProtocolError("calendar.events fehlt")
    events = []
    for item in data["events"][:MAX_EVENTS]:
        if not isinstance(item, dict):
            continue
        start, end = item.get("start"), item.get("end")
        if not (isinstance(start, str) and isinstance(end, str)
                and _ISO_LOCAL.match(start) and _ISO_LOCAL.match(end)):
            continue
        events.append({
            "subject": clean_text(item.get("subject"), 200) or "(ohne Betreff)",
            "location": clean_text(item.get("location"), 120),
            "start": start,
            "end": end,
            "all_day": bool(item.get("all_day")),
        })
    return events
