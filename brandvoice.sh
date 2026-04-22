#!/usr/bin/env bash
# brandvoice — launch the Brand Voice menu bar app
# Usage:
#   ./brandvoice.sh                  (launch GUI)
#   ./brandvoice.sh --text "msg"     (CLI mode)
#   ./brandvoice.sh --help           (show options)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="${SCRIPT_DIR}/.venv/bin/python"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "No virtual environment found at ${SCRIPT_DIR}/.venv"
    echo "Run install.sh first:  ./install.sh"
    exit 1
fi

exec "$VENV_PYTHON" -m app.main "$@"
