#!/usr/bin/env bash
# Brand Voice Agent — interactive installer
# curl -sSL <url>/install.sh | bash
# or: ./install.sh

set -euo pipefail

CYAN='\033[36m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
WHITE='\033[1;37m'
GREY='\033[90m'
RESET='\033[0m'
LINE="────────────────────────────────────────────────────────────"

INSTALL_DIR="${HOME}/brand-voice-agent"
APP_NAME="brand-voice-agent"
KEYCHAIN_ACCOUNT="brand-voice-agent"

print_header() {
    printf "\n${CYAN}${LINE}${RESET}\n"
    printf "${WHITE}  Brand Voice Agent — Installer${RESET}\n"
    printf "${CYAN}${LINE}${RESET}\n\n"
}

print_step() {
    printf "${GREEN}[✓]${RESET} %s\n" "$1"
}

print_info() {
    printf "${GREY}    %s${RESET}\n" "$1"
}

print_warn() {
    printf "${YELLOW}[!]${RESET} %s\n" "$1"
}

# -----------------------------------------------------------------------

print_header

# 1. check for macOS
if [[ "$(uname)" != "Darwin" ]]; then
    echo "This tool is macOS only. Exiting."
    exit 1
fi
print_step "macOS detected"

# 2. homebrew
if ! command -v brew &>/dev/null; then
    printf "\n${YELLOW}Homebrew not found. Install it?${RESET} (y/n): "
    read -r yn
    if [[ "$yn" =~ ^[Yy] ]]; then
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    else
        print_warn "Homebrew required. Install it and re-run."
        exit 1
    fi
fi
print_step "Homebrew available"

# 3. python 3.11+
PYTHON_BIN=""
for py in python3.13 python3.12 python3.11 python3; do
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
    print_warn "Python 3.11+ not found. Installing via Homebrew..."
    brew install python@3.11
    PYTHON_BIN="python3.11"
fi
print_step "Python: $($PYTHON_BIN --version)"

# 4. project directory
if [[ -d "$INSTALL_DIR" ]]; then
    print_step "Project directory exists: ${INSTALL_DIR}"
else
    print_warn "Project directory not found at ${INSTALL_DIR}"
    printf "    ${GREY}Clone or copy the repo to ${INSTALL_DIR} and re-run.${RESET}\n"
    printf "    ${GREY}Or set INSTALL_DIR before running:${RESET}\n"
    printf "    ${GREY}  INSTALL_DIR=/your/path ./install.sh${RESET}\n"

    # try current directory as fallback
    if [[ -f "./app/main.py" ]]; then
        INSTALL_DIR="$(pwd)"
        print_step "Using current directory: ${INSTALL_DIR}"
    else
        exit 1
    fi
fi

cd "$INSTALL_DIR"

# 5. virtual environment
if [[ ! -d ".venv" ]]; then
    print_info "Creating virtual environment..."
    "$PYTHON_BIN" -m venv .venv
fi
print_step "Virtual environment: .venv"

# 6. install deps
print_info "Installing dependencies..."
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
print_step "Dependencies installed"

# 7. API key
printf "\n${CYAN}${LINE}${RESET}\n"
printf "${WHITE}  Lightning AI Credentials${RESET}\n"
printf "${CYAN}${LINE}${RESET}\n\n"

existing_key=$(security find-generic-password -a "$KEYCHAIN_ACCOUNT" -s "lightning-api-key" -w 2>/dev/null || echo "")
if [[ -n "$existing_key" ]]; then
    print_step "API key already in Keychain"
    printf "    ${GREY}Update it? (y/n): ${RESET}"
    read -r yn
    if [[ "$yn" =~ ^[Yy] ]]; then
        existing_key=""
    fi
fi

if [[ -z "$existing_key" ]]; then
    printf "${YELLOW}Paste your Lightning AI API key (sk-lit-...):${RESET} "
    read -rs api_key
    echo ""
    if [[ -n "$api_key" ]]; then
        security delete-generic-password -a "$KEYCHAIN_ACCOUNT" -s "lightning-api-key" 2>/dev/null || true
        security add-generic-password -a "$KEYCHAIN_ACCOUNT" -s "lightning-api-key" -w "$api_key"
        print_step "API key stored in Keychain"
    fi
fi

# 8. agent auth token (optional)
existing_token=$(security find-generic-password -a "$KEYCHAIN_ACCOUNT" -s "agent-auth-token" -w 2>/dev/null || echo "")
if [[ -n "$existing_token" ]]; then
    print_step "Agent auth token already in Keychain"
else
    printf "\n${GREY}Agent auth token (optional — for Lightning AI Agent mode):${RESET}\n"
    printf "${YELLOW}Paste the base64 token (or press Enter to skip):${RESET} "
    read -rs agent_token
    echo ""
    if [[ -n "$agent_token" ]]; then
        security add-generic-password -a "$KEYCHAIN_ACCOUNT" -s "agent-auth-token" -w "$agent_token"
        print_step "Agent auth token stored in Keychain"
    else
        print_info "Skipped (you can add it later from the menu bar)"
    fi
fi

# 9. permissions guide
printf "\n${CYAN}${LINE}${RESET}\n"
printf "${WHITE}  macOS Permissions${RESET}\n"
printf "${CYAN}${LINE}${RESET}\n\n"
printf "${YELLOW}You need to grant these permissions for hotkeys to work:${RESET}\n\n"
printf "  System Settings → Privacy & Security →\n"
printf "    ${GREEN}Accessibility${RESET}: enable ${WHITE}${INSTALL_DIR}/.venv/bin/python${RESET}\n"
printf "    ${GREEN}Input Monitoring${RESET}: enable the same\n\n"
printf "  ${GREY}If launching from Terminal or Cursor, enable those apps too.${RESET}\n"
printf "  ${GREY}Restart Terminal after changing permissions.${RESET}\n\n"

# 10. auto-start
printf "${YELLOW}Enable auto-start at login?${RESET} (y/n): "
read -r yn
if [[ "$yn" =~ ^[Yy] ]]; then
    PLIST_PATH="$HOME/Library/LaunchAgents/com.local.brand-voice-agent.plist"
    cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.local.brand-voice-agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>${INSTALL_DIR}/.venv/bin/python</string>
        <string>-m</string>
        <string>app.main</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${INSTALL_DIR}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
PLIST
    launchctl load -w "$PLIST_PATH" 2>/dev/null || true
    print_step "Auto-start enabled"
fi

# 11. launch now?
printf "\n${YELLOW}Launch Brand Voice now?${RESET} (y/n): "
read -r yn
if [[ "$yn" =~ ^[Yy] ]]; then
    printf "\n${GREEN}Starting...${RESET}\n"
    cd "$INSTALL_DIR"
    .venv/bin/python -m app.main &
    disown
    print_step "Running! Look for 'BV' in your menu bar."
fi

printf "\n${CYAN}${LINE}${RESET}\n"
printf "${GREEN}  Done!${RESET}\n"
printf "${GREY}  Select text anywhere → Cmd+Ctrl+G → rewritten${RESET}\n"
printf "${GREY}  Cmd+Ctrl+M to cycle modes${RESET}\n"
printf "${GREY}  Click 'BV' in menu bar for settings${RESET}\n"
printf "${CYAN}${LINE}${RESET}\n\n"
