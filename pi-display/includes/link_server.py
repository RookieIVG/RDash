"""Bluetooth-RFCOMM-Server (plus optionaler TCP-Testzugang).

Ablauf pro Verbindung:
  1. Prüfung Adress-Allowlist und Verbindungs-Rate-Limit
  2. erste Zeile muss 'hello' mit gültigem Token sein  -> 'welcome'
  3. danach Daten (media, cover, calendar, ping, bye) mit Rate-Limit
Es ist immer nur ein Sender aktiv; ein neuer ersetzt den alten.
"""

import hmac
import socket
import threading

from . import protocol
from .logger import get_logger
from .ratelimit import KeyedRateLimiter, TokenBucket

log = get_logger("link")


class LineTooLong(Exception):
    pass


class LineReader:
    def __init__(self, conn, max_bytes):
        self.conn = conn
        self.max_bytes = max_bytes
        self.buffer = b""

    def readline(self):
        """Liefert die nächste Zeile (ohne '\\n') oder None bei Verbindungsende."""
        while b"\n" not in self.buffer:
            if len(self.buffer) > self.max_bytes:
                raise LineTooLong()
            chunk = self.conn.recv(65536)
            if not chunk:
                return None
            self.buffer += chunk
        line, self.buffer = self.buffer.split(b"\n", 1)
        if len(line) > self.max_bytes:
            raise LineTooLong()
        return line


