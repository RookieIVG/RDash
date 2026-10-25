"""InfoDisplay – Empfänger auf dem Raspberry Pi

Nimmt Daten vom Windows-Sender per Bluetooth (RFCOMM) entgegen und stellt
sie über einen lokalen Webserver für den Kiosk-Browser bereit.

Start:  python3 receiver.py [--config /etc/infodisplay/config.ini]
"""

import argparse
import os
import signal
import sys
import threading

from includes.config import DEFAULT_CONFIG_PATH, load_config
from includes.link_server import LinkServer
from includes.logger import get_logger, setup_logging
from includes.state import DisplayState
from includes.web_server import InfoHTTPServer

APP_DIR = os.path.dirname(os.path.abspath(__file__))
log = get_logger("receiver")


def read_version():
    for candidate in (os.path.join(APP_DIR, "VERSION"), os.path.join(APP_DIR, "..", "VERSION")):
        try:
            with open(candidate, encoding="utf-8") as fh:
                return fh.read().strip()
        except OSError:
            continue
    return "0.0.0"


def main():
    parser = argparse.ArgumentParser(description="InfoDisplay Pi-Empfänger")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="Pfad zur config.ini")
    args = parser.parse_args()

    version = read_version()
    try:
        cfg = load_config(args.config)
    except (OSError, ValueError) as exc:
        setup_logging(None)
        log.error("Konfiguration fehlerhaft: %s", exc)
        return 2

    setup_logging(cfg.log_file, cfg.log_level, cfg.log_max_bytes, cfg.log_backup_count)
    log.info("InfoDisplay-Empfänger %s startet", version)

    state = DisplayState(
        app_info={"name": "InfoDisplay", "version": version},
        ui={"show_seconds": cfg.ui_show_seconds, "layout": cfg.ui_layout, "rotation": cfg.ui_rotation,
            "news_seconds": cfg.ui_news_seconds, "news_page_seconds": cfg.ui_news_page_seconds,
            "focus": cfg.ui_focus},
    )

    try:
        httpd = InfoHTTPServer(cfg, state)
    except OSError as exc:
        log.error("Webserver konnte nicht auf %s:%d starten: %s", cfg.web_host, cfg.web_port, exc)
        return 1
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    log.info("Anzeige erreichbar unter http://%s:%d/", cfg.web_host, cfg.web_port)

    link = LinkServer(cfg, state, version)
    link.start()

    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    stop.wait()

    log.info("Beende …")
    link.stop()
    httpd.shutdown()
    httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
