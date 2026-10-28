"""Nachrichtenformat zwischen Sender und Raspberry Pi.

Jede Nachricht ist ein JSON-Objekt in einer eigenen Zeile (UTF-8, '\\n').
Muss mit pi-display/includes/protocol.py zusammenpassen.
"""

import json
import socket
import time

PROTOCOL_VERSION = 1


def now_ms():
    return int(time.time() * 1000)


def encode(message):
    """Serialisiert eine Nachricht als eine JSON-Zeile."""
    return json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"


def hello(token, app_version):
    return {
        "type": "hello",
        "v": PROTOCOL_VERSION,
        "token": token,
        "client": socket.gethostname(),
        "app_version": app_version,
        "sent_at_ms": now_ms(),
    }


def media(data):
    return {"type": "media", "sent_at_ms": now_ms(), "data": data}


def cover(cover_id, mime, b64):
    return {"type": "cover", "sent_at_ms": now_ms(), "data": {"id": cover_id, "mime": mime, "b64": b64}}


def cover_chunk(cover_id, mime, index, total, part):
    """Ein Stück des Covers (Base64). Zwischen den Stücken können andere Nachrichten gesendet werden."""
    return {"type": "cover_chunk", "sent_at_ms": now_ms(),
            "data": {"id": cover_id, "mime": mime, "index": index, "total": total, "b64": part}}


def calendar(events):
    return {"type": "calendar", "sent_at_ms": now_ms(), "data": {"events": events}}


def weather(data):
    return {"type": "weather", "sent_at_ms": now_ms(), "data": data}


def news(items):
    return {"type": "news", "sent_at_ms": now_ms(), "data": {"items": items}}


def ping():
    return {"type": "ping", "sent_at_ms": now_ms()}


def bye():
    return {"type": "bye", "sent_at_ms": now_ms()}
