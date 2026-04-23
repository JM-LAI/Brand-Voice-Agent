#!/usr/bin/env bash
# brandvoice — launch the Brand Voice menu bar app
# Usage:
#   ./brandvoice.sh                  (launch GUI, detaches from terminal)
#   ./brandvoice.sh --text "msg"     (CLI mode, runs in foreground)
#   ./brandvoice.sh --help           (show options)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="${SCRIPT_DIR}/.venv/bin/python"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "No virtual environment found at ${SCRIPT_DIR}/.venv"
    echo "Run install.sh first:  ./install.sh"
    exit 1
fi

# CLI mode runs in foreground so you can see output
if [[ "${1:-}" == "--text" || "${1:-}" == "--help" || "${1:-}" == "--version" ]]; then
    exec "$VENV_PYTHON" -m app.main "$@"
fi

# GUI mode: detach from terminal so closing the terminal doesn't kill the app
nohup "$VENV_PYTHON" -m app.main "$@" &>/dev/null &
disown
echo "Brand Voice running in background (PID $!). Check your menu bar."
