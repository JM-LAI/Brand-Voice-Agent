# Brand Voice Agent

macOS menu bar tool that rewrites CX support messages to match the team's brand voice. Select text anywhere, press a hotkey, get a cleaner version back.

Built for CREs, non-native speakers, dyslexic folks, and anyone who wants consistent brand voice without second-guessing every message.

## Install

1. Open **Terminal** (press Cmd+Space, type "Terminal", press Enter)
2. Paste this and press Enter:

```bash
bash <(curl -sSL https://raw.githubusercontent.com/JM-LAI/Brand-Voice-Agent/main/install.sh)
```

3. The installer will open the API key page in your browser — copy your key and paste it when prompted
4. The app launches and walks you through macOS permissions

That's it. The installer handles Homebrew, Python, dependencies, and everything else automatically.

Already installed? Run `./install.sh` again — it's idempotent.

### Update

Pull the latest and restart:

```bash
cd ~/Brand-Voice-Agent && git pull && ./brandvoice.sh
```

### What You'll Need

- **macOS** (any recent version)
- **Lightning AI API key** (free) — get one at https://lightning.ai/lightning-ai/model-apis?showApiKey=true
- ~2 minutes

### macOS Permissions (step by step)

The app needs Accessibility and Input Monitoring permissions to capture hotkeys and paste text. The onboarding flow guides you through this automatically, but here's the full walkthrough:

**Accessibility:**

1. Open **System Settings** (Apple menu → System Settings)
2. Click **Privacy & Security** in the left sidebar
3. Scroll down and click **Accessibility**
4. Click the **+** button at the bottom of the list
5. A file picker opens — press **Cmd+Shift+G** to open "Go to Folder"
6. Paste the Python path (the installer copies it to your clipboard) and press Enter
7. Click **Open**
8. Make sure the toggle next to the new entry is **ON**

**Input Monitoring:**

9. Go back to **Privacy & Security**
10. Click **Input Monitoring**
11. Click the **+** button
12. Press **Cmd+Shift+G** again, paste the same Python path, press Enter
13. Click **Open**
14. Make sure the toggle is **ON**

**Terminal (required if you launch from Terminal):**

15. Go back to **Privacy & Security** → **Accessibility**
16. Click the **+** button
17. Navigate to **Applications → Utilities → Terminal** and click Open
18. Make sure the toggle is **ON**
19. Repeat for **Input Monitoring**: Privacy & Security → Input Monitoring → **+** → Applications → Utilities → Terminal → Open → toggle **ON**
20. **Quit Terminal completely** (Cmd+Q) and reopen it for changes to take effect

> **Important:** If you skip the Terminal steps, the hotkeys will not work. macOS requires both the Python binary AND the app you launch it from to have permissions.

## How It Works

1. Select text in any app (Slack, email, Notes, anywhere)
2. Press **Cmd+Ctrl+G** — text is replaced with the rewritten version
3. Press **Cmd+Ctrl+M** to cycle between modes
4. Press **Cmd+Ctrl+Z** to undo the last rewrite

The menu bar shows the active mode: **BV** (Brand Voice), **Gram** (Grammar), **Short** (Shorten), **Form** (Formal), **Chill** (Casual).

## Modes

| Mode | What it does |
|---|---|
| **Brand Voice** | Full rewrite — brand voice + grammar + sentiment. Warm, human, technically accurate. |
| **Grammar Only** | Fix grammar, spelling, and text-speak (ur→your, u→you). Preserves tone. |
| **Shorten** | Make it shorter, keep all meaning and technical details. |
| **Formal** | Polish to professional tone. |
| **Casual** | Soften to friendly, approachable tone. |

All modes powered by Gemma 4 31B on Lightning AI (free tier). Switch models from the menu bar.

## Editable Rules

Every mode's prompt is a plain text file you can edit:

**Menu bar → Edit Rules → [mode]** opens the file in your default text editor.

