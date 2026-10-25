"""Zentrales Logging für den Pi-Empfänger.

Alle Module holen sich ihren Logger über get_logger(); die Ausgabe landet
gesammelt in einer rotierenden Logdatei (und optional auf der Konsole).
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

LOGGER_NAME = "infodisplay"
_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(log_file, level="INFO", max_bytes=2_000_000, backup_count=5, console=True):
    """Richtet das zentrale Logging ein und liefert den Haupt-Logger zurück."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    logger.handlers.clear()
    logger.propagate = False
    formatter = logging.Formatter(_FORMAT, _DATEFMT)

    file_error = None
    if log_file:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
            fh = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        except OSError as exc:  # z. B. fehlende Schreibrechte
            file_error = exc

    # Konsole nur, wenn eine vorhanden ist (unter systemd landet sie im Journal)
    if console and sys.stdout is not None:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(formatter)
        logger.addHandler(sh)

    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    if file_error:
        logger.warning("Logdatei %s nicht beschreibbar: %s", log_file, file_error)
    return logger


def get_logger(component):
    """Liefert einen Unter-Logger, z. B. infodisplay.media."""
    return logging.getLogger(f"{LOGGER_NAME}.{component}")
