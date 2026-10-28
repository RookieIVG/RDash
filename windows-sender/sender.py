"""InfoDisplay – Windows-Sender

Liest die laufende Musik (Windows-Medienschnittstelle), die nächsten
Outlook-Termine sowie optional Wetter und Schlagzeilen (Internet) und
überträgt alles per Bluetooth an den Raspberry Pi.

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


COVER_CHUNK_CHARS = 4096     # Base64-Zeichen pro Cover-Stück (über Bluetooth je nach Strecke 0,05–2 s)


class CoverSender:
    """Überträgt das Cover in Stücken (cover_chunk).

    Zwischen den Stücken kommen andere Nachrichten durch – ein neuer Titel muss nicht warten, bis
    ein großes Cover über eine langsame Bluetooth-Strecke übertragen ist. Kommt währenddessen ein
    neues Cover, wird das alte abgebrochen.
    """

    def __init__(self, link):
        self.link = link
        self.current = None
        self._wake = asyncio.Event()

    def offer(self, cover):
        self.current = cover
        self._wake.set()

    def resend(self):
        """Nach einer Neuverbindung das aktuelle Cover noch einmal schicken."""
        if self.current:
            self._wake.set()

    async def run(self):
        while True:
            await self._wake.wait()
            self._wake.clear()
            cover = self.current
            if not cover:
                continue
            b64 = cover["b64"]
            parts = [b64[i:i + COVER_CHUNK_CHARS] for i in range(0, len(b64), COVER_CHUNK_CHARS)] or [""]
            start = time.monotonic()
            for index, part in enumerate(parts):
                if self.current is not cover:
                    log.debug("Cover %s überholt – Übertragung abgebrochen", cover["id"])
                    break
                if not await self.link.publish(protocol.cover_chunk(cover["id"], cover["mime"], index, len(parts), part)):
                    break               # nicht verbunden – nach der Neuverbindung kommt resend()
                await asyncio.sleep(0)  # anderen Nachrichten (Titel, Ping) den Vortritt lassen
            else:
                log.debug("Cover gesendet: %.1f KB in %.1f s", len(b64) / 1024, time.monotonic() - start)


class LinkManager:
    """Hält die Verbindung aufrecht und verschickt Nachrichten der Reihe nach."""

    def __init__(self, client):
        self.client = client
        self.connected = asyncio.Event()
        self.generation = 0          # erhöht sich bei jeder neuen Verbindung
        self._snapshot = {}           # zuletzt gesendete Daten je Typ (für Neuverbindung)
        self._lock = asyncio.Lock()
        self.covers = CoverSender(self)

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
            self.covers.resend()
            for key in ("calendar", "weather", "news"):
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
        if generation != link.generation:   # neue Verbindung -> alles neu senden
            last, generation = None, link.generation
        # Erst Titel/Interpret (klein, sofort sichtbar), danach das Cover – stückweise im Hintergrund
        # (CoverSender), damit der Text beim Liedwechsel nie auf das Bild warten muss.
        if _media_changed(media, last, last_time, cfg.resend_interval):
            if await link.publish(protocol.media(media)):
                last, last_time = media, time.monotonic()
                log.debug("Medien gesendet: %s – %s (%s)", media.get("artist"), media.get("title"), media.get("status"))
        if cover:
            link.covers.offer(cover)
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


async def weather_loop(cfg, link):
    from includes.web_feeds import fetch_weather
    while True:
        try:
            data = await asyncio.to_thread(fetch_weather, cfg)
            await link.publish(protocol.weather(data), remember="weather")
            log.debug("Wetter gesendet: %s °C, Code %s", data.get("temp"), data.get("code"))
        except Exception as exc:
            log.warning("Wetter nicht abrufbar: %s", exc)
        await asyncio.sleep(cfg.weather_refresh_minutes * 60)


async def news_loop(cfg, link):
    from includes.web_feeds import fetch_news
    while True:
        try:
            items = await asyncio.to_thread(fetch_news, cfg)
            if items is not None:
                await link.publish(protocol.news(items), remember="news")
                log.debug("%d Schlagzeilen gesendet", len(items))
        except Exception as exc:
            log.warning("Schlagzeilen nicht abrufbar: %s", exc)
        await asyncio.sleep(cfg.news_refresh_minutes * 60)


async def heartbeat_loop(cfg, link):
    while True:
        await asyncio.sleep(cfg.heartbeat_seconds)
        if link.connected.is_set():
            await link.publish(protocol.ping())


async def run(cfg, version):
    client = LinkClient(cfg, version)
    link = LinkManager(client)
    tasks = [link.supervisor(), link.covers.run(), heartbeat_loop(cfg, link)]
    if cfg.media_enabled:
        tasks.append(media_loop(cfg, link))
    if cfg.calendar_enabled:
        tasks.append(calendar_loop(cfg, link))
    if cfg.weather_enabled:
        tasks.append(weather_loop(cfg, link))
    if cfg.news_enabled and cfg.feeds:
        tasks.append(news_loop(cfg, link))
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
    if cfg.weather_enabled:
        from includes.web_feeds import fetch_weather
        print("WETTER:", json.dumps(fetch_weather(cfg), ensure_ascii=False, indent=2))
    if cfg.news_enabled:
        from includes.web_feeds import fetch_news
        print("SCHLAGZEILEN:", json.dumps(fetch_news(cfg), ensure_ascii=False, indent=2))


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
