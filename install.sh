#!/usr/bin/env bash
# VB OCR - installation for macOS / Linux (for development and testing)
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
"$PY" -c 'import sys; assert (3,9) <= sys.version_info[:2] <= (3,13), "Python 3.9-3.13 required"'
[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m vbocr setup
echo "Installed. Start the server with: ./start-server.sh"
