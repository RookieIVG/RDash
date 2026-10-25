"""Wetter (Open-Meteo) und Schlagzeilen (RSS/Atom) aus dem Internet.

Der Raspberry Pi hat keinen Internetzugang – deshalb holt der PC die Daten
und schickt sie per Bluetooth weiter. Nur Standardbibliothek (urllib, ElementTree).
"""

import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .logger import get_logger

log = get_logger("web")

MAX_BYTES = 2 * 1024 * 1024
USER_AGENT = "InfoDisplay (Raspberry-Pi-Anzeige)"
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"


def _opener(cfg):
    if cfg.proxy:
        handler = urllib.request.ProxyHandler({"http": cfg.proxy, "https": cfg.proxy})
    else:
        handler = urllib.request.ProxyHandler()   # Proxy aus den Windows-Einstellungen
    return urllib.request.build_opener(handler)


def _get(cfg, url):
    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        raise ValueError(f"nur http/https erlaubt: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with _opener(cfg).open(request, timeout=cfg.web_timeout) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError(f"Antwort zu groß: {url}")
    return data


# ---------------------------------------------------------------- Wetter
def fetch_weather(cfg):
    query = urllib.parse.urlencode({
        "latitude": cfg.latitude,
        "longitude": cfg.longitude,
        "current": "temperature_2m,weather_code,is_day",
        "daily": "temperature_2m_max,temperature_2m_min",
        "timezone": "auto",
        "forecast_days": 1,
    })
    data = json.loads(_get(cfg, f"{OPEN_METEO}?{query}").decode("utf-8"))
    current, daily = data.get("current", {}), data.get("daily", {})

    def first(key):
        values = daily.get(key) or [None]
        return values[0]

    return {
        "place": cfg.place,
        "temp": current.get("temperature_2m"),
        "code": current.get("weather_code"),
        "is_day": bool(current.get("is_day", 1)),
        "t_max": first("temperature_2m_max"),
        "t_min": first("temperature_2m_min"),
    }


# ---------------------------------------------------------------- Schlagzeilen
def _local(tag):
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(node, name):
    for child in node:
        if _local(child.tag) == name:
            return "".join(child.itertext()).strip()
    return ""


_TAGS = re.compile(r"<[^>]*>")
MAX_TEXT = 300


def plain_text(value, limit=MAX_TEXT):
    """HTML aus Feed-Beschreibungen entfernen, Leerraum glätten, an Wortgrenze kürzen."""
    # zweimal: Feeds liefern HTML teils roh, teils als &lt;p&gt; maskiert
    text = " ".join(_TAGS.sub(" ", html.unescape(_TAGS.sub(" ", value or ""))).split())
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + " …"
    return text


def parse_feed(data, max_items, with_text=False):
    """Liefert (Quellenname, [{title, text}]) für RSS 2.0, RSS 1.0 (RDF) und Atom."""
    root = ET.fromstring(data)
    source = ""
    entries = []
    for node in root.iter():
        name = _local(node.tag)
        if name in ("channel", "feed") and not source:
            source = _child_text(node, "title")
        elif name in ("item", "entry"):
            title = " ".join(_child_text(node, "title").split())
            if not title:
                continue
            text = ""
            if with_text:   # RSS: description, Atom: summary bzw. content
                text = plain_text(_child_text(node, "description") or _child_text(node, "summary")
                                  or _child_text(node, "content"))
                if text == title:
                    text = ""
            entries.append({"title": title, "text": text})
            if len(entries) >= max_items:
                break
    return source, entries


def fetch_news(cfg):
    """Holt alle Feeds und mischt die Schlagzeilen abwechselnd (neueste zuerst je Feed)."""
    per_feed = []
    for url in cfg.feeds:
        try:
            source, entries = parse_feed(_get(cfg, url), cfg.max_headlines, cfg.news_text)
        except Exception as exc:
            log.warning("Feed nicht lesbar (%s): %s", url, exc)
            continue
        source = source or urllib.parse.urlsplit(url).hostname or ""
        per_feed.append([dict(e, source=source) for e in entries])
    items = []
    while len(items) < cfg.max_headlines and any(per_feed):
        for entries in per_feed:
            if entries and len(items) < cfg.max_headlines:
                items.append(entries.pop(0))
    return items if per_feed else None
