"""Verbindung zum Raspberry Pi über Bluetooth (RFCOMM) bzw. TCP (Testmodus).

Blockierende Socket-Klasse; der asynchrone Teil (Wiederverbinden,
Heartbeat) liegt in sender.py.
"""

import json
import socket
import threading
import time

from . import protocol
from .logger import get_logger

log = get_logger("link")

MAX_REPLY_BYTES = 64 * 1024
MIN_SEND_TIMEOUT = 15.0     # Sekunden
SLOW_BYTES_PER_S = 1000     # angenommene Mindestrate über Bluetooth (bei Störungen) für das Sendelimit


class LinkError(Exception):
    """Verbindung abgelehnt oder unterbrochen."""


class LinkClient:
    def __init__(self, cfg, app_version):
        self.cfg = cfg
        self.app_version = app_version
        self._sock = None
        self._lock = threading.Lock()

    @property
    def target(self):
        if self.cfg.transport == "tcp":
            return f"tcp://{self.cfg.tcp_host}:{self.cfg.tcp_port}"
        return f"bt://{self.cfg.pi_mac}#{self.cfg.channel}"

    def _open_socket(self):
        timeout = self.cfg.connect_timeout
        if self.cfg.transport == "tcp":
            return socket.create_connection((self.cfg.tcp_host, self.cfg.tcp_port), timeout=timeout)
        if not hasattr(socket, "AF_BLUETOOTH"):
            raise LinkError("Diese Python-Version unterstützt kein Bluetooth (AF_BLUETOOTH fehlt)")
        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        sock.settimeout(timeout)
        try:
            sock.connect((self.cfg.pi_mac, self.cfg.channel))
        except OSError:
            sock.close()
            raise
        return sock

    def _read_line(self, sock):
        buf = b""
        while b"\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                raise LinkError("Verbindung vom Pi geschlossen")
            buf += chunk
            if len(buf) > MAX_REPLY_BYTES:
                raise LinkError("Antwort des Pi zu groß")
        return buf.split(b"\n", 1)[0]

    def connect(self):
        """Verbindet, meldet sich mit dem Token an und wartet auf 'welcome'."""
        self.close()
        sock = self._open_socket()
        try:
            sock.settimeout(10)
            sock.sendall(protocol.encode(protocol.hello(self.cfg.token, self.app_version)))
            reply = json.loads(self._read_line(sock).decode("utf-8"))
            if reply.get("type") != "welcome":
                raise LinkError(f"Anmeldung abgelehnt: {reply.get('reason', 'unbekannt')}")
            sock.settimeout(15)
        except Exception:
            sock.close()
            raise
        with self._lock:
            self._sock = sock
        log.info("Verbunden mit %s (Pi-Version %s)", self.target, reply.get("server_version", "?"))

    def send(self, message):
        data = protocol.encode(message)
        with self._lock:
            if self._sock is None:
                raise LinkError("Nicht verbunden")
            # Zeitlimit nach Größe: ein Cover darf bei schlechter Funkverbindung länger brauchen,
            # ohne dass die Verbindung abgebrochen wird
            self._sock.settimeout(max(MIN_SEND_TIMEOUT, len(data) / SLOW_BYTES_PER_S))
            start = time.monotonic()
            self._sock.sendall(data)
            elapsed = time.monotonic() - start
        if len(data) > 8192 or elapsed > 2:
            log.debug("%s gesendet: %.1f KB in %.1f s", message.get("type"), len(data) / 1024, elapsed)

    def close(self, say_bye=False):
        with self._lock:
            sock, self._sock = self._sock, None
        if sock is None:
            return
        try:
            if say_bye:
                sock.sendall(protocol.encode(protocol.bye()))
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass
