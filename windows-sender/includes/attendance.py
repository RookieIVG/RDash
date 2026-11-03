"""Anwesenheitsstatus ausgewählter Personen aus dem SAP-OData-Dienst (Zeiterfassung).

Der PC fragt den Dienst im Firmennetz ab (der Raspberry Pi hat keinen Netzzugang) und schickt nur
Anzeigename, Status, Kategorie und ggf. „bis“-Datum der eingestellten Personen per Bluetooth weiter.

Anmeldung ([attendance] auth):
  cert  – Benutzerzertifikat aus dem Windows-Zertifikatsspeicher (wie der Browser). Abruf über WinHTTP,
          der private Schlüssel bleibt im Speicher (kein Export, kein Passwort in der Config)
  sso   – Windows-Anmeldung (Kerberos/NTLM über SSPI)
  basic – Benutzer/Passwort aus der Config (%APPDATA%, nur für den eigenen Benutzer lesbar)
  none  – ohne Anmeldung
"""

import base64
import http.client
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from .logger import get_logger
from .web_feeds import USER_AGENT, _ssl_context

log = get_logger("attendance")

MAX_BYTES = 4 * 1024 * 1024
PERNR = re.compile(r"^\d{1,8}$")
CATEGORIES = ("anwesend", "telearbeit", "nicht_anwesend", "ganztaegig")
LABELS = {"anwesend": "Anwesend", "telearbeit": "Telearbeit",
          "nicht_anwesend": "Nicht anwesend", "ganztaegig": "Ganztägig abwesend"}

# Statustext enthält … -> Kategorie (erste passende Regel gewinnt; eigene Regeln in [attendance_status]).
# SAP liefert z. B. "anwesend", "nicht anwesend", "Telearbeit", "ganzt. abw.".
# "anwesend" selbst steht nicht in der Liste, weil auch "nicht anwesend" es enthält – dafür gibt es das Feld Anwesend.
DEFAULT_RULES = [
    ("telearbeit", "telearbeit"), ("tele", "telearbeit"), ("home", "telearbeit"), ("mobil", "telearbeit"),
    ("ganzt", "ganztaegig"), ("urlaub", "ganztaegig"), ("krank", "ganztaegig"), ("dienstreise", "ganztaegig"),
    ("nicht anwesend", "nicht_anwesend"), ("abwesend", "nicht_anwesend"),
]

# WinHTTP-Fehlercodes -> verständliche Meldung
WINHTTP_ERRORS = {
    12002: "Zeitüberschreitung",
    12007: "Servername nicht gefunden (Firmennetz/VPN?)",
    12029: "Keine Verbindung zum Server",
    12030: "Verbindung abgebrochen",
    12044: "Server verlangt ein Benutzerzertifikat – [attendance] cert prüfen",
    12175: "Zertifikatsfehler (Server- oder Benutzerzertifikat)",
    12185: "Kein passendes Benutzerzertifikat gefunden – [attendance] cert prüfen",
}


class AttendanceError(Exception):
    """Abruf fehlgeschlagen (Anmeldung, Netz, Antwort)."""


# ---------------------------------------------------------------- Abruf: Zertifikat über WinHTTP
def _request_winhttp(cfg, url):
    try:
        import pythoncom
        import pywintypes
        import win32com.client
    except ImportError as exc:
        raise AttendanceError("Anmeldung 'cert' geht nur unter Windows (pywin32 fehlt)") from exc
    pythoncom.CoInitialize()     # läuft in einem Hilfsthread
    try:
        req = win32com.client.Dispatch("WinHttp.WinHttpRequest.5.1")
        timeout_ms = int(cfg.web_timeout * 1000)
        req.SetTimeouts(timeout_ms, timeout_ms, timeout_ms, timeout_ms)
        req.Open("GET", url, False)
        # Zertifikat aus dem Speicher des angemeldeten Benutzers, gesucht über einen Teil des Inhabers (Subject)
        req.SetClientCertificate("CURRENT_USER\\MY\\" + cfg.att_cert)
        req.SetRequestHeader("Accept", "application/json")
        req.SetRequestHeader("User-Agent", USER_AGENT)
        try:
            req.Send()
        except pywintypes.com_error as exc:
            scode = (exc.excepinfo[5] if exc.excepinfo else exc.hresult) or 0
            code = scode & 0xFFFF
            raise AttendanceError(WINHTTP_ERRORS.get(code, f"WinHTTP-Fehler {code}")) from None
        status = int(req.Status)
        body = bytes(req.ResponseBody) if status == 200 else b""
        return status, body, req.GetResponseHeader("Content-Type") if status == 200 else ""
    finally:
        pythoncom.CoUninitialize()


# ---------------------------------------------------------------- Abruf: SSO / Basic / ohne
def _negotiate_token(ctx, challenge=None):
    _err, out = ctx.authorize(challenge)
    return "Negotiate " + base64.b64encode(out[0].Buffer).decode("ascii")