Rules live at `~/Library/Application Support/brand-voice-agent/rules/`. Changes take effect on the next rewrite — no restart needed. To restore defaults: **Menu bar → Edit Rules → Reset All Rules**.

## Features

- **Preview before paste** — review and edit the rewrite before it replaces your text
- **Undo** — Cmd+Ctrl+Z pastes back the original
- **Notifications** — success shows word count, failures show the error
- **Rewrite history** — last 20 rewrites accessible from the menu bar
- **Sound feedback** — optional system sound on completion
- **Hotkey recorder** — set custom hotkeys from the menu, no manual typing
- **Auto-start at login** — runs in the background via LaunchAgent
- **Connection test** — verify API connectivity from settings
- **First-run onboarding** — guided setup for new users
- **CLI mode** — for scripts and automation (see below)

## CLI Mode

```bash
# rewrite with default Brand Voice mode
./brandvoice.sh --text "hi we see ur issue and are looking into it"

# use a specific mode
./brandvoice.sh --text "your message" --mode "Grammar Only"

# use a specific model
./brandvoice.sh --text "your message" --model "lightning-ai/DeepSeek-V3.1"

# show all options
./brandvoice.sh --help
```

## Troubleshooting

### Hotkey not working
- Follow the [macOS Permissions](#macos-permissions-step-by-step) steps above
- Make sure both **Accessibility** and **Input Monitoring** toggles are ON
- Restart Terminal after changing permissions
- Try a different hotkey: Menu bar → Settings → Set Rewrite Hotkey

### Menu bar icon disappeared
```bash
./brandvoice.sh
```

### API errors
- Menu bar → Settings → Test Connection
- Check your API key: Menu bar → Settings → API Key
- Check logs: Menu bar → Settings → Open Logs

### Logs
```bash
tail -f ~/Library/Logs/brand-voice-agent.log
```

## Uninstall

### 1. Stop the app
Click the menu bar icon → **Quit**, or:
```bash
pkill -f "app.main"
```

### 2. Remove auto-start (if enabled)
```bash
launchctl unload -w ~/Library/LaunchAgents/com.local.brand-voice-agent.plist 2>/dev/null
rm -f ~/Library/LaunchAgents/com.local.brand-voice-agent.plist
```

### 3. Remove app data
```bash
# settings, rules, and state
rm -rf ~/Library/Application\ Support/brand-voice-agent

# logs
rm -f ~/Library/Logs/brand-voice-agent.log
rm -f ~/Library/Logs/brand-voice-agent.stdout.log
rm -f ~/Library/Logs/brand-voice-agent.stderr.log
```

### 4. Remove API key from Keychain
```bash
security delete-generic-password -s "lightning-api-key" -a "brand-voice-agent" 2>/dev/null
```

### 5. Remove the repo
```bash
rm -rf ~/Brand-Voice-Agent
```

### 6. Remove macOS permissions
System Settings → Privacy & Security → Accessibility / Input Monitoring — remove the Python binary entry.

## File Locations

| What | Where |
|---|---|
| App code | `Brand-Voice-Agent/app/` |
| Rules files | `~/Library/Application Support/brand-voice-agent/rules/` |
| State/config | `~/Library/Application Support/brand-voice-agent/state.json` |
| Logs | `~/Library/Logs/brand-voice-agent.log` |
| LaunchAgent | `~/Library/LaunchAgents/com.local.brand-voice-agent.plist` |
| API key | macOS Keychain (service: `lightning-api-key`) |

## Architecture

```
app/
  main.py       — entry point (GUI or CLI)
  tray.py       — rumps menu bar app, mode display, spinner
  ui.py         — hotkey recorder, preview window, notifications, onboarding
  hotkeys.py    — pynput global hotkey listener (daemon thread)
  clipboard.py  — Quartz CGEvent clipboard simulation
  llm.py        — Lightning AI chat completions client
  prompts.py    — load/save editable rules from disk
  settings.py   — state.json + macOS Keychain
  config.py     — constants, model list, defaults
```

Powered by Lightning AI's hosted models (Gemma 4 31B default). No local model needed.
