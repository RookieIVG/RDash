"""Konfiguration des Pi-Empfängers.

Die Datei liegt unter /etc/infodisplay/config.ini – also außerhalb des
Web-Roots (/opt/infodisplay/web) und ist nur für root und den Dienst lesbar.
"""

import configparser
import os
from dataclasses import dataclass, field

DEFAULT_CONFIG_PATH = os.environ.get("INFODISPLAY_CONFIG", "/etc/infodisplay/config.ini")

_DEFAULTS = {
    "bluetooth": {
        "enabled": "true",
        "channel": "22",
        "adapter_address": "",
        "allowed_macs": "",
        "token": "",
    },
    "security": {
        "max_line_bytes": "1048576",
        "msg_rate_per_sec": "10",
        "msg_burst": "40",
        "max_violations": "20",
        "auth_timeout": "10",
        "idle_timeout": "120",
        "connect_attempts_per_min": "6",
        "http_rate_per_sec": "20",
        "http_burst": "60",
        "max_sse_clients": "5",
    },
    "web": {
        "host": "127.0.0.1",
        "port": "8080",
        "web_root": "/opt/infodisplay/web",
    },
    "ui": {
        "show_seconds": "true",
        "news_seconds": "12",
        "news_page_seconds": "30",
        "focus": "calendar",
        "saver_speed": "40",
        "layout": "auto",
        "rotation": "0",
    },
    "debug": {
        "tcp_test_port": "0",
        "tcp_test_host": "127.0.0.1",
    },
    "logging": {
        "file": "/var/log/infodisplay/infodisplay.log",
        "level": "INFO",
        "max_bytes": "2000000",
        "backup_count": "5",
    },
}


@dataclass
class ReceiverConfig:
    path: str
    bt_enabled: bool
    channel: int
    adapter_address: str
    allowed_macs: set = field(default_factory=set)
    token: str = ""
    max_line_bytes: int = 1_048_576
    msg_rate_per_sec: float = 10
    msg_burst: float = 40
    max_violations: int = 20
    auth_timeout: float = 10
    idle_timeout: float = 120
    connect_attempts_per_min: float = 6
    http_rate_per_sec: float = 20
    http_burst: float = 60
    max_sse_clients: int = 5
    web_host: str = "127.0.0.1"
    web_port: int = 8080
    web_root: str = "/opt/infodisplay/web"
    ui_show_seconds: bool = True
    ui_news_seconds: int = 12
    ui_news_page_seconds: int = 30
    ui_focus: str = "calendar"
    ui_saver_speed: int = 40
    ui_layout: str = "auto"
    ui_rotation: int = 0
    tcp_test_port: int = 0
    tcp_test_host: str = "127.0.0.1"
    log_file: str = ""
    log_level: str = "INFO"
    log_max_bytes: int = 2_000_000
    log_backup_count: int = 5


def load_config(path=None):
    path = path or DEFAULT_CONFIG_PATH
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Konfigurationsdatei nicht gefunden: {path}")
    cp = configparser.ConfigParser(interpolation=None)
    cp.read_dict(_DEFAULTS)
    cp.read(path, encoding="utf-8-sig")   # auch mit BOM (Editor "UTF-8 mit BOM", PowerShell 5)

    layout = cp.get("ui", "layout").strip().lower()
    focus = cp.get("ui", "focus").strip().lower()
    cfg = ReceiverConfig(
        path=path,
        bt_enabled=cp.getboolean("bluetooth", "enabled"),
        channel=cp.getint("bluetooth", "channel"),
        adapter_address=cp.get("bluetooth", "adapter_address").strip().upper(),
        allowed_macs={m.strip().upper() for m in cp.get("bluetooth", "allowed_macs").split(",") if m.strip()},
        token=cp.get("bluetooth", "token").strip(),
        max_line_bytes=cp.getint("security", "max_line_bytes"),
        msg_rate_per_sec=cp.getfloat("security", "msg_rate_per_sec"),
        msg_burst=cp.getfloat("security", "msg_burst"),
        max_violations=cp.getint("security", "max_violations"),
        auth_timeout=cp.getfloat("security", "auth_timeout"),
        idle_timeout=cp.getfloat("security", "idle_timeout"),
        connect_attempts_per_min=cp.getfloat("security", "connect_attempts_per_min"),
        http_rate_per_sec=cp.getfloat("security", "http_rate_per_sec"),
        http_burst=cp.getfloat("security", "http_burst"),
        max_sse_clients=cp.getint("security", "max_sse_clients"),
        web_host=cp.get("web", "host").strip(),
        web_port=cp.getint("web", "port"),
        web_root=os.path.realpath(cp.get("web", "web_root").strip()),
        ui_show_seconds=cp.getboolean("ui", "show_seconds"),
        ui_news_seconds=max(4, min(120, cp.getint("ui", "news_seconds"))),
        ui_news_page_seconds=max(5, min(600, cp.getint("ui", "news_page_seconds"))),
        ui_focus=focus if focus in ("calendar", "news") else "calendar",
        ui_saver_speed=max(5, min(500, cp.getint("ui", "saver_speed"))),
        ui_layout=layout if layout in ("auto", "landscape", "portrait") else "auto",
        ui_rotation=cp.getint("ui", "rotation"),
        tcp_test_port=cp.getint("debug", "tcp_test_port"),
        tcp_test_host=cp.get("debug", "tcp_test_host").strip(),
        log_file=cp.get("logging", "file").strip(),
        log_level=cp.get("logging", "level"),
        log_max_bytes=cp.getint("logging", "max_bytes"),
        log_backup_count=cp.getint("logging", "backup_count"),
    )

    if not cfg.token or cfg.token.upper().startswith("CHANGE") or len(cfg.token) < 16:
        raise ValueError("bluetooth.token fehlt oder ist zu kurz (mind. 16 Zeichen)")
    if not 1 <= cfg.channel <= 30:
        raise ValueError("bluetooth.channel muss zwischen 1 und 30 liegen")
    if cfg.ui_rotation not in (0, 90, 180, 270):
        raise ValueError("ui.rotation muss 0, 90, 180 oder 270 sein")
    if not os.path.isdir(cfg.web_root):
        raise ValueError(f"web.web_root existiert nicht: {cfg.web_root}")
    return cfg