def _request_http(cfg, url):
    """GET mit SSO/Basic/ohne Anmeldung. Eine Verbindung für beide Schritte (NTLM braucht das)."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme == "https":
        conn = http.client.HTTPSConnection(parts.hostname, parts.port or 443, timeout=cfg.web_timeout,
                                           context=_ssl_context(cfg))
    else:
        conn = http.client.HTTPConnection(parts.hostname, parts.port or 80, timeout=cfg.web_timeout)
    path = parts.path + ("?" + parts.query if parts.query else "")
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    sso = None
    if cfg.att_auth == "basic":
        pair = f"{cfg.att_user}:{cfg.att_password}".encode("utf-8")
        headers["Authorization"] = "Basic " + base64.b64encode(pair).decode("ascii")
    elif cfg.att_auth == "sso":
        try:
            import sspi  # pywin32 – nur unter Windows
        except ImportError as exc:
            raise AttendanceError("Anmeldung 'sso' geht nur unter Windows (pywin32/sspi fehlt)") from exc
        sso = sspi.ClientAuth("Negotiate", targetspn=f"HTTP/{parts.hostname}")
        headers["Authorization"] = _negotiate_token(sso)
    try:
        conn.request("GET", path, headers=headers)
        resp = conn.getresponse()
        body = resp.read(MAX_BYTES + 1)
        challenge = resp.getheader("WWW-Authenticate", "") or ""
        if resp.status == 401 and sso is not None and challenge.startswith("Negotiate "):
            headers["Authorization"] = _negotiate_token(sso, base64.b64decode(challenge.split(" ", 1)[1]))
            conn.request("GET", path, headers=headers)
            resp = conn.getresponse()
            body = resp.read(MAX_BYTES + 1)
    except OSError as exc:
        raise AttendanceError(f"Keine Verbindung: {exc}") from None
    finally:
        conn.close()
    return resp.status, body, resp.getheader("Content-Type", "") or ""


def _request(cfg, url):
    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        raise AttendanceError(f"nur http/https erlaubt: {url}")
    status, body, content_type = (_request_winhttp if cfg.att_auth == "cert" else _request_http)(cfg, url)
    if status == 401:
        raise AttendanceError("Anmeldung abgelehnt (401) – [attendance] auth/cert prüfen")
    if status == 403:
        raise AttendanceError("Keine Berechtigung (403)")
    if status == 404:
        raise AttendanceError("Nicht gefunden (404) – service_url bzw. Personalnummer prüfen")
    if status != 200:
        raise AttendanceError(f"Antwort {status}")
    if len(body) > MAX_BYTES:
        raise AttendanceError("Antwort zu groß")
    return body, content_type


# ---------------------------------------------------------------- Auswertung
def _parse_date(value):
    """OData-Datum ("/Date(1730764800000)/" bzw. "2026-11-05T00:00:00") -> "YYYY-MM-DD" oder ""."""
    if not value:
        return ""
    value = str(value)
    match = re.match(r"^/Date\((-?\d+)", value)
    if match:
        return datetime.fromtimestamp(int(match.group(1)) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", value)
    return match.group(1) if match else ""


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def parse_entries(body, content_type=""):
    """Alle AttendanceStatus-Einträge als Liste von dicts – JSON (d.results / d) oder Atom (feed / entry)."""
    text = body.decode("utf-8", "replace").lstrip()
    if "json" in content_type or text.startswith("{"):
        data = json.loads(text)
        data = data.get("d", data)
        rows = data.get("results", [data]) if isinstance(data, dict) else data
        return [{k: ("" if v is None else str(v)) for k, v in row.items() if not isinstance(v, (dict, list))}
                for row in rows if isinstance(row, dict)]
    root = ET.fromstring(body)
    return [{_local(c.tag): (c.text or "").strip() for c in props}
            for props in root.iter() if _local(props.tag) == "properties"]


def classify(status, anwesend, rules):
    lower = status.lower()
    for fragment, category in rules:
        if fragment in lower:
            return category
    return "anwesend" if str(anwesend).strip() in ("1", "X", "true", "True") else "nicht_anwesend"


def display_name(fields, override, name_format="vorname_nachname"):
    """SAP liefert "Nachname Vorname, Titel" (teils abgeschnitten)."""
    if override:
        return override
    full = (fields.get("Ename") or fields.get("Pernr") or "").split(",")[0].strip()
    parts = full.split()
    if name_format == "sap" or len(parts) < 2:
        return full
    if name_format == "vorname":
        return " ".join(parts[1:])
    return " ".join(parts[1:] + parts[:1])          # vorname_nachname


def build_item(fields, cfg, pernr):
    status = (fields.get("Status") or "").strip()
    category = classify(status, fields.get("Anwesend", ""), cfg.att_rules)
    return {
        "name": display_name(fields, cfg.att_names.get(pernr), cfg.att_name_format),
        "status": LABELS[category],
        "category": category,
        "until": _parse_date(fields.get("Endda")),
    }


def _url(cfg, path):
    query = {"$format": "json"}
    if cfg.att_sap_client:
        query["sap-client"] = cfg.att_sap_client
    return f"{cfg.att_service_url.rstrip('/')}/{path}?" + urllib.parse.urlencode(query)


def fetch_attendance(cfg):
    """Liste für die Anzeige in der eingestellten Reihenfolge – oder None, wenn der Abruf scheiterte."""
    wanted = []
    for pernr in cfg.att_persons:
        if PERNR.match(pernr):
            wanted.append(pernr.zfill(8))
        else:
            log.warning("Ungültige Personalnummer in [attendance] persons: %r", pernr)
    if not wanted:
        return None
    # Ein Abruf für alle: AttendanceStatusSet liefert das ganze Team
    try:
        rows = {r.get("Pernr", "").zfill(8): r for r in parse_entries(*_request(cfg, _url(cfg, "AttendanceStatusSet")))}
    except Exception as exc:
        log.warning("Anwesenheit nicht abrufbar: %s", exc)
        return None
    items = []
    for pernr in wanted:
        fields = rows.get(pernr)
        if fields is None:      # nicht in der Liste -> einzeln nachfragen
            try:
                found = parse_entries(*_request(cfg, _url(cfg, f"AttendanceStatusSet('{pernr}')")))
                fields = found[0] if found else None
            except Exception as exc:
                log.warning("Personalnummer %s nicht gefunden: %s", pernr, exc)
        if fields is not None:
            items.append(build_item(fields, cfg, pernr))
    return items
