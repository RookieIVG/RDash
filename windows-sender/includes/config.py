"""Konfiguration des Windows-Senders.

Die Konfiguration liegt bewusst NICHT im Programmordner, sondern unter
%APPDATA%\\InfoDisplay\\config.ini – dort steht auch der geheime Token.
"""

import configparser
import os
from dataclasses import dataclass, field

DEFAULT_CONFIG_PATH = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "InfoDisplay", "config.ini")

_DEFAULTS = {
    "link": {
        "transport": "bluetooth",       # bluetooth | tcp (tcp nur zum Testen)
        "pi_mac": "",
        "channel": "22",
        "tcp_host": "127.0.0.1",
        "tcp_port": "5099",
        "token": "",
        "connect_timeout": "15",
        "heartbeat_seconds": "20",
    },
    "media": {
        "enabled": "true",
        "poll_interval": "1.0",
        "resend_interval": "10",
        "preferred_apps": "",
        "send_cover": "true",
        "cover_max_px": "400",
    },
    "calendar": {
        "enabled": "true",
        "start_outlook": "false",
        "refresh_minutes": "5",
        "days_ahead": "1",
        "max_events": "10",
        "hide_subjects": "false",
        "hide_private": "true",
        "restrict_date_format": "%d.%m.%Y %H:%M",
    },
    "weather": {
        "enabled": "false",
        "place": "Graz",
        "latitude": "47.07",
        "longitude": "15.44",
        "refresh_minutes": "15",
    },
    "news": {
        "enabled": "false",
        "feeds": "https://rss.orf.at/news.xml",
        "max_headlines": "10",
        "with_text": "true",
        "refresh_minutes": "15",
    },
    "internet": {
        "proxy": "",
        "timeout": "15",
    },
    "logging": {
        "file": r"%LOCALAPPDATA%\InfoDisplay\logs\sender.log",
        "level": "INFO",
        "max_bytes": "2000000",
        "backup_count": "5",
    },
}


@dataclass
class SenderConfig:
    path: str
    transport: str
    pi_mac: str
    channel: int
    tcp_host: str
    tcp_port: int
    token: str
    connect_timeout: float
    heartbeat_seconds: float
    media_enabled: bool
    poll_interval: float
    resend_interval: float
    preferred_apps: list = field(default_factory=list)
    send_cover: bool = True
    cover_max_px: int = 400
    calendar_enabled: bool = True
    start_outlook: bool = False
    refresh_minutes: float = 5
    days_ahead: int = 1
    max_events: int = 10
    hide_subjects: bool = False
    hide_private: bool = True
    restrict_date_format: str = "%d.%m.%Y %H:%M"
    weather_enabled: bool = False
    place: str = "Graz"
    latitude: float = 47.07
    longitude: float = 15.44
    weather_refresh_minutes: float = 15
    news_enabled: bool = False
    feeds: list = field(default_factory=list)
    max_headlines: int = 10
    news_text: bool = True
    news_refresh_minutes: float = 15
    proxy: str = ""
    web_timeout: float = 15
    log_file: str = ""
    log_level: str = "INFO"
    log_max_bytes: int = 2_000_000
    log_backup_count: int = 5


def _split_list(value):
    return [v.strip().lower() for v in value.split(",") if v.strip()]


def load_config(path=None, require_link=True):
    """Liest die INI-Datei und prüft die Pflichtwerte (Verbindungsdaten nur bei require_link)."""
    path = path or DEFAULT_CONFIG_PATH
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Konfigurationsdatei nicht gefunden: {path}")

    cp = configparser.ConfigParser(interpolation=None)
    cp.read_dict(_DEFAULTS)
    cp.read(path, encoding="utf-8")

    cfg = SenderConfig(
        path=path,
        transport=cp.get("link", "transport").strip().lower(),
        pi_mac=cp.get("link", "pi_mac").strip().upper(),
        channel=cp.getint("link", "channel"),
        tcp_host=cp.get("link", "tcp_host").strip(),
        tcp_port=cp.getint("link", "tcp_port"),
        token=cp.get("link", "token").strip(),
        connect_timeout=cp.getfloat("link", "connect_timeout"),
        heartbeat_seconds=max(5.0, cp.getfloat("link", "heartbeat_seconds")),
        media_enabled=cp.getboolean("media", "enabled"),
        poll_interval=max(0.25, cp.getfloat("media", "poll_interval")),
        resend_interval=max(2.0, cp.getfloat("media", "resend_interval")),
        preferred_apps=_split_list(cp.get("media", "preferred_apps")),
        send_cover=cp.getboolean("media", "send_cover"),
        cover_max_px=max(64, min(1024, cp.getint("media", "cover_max_px"))),
        calendar_enabled=cp.getboolean("calendar", "enabled"),
        start_outlook=cp.getboolean("calendar", "start_outlook"),
        refresh_minutes=max(1.0, cp.getfloat("calendar", "refresh_minutes")),
        days_ahead=max(0, min(14, cp.getint("calendar", "days_ahead"))),
        max_events=max(1, min(50, cp.getint("calendar", "max_events"))),
        hide_subjects=cp.getboolean("calendar", "hide_subjects"),
        hide_private=cp.getboolean("calendar", "hide_private"),
        restrict_date_format=cp.get("calendar", "restrict_date_format"),
        weather_enabled=cp.getboolean("weather", "enabled"),
        place=cp.get("weather", "place").strip()[:40],
        latitude=cp.getfloat("weather", "latitude"),
        longitude=cp.getfloat("weather", "longitude"),
        weather_refresh_minutes=max(5.0, cp.getfloat("weather", "refresh_minutes")),
        news_enabled=cp.getboolean("news", "enabled"),
        feeds=[u.strip() for u in cp.get("news", "feeds").replace("\n", ",").split(",") if u.strip()],
        max_headlines=max(1, min(30, cp.getint("news", "max_headlines"))),
        news_text=cp.getboolean("news", "with_text"),
        news_refresh_minutes=max(5.0, cp.getfloat("news", "refresh_minutes")),
        proxy=cp.get("internet", "proxy").strip(),
        web_timeout=max(3.0, cp.getfloat("internet", "timeout")),
        log_file=os.path.expandvars(cp.get("logging", "file")),
        log_level=cp.get("logging", "level"),
        log_max_bytes=cp.getint("logging", "max_bytes"),
        log_backup_count=cp.getint("logging", "backup_count"),
    )

    if not (-90 <= cfg.latitude <= 90 and -180 <= cfg.longitude <= 180):
        raise ValueError("weather.latitude/longitude ungültig")
    if not require_link:
        return cfg
    if cfg.transport not in ("bluetooth", "tcp"):
        raise ValueError("link.transport muss 'bluetooth' oder 'tcp' sein")
    if not cfg.token or cfg.token.upper().startswith("CHANGE"):
        raise ValueError("link.token ist nicht gesetzt (Token vom Raspberry Pi eintragen)")
    if cfg.transport == "bluetooth":
        parts = cfg.pi_mac.split(":")
        if len(parts) != 6 or not all(len(p) == 2 for p in parts):
            raise ValueError("link.pi_mac ist ungültig (Format AA:BB:CC:DD:EE:FF)")
        if not 1 <= cfg.channel <= 30:
            raise ValueError("link.channel muss zwischen 1 und 30 liegen")
    return cfg
