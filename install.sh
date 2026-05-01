#!/usr/bin/env bash
# Brand Voice Agent — one-liner installer
# curl -sSL https://raw.githubusercontent.com/JM-LAI/Brand-Voice-Agent/main/install.sh | bash

set -euo pipefail

CYAN='\033[36m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
WHITE='\033[1;37m'
GREY='\033[90m'
RED='\033[1;31m'
RESET='\033[0m'
LINE="────────────────────────────────────────────────────────────"

REPO_URL="https://github.com/JM-LAI/Brand-Voice-Agent.git"
INSTALL_DIR="${INSTALL_DIR:-${HOME}/Brand-Voice-Agent}"
KEYCHAIN_ACCOUNT="brand-voice-agent"

print_header() {
    printf "\n${CYAN}${LINE}${RESET}\n"
    printf "${WHITE}  Brand Voice Agent — Installer${RESET}\n"
    printf "${CYAN}${LINE}${RESET}\n\n"
}

ok()   { printf "${GREEN}[✓]${RESET} %s\n" "$1"; }
info() { printf "${GREY}    %s${RESET}\n" "$1"; }
warn() { printf "${YELLOW}[!]${RESET} %s\n" "$1"; }
fail() { printf "${RED}[✗]${RESET} %s\n" "$1"; exit 1; }

# -----------------------------------------------------------------------

print_header

# macOS only
[[ "$(uname)" == "Darwin" ]] || fail "This tool is macOS only."
ok "macOS detected"

# homebrew
if ! command -v brew &>/dev/null; then
    warn "Homebrew not found — installing..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi
ok "Homebrew available"

# python 3.11+
PYTHON_BIN=""
for py in python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$py" &>/dev/null; then
        ver=$("$py" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [[ "$major" -ge 3 && "$minor" -ge 11 ]]; then
            PYTHON_BIN="$py"
            break
        fi
    fi
done

if [[ -z "$PYTHON_BIN" ]]; then
    warn "Python 3.11+ not found — installing via Homebrew..."
    brew install python@3.12
    PYTHON_BIN="python3.12"
fi
ok "Python: $($PYTHON_BIN --version)"

# clone or update repo
if [[ -d "$INSTALL_DIR/.git" ]]; then
    ok "Repo already cloned at ${INSTALL_DIR}"
    info "Pulling latest..."
    git -C "$INSTALL_DIR" pull --ff-only 2>/dev/null || true
elif [[ -f "$INSTALL_DIR/app/main.py" ]]; then
    ok "Project found at ${INSTALL_DIR} (not a git repo, skipping pull)"
else
    info "Cloning repo to ${INSTALL_DIR}..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    ok "Cloned to ${INSTALL_DIR}"
fi

cd "$INSTALL_DIR"

# virtual environment + deps
if [[ ! -d ".venv" ]]; then
    info "Creating virtual environment..."
    "$PYTHON_BIN" -m venv .venv
fi
info "Installing dependencies..."
.venv/bin/pip install --quiet --upgrade pip 2>/dev/null
.venv/bin/pip install --quiet -r requirements.txt 2>/dev/null
ok "Dependencies installed"

# API key
printf "\n${CYAN}${LINE}${RESET}\n"
printf "${WHITE}  Lightning AI API Key${RESET}\n"
printf "${CYAN}${LINE}${RESET}\n\n"

existing_key=$(security find-generic-password -a "$KEYCHAIN_ACCOUNT" -s "lightning-api-key" -w 2>/dev/null || echo "")
if [[ -n "$existing_key" ]]; then
    ok "API key already in Keychain"
    printf "    ${GREY}Replace it? (y/n): ${RESET}"
    read -r yn
    if [[ ! "$yn" =~ ^[Yy] ]]; then
        info "Keeping existing key"
    else
        existing_key=""
    fi
fi

if [[ -z "$existing_key" ]]; then
    printf "${WHITE}  You need a free Lightning AI API key to continue.${RESET}\n\n"
    printf "${GREY}  Steps:${RESET}\n"
    printf "${GREY}    1. Go to: ${WHITE}https://lightning.ai/lightning-ai/model-apis?showApiKey=true${RESET}\n"
    printf "${GREY}    2. Sign up or log in (free)${RESET}\n"
    printf "${GREY}    3. Click \"Create API Key\"${RESET}\n"
    printf "${GREY}    4. Copy the key (starts with sk-lit-...)${RESET}\n\n"

    # try to open the browser for them
    open "https://lightning.ai/lightning-ai/model-apis?showApiKey=true" 2>/dev/null || true

    printf "${YELLOW}I've opened the page in your browser.${RESET}\n"
    printf "${YELLOW}Once you have the key, paste it here and press Enter.${RESET}\n\n"
    printf "${WHITE}API key: ${RESET}"
    read -rs api_key
    echo ""

    if [[ -n "$api_key" ]]; then
        security delete-generic-password -a "$KEYCHAIN_ACCOUNT" -s "lightning-api-key" 2>/dev/null || true
        security add-generic-password -a "$KEYCHAIN_ACCOUNT" -s "lightning-api-key" -w "$api_key"
        ok "API key stored in Keychain"
    else
        warn "No key entered — you can add it later from the menu bar (Settings → API Key)"
    fi
fi

# make launcher executable
chmod +x "$INSTALL_DIR/brandvoice.sh" 2>/dev/null || true

# launch
printf "\n${CYAN}${LINE}${RESET}\n"
printf "${GREEN}  All set!${RESET}\n"
printf "${CYAN}${LINE}${RESET}\n\n"

printf "${YELLOW}Launch Brand Voice now?${RESET} (y/n): "
read -r yn
if [[ "$yn" =~ ^[Yy] ]]; then
    "$INSTALL_DIR/brandvoice.sh"
    printf "\n"
    ok "Running! Look for the mode indicator in your menu bar."
    info "The app will walk you through permissions on first launch."
fi

# print the python path they'll need for permissions
VENV_PYTHON="$(cd "$INSTALL_DIR" && .venv/bin/python -c "import sys,os; print(os.path.realpath(sys.executable))")"
printf "${YELLOW}  ⚠ IMPORTANT — You'll need this path for macOS permissions:${RESET}\n\n"
printf "${WHITE}    ${VENV_PYTHON}${RESET}\n\n"
printf "${GREY}  The app will try to copy it to your clipboard during setup,${RESET}\n"
printf "${GREY}  but if that fails, copy it from here.${RESET}\n"
printf "${GREY}  Add this path to: System Settings → Privacy & Security →${RESET}\n"
printf "${GREY}    • Accessibility${RESET}\n"
printf "${GREY}    • Input Monitoring${RESET}\n\n"

printf "\n${GREY}  Quick reference:${RESET}\n"
printf "${GREY}    Cmd+Ctrl+G    Rewrite selected text${RESET}\n"
printf "${GREY}    Cmd+Ctrl+M    Cycle modes${RESET}\n"
printf "${GREY}    Cmd+Ctrl+Z    Undo last rewrite${RESET}\n"
printf "${GREY}    Menu bar      Settings, models, rules, history${RESET}\n\n"
printf "${GREY}  To launch again later:${RESET}\n"
printf "${GREY}    ${INSTALL_DIR}/brandvoice.sh${RESET}\n\n"
printf "${GREY}  To uninstall, see the README:${RESET}\n"
printf "${GREY}    ${INSTALL_DIR}/README.md${RESET}\n\n"
