#!/usr/bin/env bash
# Erzeugt die Installationspakete aus einem Git-Stand (Standard: origin/main):
#   infodisplay-<Version>.zip      komplettes Projekt
#   infodisplay-pi-<Version>.zip   nur für den Raspberry Pi (z. B. Update per USB-Stick)
#   infodisplay-pc-<Version>.zip   nur für den Windows-PC
# Aufruf:  tools/make_packages.sh [Zielordner] [Git-Stand]
set -euo pipefail
OUT="${1:-.}"
REF="${2:-origin/main}"
cd "$(dirname "$0")/.."
VERSION="$(git show "$REF:VERSION" | tr -d '[:space:]')"
mkdir -p "$OUT"

git archive --format=zip --prefix=infodisplay/ -o "$OUT/infodisplay-$VERSION.zip" "$REF"
git archive --format=zip --prefix=infodisplay/ -o "$OUT/infodisplay-pi-$VERSION.zip" "$REF" \
  VERSION CHANGELOG.md README.md pi-display tools/fake_sender.py
git archive --format=zip --prefix=infodisplay/ -o "$OUT/infodisplay-pc-$VERSION.zip" "$REF" \
  VERSION CHANGELOG.md README.md ANLEITUNG-FIRMEN-PC.md windows-sender

ls -l "$OUT"/infodisplay-*"$VERSION".zip
