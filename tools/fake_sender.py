"""Testsender: schickt Beispieldaten an den Pi – ohne Windows, Musik oder Outlook.

Beispiele:
  # direkt auf dem Pi über den TCP-Testzugang ([debug] tcp_test_port = 5099)
  python3 fake_sender.py --tcp 127.0.0.1:5099 --token <TOKEN>

  # über Bluetooth von einem Linux-Rechner
  python3 fake_sender.py --bt AA:BB:CC:DD:EE:FF --channel 22 --token <TOKEN>
"""

import argparse
import base64
import json
import socket
import time
from datetime import datetime, timedelta

# Kleines Beispiel-Cover (64x64 PNG, Farbverlauf in Firmenfarben) wird zur Laufzeit erzeugt
import struct
import zlib


def make_png(size=64):
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            t = (x + y) / (2 * size - 2)
            row += bytes((int(0 + 22 * t), int(126 + 33 * t), int(54 + 165 * t)))
        rows.append(bytes(row))
    raw = zlib.compress(b"".join(rows))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", raw) + chunk(b"IEND", b""))


def send(sock, message):
    sock.sendall(json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n")


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tcp", help="host:port des TCP-Testzugangs")
    group.add_argument("--bt", help="Bluetooth-Adresse des Pi")
    parser.add_argument("--channel", type=int, default=22)
    parser.add_argument("--token", required=True)
    parser.add_argument("--seconds", type=int, default=30, help="Wie lange Daten gesendet werden")
    parser.add_argument("--no-calendar", action="store_true", help="Keine Kalenderdaten senden (wie ohne Outlook)")
    parser.add_argument("--no-web", action="store_true", help="Kein Wetter und keine Schlagzeilen senden")
    args = parser.parse_args()

    if args.tcp:
        host, port = args.tcp.rsplit(":", 1)
        sock = socket.create_connection((host, int(port)), timeout=10)
    else:
        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        sock.settimeout(10)
        sock.connect((args.bt, args.channel))

    send(sock, {"type": "hello", "v": 1, "token": args.token, "client": "Testsender", "app_version": "test"})
    reply = sock.recv(4096).decode("utf-8").strip()
    print("Antwort:", reply)
    if '"welcome"' not in reply:
        return 1

    png = make_png()
    send(sock, {"type": "cover", "data": {"id": "abcdef0123456789", "mime": "image/png",
                                           "b64": base64.b64encode(png).decode()}})
    now = datetime.now().replace(second=0, microsecond=0)
    fmt = "%Y-%m-%dT%H:%M"
    if not args.no_calendar:
        send(sock, {"type": "calendar", "data": {"events": [
            {"subject": "Jour fixe IT", "location": "Besprechungsraum 2", "start": (now - timedelta(minutes=20)).strftime(fmt),
             "end": (now + timedelta(minutes=25)).strftime(fmt), "all_day": False},
            {"subject": "KLISAT Wartungsfenster", "location": "", "start": (now + timedelta(hours=2)).strftime(fmt),
             "end": (now + timedelta(hours=3)).strftime(fmt), "all_day": False},
            {"subject": "Schulung Datenschutz", "location": "Online (Teams)",
             "start": (now + timedelta(days=1)).replace(hour=9, minute=0).strftime(fmt),
             "end": (now + timedelta(days=1)).replace(hour=10, minute=30).strftime(fmt), "all_day": False},
        ]}})

    if not args.no_web:
        send(sock, {"type": "weather", "data": {"place": "Graz", "temp": 12.4, "code": 2, "is_day": True,
                                                 "t_max": 15.1, "t_min": 6.3}})
        send(sock, {"type": "news", "data": {"items": [
            {"title": "Testschlagzeile: Neue Straßenbahnlinie in Graz eröffnet", "source": "Testquelle",
             "text": "Die neue Linie verbindet ab Montag den Hauptbahnhof mit dem LKH. Fahrgäste profitieren von "
                     "dichteren Intervallen und neuen Niederflurwagen."},
            {"title": "Zweite Schlagzeile mit etwas längerem Text, damit man sieht, wie lange Überschriften "
                      "auf der Anzeige gekürzt werden", "source": "Testquelle"},
            {"title": "Dritte Schlagzeile", "source": "Andere Quelle", "text": "Kurzer Text zur dritten Meldung."},
            {"title": "Vierte Schlagzeile ohne Text", "source": "Andere Quelle"},
            {"title": "Fünfte Schlagzeile", "source": "Testquelle",
             "text": "Noch ein Beschreibungstext, damit die Großansicht weiterblättern muss."},
            {"title": "Sechste Schlagzeile", "source": "Andere Quelle", "text": "Text sechs."},
            {"title": "Siebte Schlagzeile", "source": "Testquelle", "text": "Text sieben mit etwas mehr Inhalt."},
        ]}})

    duration = 214_000
    start = time.time()
    while time.time() - start < args.seconds:
        pos = int((time.time() - start) * 1000) % duration
        send(sock, {"type": "media", "data": {"active": True, "status": "playing", "title": "Morning Light",
                                               "artist": "The Example Band", "album": "Testaufnahmen",
                                               "source_app": "Spotify", "position_ms": pos,
                                               "duration_ms": duration, "cover_id": "abcdef0123456789"}})
        send(sock, {"type": "ping"})
        time.sleep(5)
    send(sock, {"type": "bye"})
    sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
