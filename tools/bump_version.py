"""Erhöht die Versionsnummer (Semantic Versioning) und ergänzt CHANGELOG.md automatisch.

Aufruf (im Projektordner):
  python tools/bump_version.py patch "Fehler bei Cover-Anzeige behoben"
  python tools/bump_version.py minor "Wetteranzeige ergänzt" "Neue Option xyz"
  python tools/bump_version.py major "Protokoll v2 (nicht abwärtskompatibel)"

Der Typ des Eintrags wird automatisch gewählt:
  major/minor -> "Hinzugefügt", patch -> "Behoben" (mit --type änderbar)
"""

import argparse
import datetime
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "VERSION"
CHANGELOG = ROOT / "CHANGELOG.md"
SECTIONS = {"added": "Hinzugefügt", "changed": "Geändert", "fixed": "Behoben", "removed": "Entfernt",
            "security": "Sicherheit"}


def bump(version, part):
    major, minor, patch = (int(x) for x in version.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def main():
    parser = argparse.ArgumentParser(description="Version erhöhen und Changelog ergänzen")
    parser.add_argument("part", choices=("major", "minor", "patch"))
    parser.add_argument("entries", nargs="+", help="Änderungen (je Eintrag ein Argument)")
    parser.add_argument("--type", choices=SECTIONS.keys(), help="Art der Änderung")
    args = parser.parse_args()

    old = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", old):
        raise SystemExit(f"VERSION ungültig: {old!r}")
    new = bump(old, args.part)
    section = SECTIONS[args.type or ("fixed" if args.part == "patch" else "added")]

    today = datetime.date.today().isoformat()
    block = f"## [{new}] – {today}\n\n### {section}\n" + "".join(f"- {e}\n" for e in args.entries) + "\n"

    text = CHANGELOG.read_text(encoding="utf-8") if CHANGELOG.exists() else "# Changelog\n\n"
    marker = re.search(r"^## \[", text, flags=re.M)
    text = text[: marker.start()] + block + text[marker.start():] if marker else text.rstrip() + "\n\n" + block

    CHANGELOG.write_text(text, encoding="utf-8")
    VERSION_FILE.write_text(new + "\n", encoding="utf-8")
    print(f"Version {old} -> {new}, CHANGELOG.md ergänzt.")


if __name__ == "__main__":
    main()
