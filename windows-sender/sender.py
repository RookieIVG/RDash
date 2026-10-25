"""InfoDisplay – Windows-Sender

Liest die laufende Musik (Windows-Medienschnittstelle) und die nächsten
Outlook-Termine und überträgt sie per Bluetooth an den Raspberry Pi.

Start:   pythonw.exe sender.py [--config PFAD]
Test:    python.exe  sender.py --test      (zeigt die Daten nur an)
"""

import argparse
import asyncio
import ctypes
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from includes import protocol
from includes.config import DEFAULT_CONFIG_PATH, load_config
from includes.link_client import LinkClient
from includes.logger import get_logger, setup_logging

APP_DIR = os.path.dirname(os.path.abspath(__file__))
log = get_logger("sender")


def read_version():
    for candidate in (os.path.join(APP_DIR, "VERSION"), os.path.join(APP_DIR, "..", "VERSION")):
        try:
            with open(candidate, encoding="utf-8") as fh:
                return fh.read().strip()
        except OSError:
            continue
    return "0.0.0"


def single_instance():
    """Verhindert, dass der Sender doppelt läuft (benannter Windows-Mutex)."""
    if os.name != "nt":
        return True
    kernel32 = ctypes.windll.kernel32
    single_instance.handle = kernel32.CreateMutexW(None, False, "Local\\InfoDisplaySender")
    return kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


class LinkManager:
    """Hält die Verbindung aufrecht und verschickt Nachrichten der Reihe nach."""

    def __init__(self, client):
        self.client = client
        self.connected = asyncio.Event()
        self.generation = 0          # erhöht sich bei jeder neuen Verbindung
        self._snapshot = {}           # zuletzt gesendete Daten je Typ (für Neuverbindung)
        self._lock = asyncio.Lock()

    async def supervisor(self):
        backoff = 2
        last_error = None
        while True:
            if self.connected.is_set():
                await asyncio.sleep(1)
                continue
            try:
                await asyncio.to_thread(self.client.connect)
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                if message != last_error:
                    log.warning("Keine Verbindung zu %s – %s (nächster Versuch laufend)", self.client.target, message)
                    last_error = message
                else:
                    log.debug("Verbindungsversuch fehlgeschlagen: %s", message)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            backoff, last_error = 2, None
            self.generation += 1
            self.connected.set()
            for key in ("cover", "calendar"):
                if key in self._snapshot:
                    await self.publish(self._snapshot[key])

    async def publish(self, message, remember=None):
        if remember:
            self._snapshot[remember] = message
        if not self.connected.is_set():
            return False
        async with self._lock:
            try:
                await asyncio.to_thread(self.client.send, message)
                return True
            except Exception as exc:
                log.warning("Verbindung unterbrochen: %s", exc)
                self.client.close()
                self.connected.clear()
                return False


def _media_changed(media, last, last_time, resend_interval):
    if last is None:
        return True
    keys = ("active", "status", "title", "artist", "album", "source_app", "duration_ms", "cover_id")
    if any(media.get(k) != last.get(k) for k in keys):
        return True
    elapsed = time.monotonic() - last_time
    expected = last.get("position_ms", 0)
    if media.get("status") == "playing":
        expected += elapsed * 1000
        if elapsed >= resend_interval:
            return True
    return abs(expected - media.get("position_ms", 0)) > 2500  # Spulen erkannt


async def media_loop(cfg, link):
    from includes.media import MediaWatcher
    watcher = MediaWatcher(cfg)
    last, last_time, generation = None, 0.0, -1
    while True:
        try:
            media, cover = await watcher.read()
        except Exception as exc:
            log.warning("Medieninfo nicht lesbar: %s", exc)
            watcher.reset()
            await asyncio.sleep(cfg.poll_interval * 5)
            continue
        if cover:
            await link.publish(protocol.cover(cover["id"], cover["mime"], cover["b64"]), remember="cover")
        if generation != link.generation:   # neue Verbindung -> alles neu senden
            last, generation = None, link.generation
        if _media_changed(media, last, last_time, cfg.resend_interval):
            if await link.publish(protocol.media(media)):
                last, last_time = media, time.monotonic()
                log.debug("Medien gesendet: %s – %s (%s)", media.get("artist"), media.get("title"), media.get("status"))
        await asyncio.sleep(cfg.poll_interval)


def _com_init():
    import pythoncom
    pythoncom.CoInitialize()


async def calendar_loop(cfg, link):
    from includes.calendar_outlook import OutlookCalendar
    calendar = OutlookCalendar(cfg)
    executor = ThreadPoolExecutor(max_workers=1, initializer=_com_init)
    loop = asyncio.get_running_loop()
    while True:
        try:
            events = await loop.run_in_executor(executor, calendar.fetch)
            if events is not None:
                await link.publish(protocol.calendar(events), remember="calendar")
                log.debug("%d Termine gesendet", len(events))
        except Exception as exc:
            log.warning("Kalender nicht lesbar: %s", exc)
        await asyncio.sleep(cfg.refresh_minutes * 60)


async def heartbeat_loop(cfg, link):
    while True:
        await asyncio.sleep(cfg.heartbeat_seconds)
        if link.connected.is_set():
            await link.publish(protocol.ping())


async def run(cfg, version):
    client = LinkClient(cfg, version)
    link = LinkManager(client)
    tasks = [link.supervisor(), heartbeat_loop(cfg, link)]
    if cfg.media_enabled:
        tasks.append(media_loop(cfg, link))
    if cfg.calendar_enabled:
        tasks.append(calendar_loop(cfg, link))
    try:
        await asyncio.gather(*tasks)
    finally:
        client.close(say_bye=True)


async def run_test(cfg):
    """Gibt einmalig aus, was gesendet würde – ohne Verbindung zum Pi."""
    if cfg.media_enabled:
        from includes.media import MediaWatcher
        media, cover = await MediaWatcher(cfg).read()
        if cover:
            cover = {**cover, "b64": f"<{len(cover['b64'])} Zeichen Base64>"}
        print("MEDIEN:", json.dumps(media, ensure_ascii=False, indent=2))
        print("COVER:", json.dumps(cover, ensure_ascii=False))
    if cfg.calendar_enabled:
        from includes.calendar_outlook import OutlookCalendar
        events = await asyncio.get_running_loop().run_in_executor(
            ThreadPoolExecutor(max_workers=1, initializer=_com_init), OutlookCalendar(cfg).fetch)
        print("KALENDER:", json.dumps(events, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="InfoDisplay Windows-Sender")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="Pfad zur config.ini")
    parser.add_argument("--test", action="store_true", help="Daten einmal ausgeben und beenden")
    args = parser.parse_args()

    version = read_version()
    try:
        cfg = load_config(args.config, require_link=not args.test)
    except (OSError, ValueError) as exc:
        setup_logging(None, console=True)
        log.error("Konfiguration fehlerhaft: %s", exc)
        return 2

    setup_logging(cfg.log_file, cfg.log_level, cfg.log_max_bytes, cfg.log_backup_count)
    if args.test:
        asyncio.run(run_test(cfg))
        return 0
    if not single_instance():
        log.error("Der Sender läuft bereits – zweite Instanz wird beendet")
        return 1

    log.info("InfoDisplay-Sender %s startet (Ziel: %s)", version,
             cfg.pi_mac if cfg.transport == "bluetooth" else f"{cfg.tcp_host}:{cfg.tcp_port}")
    try:
        asyncio.run(run(cfg, version))
    except KeyboardInterrupt:
        log.info("Beendet durch Benutzer")
    return 0


if __name__ == "__main__":
    sys.exit(main())