class LinkServer:
    def __init__(self, cfg, state, app_version):
        self.cfg = cfg
        self.state = state
        self.app_version = app_version
        self._stop = threading.Event()
        self._active = None
        self._active_lock = threading.Lock()
        self._conn_limiter = KeyedRateLimiter(cfg.connect_attempts_per_min / 60.0, cfg.connect_attempts_per_min)
        self._threads = []

    # ------------------------------------------------------------ Start/Stopp
    def start(self):
        if self.cfg.bt_enabled:
            self._spawn(self._serve, self._make_rfcomm_socket, "bluetooth")
        if self.cfg.tcp_test_port:
            log.warning("TCP-Testzugang aktiv auf %s:%d – im Produktivbetrieb deaktivieren!",
                        self.cfg.tcp_test_host, self.cfg.tcp_test_port)
            self._spawn(self._serve, self._make_tcp_socket, "tcp")

    def stop(self):
        self._stop.set()
        with self._active_lock:
            if self._active is not None:
                self._close(self._active)

    def _spawn(self, target, *args):
        thread = threading.Thread(target=target, args=args, daemon=True)
        thread.start()
        self._threads.append(thread)

    def _make_rfcomm_socket(self):
        if not hasattr(socket, "AF_BLUETOOTH"):
            raise OSError("Python ohne Bluetooth-Unterstützung (AF_BLUETOOTH fehlt)")
        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        sock.bind((self.cfg.adapter_address or socket.BDADDR_ANY, self.cfg.channel))
        return sock

    def _make_tcp_socket(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.cfg.tcp_test_host, self.cfg.tcp_test_port))
        return sock

    def _serve(self, factory, label):
        while not self._stop.is_set():
            try:
                server = factory()
                server.listen(2)
                server.settimeout(1.0)
            except OSError as exc:
                log.error("%s-Server konnte nicht starten: %s – neuer Versuch in 10 s", label, exc)
                self._stop.wait(10)
                continue
            log.info("%s-Server wartet auf Verbindungen (%s)", label,
                     f"Kanal {self.cfg.channel}" if label == "bluetooth"
                     else f"{self.cfg.tcp_test_host}:{self.cfg.tcp_test_port}")
            try:
                while not self._stop.is_set():
                    try:
                        conn, addr = server.accept()
                    except socket.timeout:
                        continue
                    self._spawn(self._handle_client, conn, addr, label)
            except OSError as exc:
                log.error("%s-Server Fehler: %s – Neustart", label, exc)
                self._stop.wait(3)
            finally:
                self._close(server)

    # ------------------------------------------------------------ Verbindung
    @staticmethod
    def _close(sock):
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass

    @staticmethod
    def _send(conn, message):
        try:
            conn.sendall(protocol.encode(message))
        except OSError:
            pass

    def _authenticate(self, conn, reader, peer):
        conn.settimeout(self.cfg.auth_timeout)
        line = reader.readline()
        if line is None:
            return None
        hello = protocol.decode(line)
        if hello.get("type") != "hello":
            raise protocol.ProtocolError("erste Nachricht ist kein hello")
        if hello.get("v") != protocol.PROTOCOL_VERSION:
            self._send(conn, {"type": "error", "reason": "protocol_version"})
            raise protocol.ProtocolError(f"Protokollversion {hello.get('v')} nicht unterstützt")
        token = hello.get("token")
        if not isinstance(token, str) or not hmac.compare_digest(token.encode(), self.cfg.token.encode()):
            self._send(conn, {"type": "error", "reason": "auth"})
            log.warning("Anmeldung mit falschem Token von %s abgelehnt", peer)
            return None
        return protocol.clean_text(hello.get("client"), 60) or peer

    def _handle_client(self, conn, addr, label):
        peer = str(addr[0]) if isinstance(addr, tuple) else str(addr)
        if label == "bluetooth" and self.cfg.allowed_macs and peer.upper() not in self.cfg.allowed_macs:
            log.warning("Verbindung von nicht freigegebenem Gerät %s abgelehnt", peer)
            self._close(conn)
            return
        if not self._conn_limiter.allow(peer):
            log.warning("Zu viele Verbindungsversuche von %s – abgelehnt", peer)
            self._close(conn)
            return

        reader = LineReader(conn, self.cfg.max_line_bytes)
        try:
            client = self._authenticate(conn, reader, peer)
        except (OSError, protocol.ProtocolError, LineTooLong) as exc:
            log.warning("Anmeldung von %s fehlgeschlagen: %s", peer, exc or type(exc).__name__)
            client = None
        if client is None:
            self._close(conn)
            return

        self._send(conn, {"type": "welcome", "v": protocol.PROTOCOL_VERSION, "server_version": self.app_version})
        with self._active_lock:
            previous, self._active = self._active, conn
        if previous is not None:
            log.info("Neuer Sender ersetzt bestehende Verbindung")
            self._close(previous)
        log.info("Sender '%s' verbunden über %s (%s)", client, label, peer)
        self.state.set_link(True, client=client, address=peer)

        try:
            self._receive_loop(conn, reader, peer)
        finally:
            self._close(conn)
            with self._active_lock:
                still_active = self._active is conn
                if still_active:
                    self._active = None
            if still_active:
                self.state.set_link(False)
                log.info("Sender '%s' getrennt", client)

    def _receive_loop(self, conn, reader, peer):
        conn.settimeout(self.cfg.idle_timeout)
        bucket = TokenBucket(self.cfg.msg_rate_per_sec, self.cfg.msg_burst)
        violations = 0
        while not self._stop.is_set():
            try:
                line = reader.readline()
            except socket.timeout:
                log.warning("Keine Daten von %s seit %d s – Verbindung wird getrennt", peer, self.cfg.idle_timeout)
                return
            except LineTooLong:
                log.warning("Nachricht von %s zu groß – Verbindung wird getrennt", peer)
                return
            except OSError as exc:
                log.info("Verbindung zu %s beendet: %s", peer, exc)
                return
            if line is None:
                return
            if not line.strip():
                continue
            if not bucket.allow():
                violations += 1
                if violations == 1 or violations % 10 == 0:
                    log.warning("Rate-Limit überschritten von %s (%d)", peer, violations)
                if violations > self.cfg.max_violations:
                    log.warning("Zu viele Verstöße von %s – Verbindung wird getrennt", peer)
                    return
                continue
            try:
                if not self._dispatch(protocol.decode(line)):
                    return
            except protocol.ProtocolError as exc:
                violations += 1
                log.warning("Ungültige Nachricht von %s: %s", peer, exc)
                if violations > self.cfg.max_violations:
                    return

    def _dispatch(self, message):
        """Verarbeitet eine Nachricht. False = Verbindung beenden."""
        kind = message["type"]
        if kind == "media":
            self.state.set_media(protocol.parse_media(message.get("data")))
        elif kind == "cover":
            self.state.set_cover(*protocol.parse_cover(message.get("data")))
        elif kind == "calendar":
            events = protocol.parse_calendar(message.get("data"))
            self.state.set_calendar(events)
            log.debug("%d Termine empfangen", len(events))
        elif kind == "weather":
            self.state.set_weather(protocol.parse_weather(message.get("data")))
        elif kind == "news":
            items = protocol.parse_news(message.get("data"))
            self.state.set_news(items)
            log.debug("%d Schlagzeilen empfangen", len(items))
        elif kind == "ping":
            self.state.touch()
        elif kind == "bye":
            log.info("Sender meldet sich ab")
            return False
        else:
            raise protocol.ProtocolError(f"unbekannter Nachrichtentyp '{protocol.clean_text(kind, 30)}'")
        return True
