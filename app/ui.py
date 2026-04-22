"""
Rich UI components: hotkey recorder, preview window, notifications, onboarding.
Uses pyobjc for native macOS panels beyond what rumps provides.
"""
import subprocess
import threading
import time

import pyperclip
import rumps

from app.config import APP_NAME
from app.settings import log


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

def notify_success(mode: str, original_words: int, new_words: int):
    rumps.notification(
        title=APP_NAME,
        subtitle=mode,
        message=f"{original_words} → {new_words} words",
    )


def notify_error(message: str):
    rumps.notification(
        title=APP_NAME,
        subtitle="Rewrite failed",
        message=str(message)[:200],
    )


# ---------------------------------------------------------------------------
# Sound
# ---------------------------------------------------------------------------

def play_sound(path: str):
    """Play a system sound in the background."""
    try:
        subprocess.Popen(
            ["afplay", path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Hotkey Recorder
# ---------------------------------------------------------------------------

def record_hotkey(title: str, current: str) -> str | None:
    """
    Show a dialog asking the user to press a hotkey combo.

    Uses a polling approach with rumps.Window since we can't do true
    NSEvent monitoring from a rumps context without blocking. Falls back
    to a text-entry dialog where the user types the combo.

    Returns pynput-format string like '<cmd>+<ctrl>+g' or None if cancelled.
    """
    win = rumps.Window(
        message=(
            f"Current: {_pretty(current)}\n\n"
            "Type your new hotkey combo using this format:\n"
            "cmd+ctrl+g  or  cmd+alt+shift+r\n\n"
            "Available modifiers: cmd, ctrl, alt, shift\n"
            "Then any single letter key."
        ),
        title=title,
        default_text=current.replace("<", "").replace(">", ""),
        ok="Save",
        cancel="Cancel",
        dimensions=(300, 24),
    )
    response = win.run()
    if response.clicked == 0:
        return None

    raw = response.text.strip().lower()
    if not raw:
        return None

    # normalise to pynput format
    parts = [p.strip() for p in raw.split("+")]
    normalised = []
    has_modifier = False
    has_key = False
    for p in parts:
        if p in ("cmd", "ctrl", "alt", "shift"):
            normalised.append(f"<{p}>")
            has_modifier = True
        elif len(p) == 1 and p.isalpha():
            normalised.append(p)
            has_key = True

    if not has_modifier or not has_key:
        rumps.alert(
            title="Invalid Hotkey",
            message="Need at least one modifier (cmd/ctrl/alt/shift) and one letter key.",
        )
        return None

    result = "+".join(normalised)
    log(f"Hotkey recorded: {result}")
    return result


def _pretty(expr: str) -> str:
    """<cmd>+<ctrl>+g → Cmd+Ctrl+G"""
    parts = expr.split("+")
    out = []
    for p in parts:
        token = p.strip("<>").lower()
        if token in ("cmd", "ctrl", "alt", "shift"):
            out.append(token.capitalize())
        else:
            out.append(token.upper())
    return "+".join(out)


# ---------------------------------------------------------------------------
# Preview Window
# ---------------------------------------------------------------------------

def show_preview(original: str, rewritten: str) -> str | None:
    """
    Show a preview dialog with original and rewritten text.

    Returns the (possibly edited) rewritten text if accepted, None if cancelled.
    """
    orig_words = len(original.split())
    new_words = len(rewritten.split())

    win = rumps.Window(
        message=(
            f"── Original ({orig_words} words) ──\n"
            f"{original}\n\n"
            f"── Rewritten ({new_words} words) ──\n"
            "Edit below if needed:"
        ),
        title="Preview Rewrite",
        default_text=rewritten,
        ok="Accept",
        cancel="Cancel",
        dimensions=(500, 200),
    )
    response = win.run()
    if response.clicked == 0:
        return None
    return response.text.strip()


# ---------------------------------------------------------------------------
# First-Run Onboarding
# ---------------------------------------------------------------------------

def _bring_to_front():
    """Bring our app to the front so dialogs are visible."""
    try:
        from AppKit import NSApplication, NSApplicationActivateIgnoringOtherApps
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    except Exception:
        pass


def run_onboarding() -> bool:
    """
    Walk the user through initial setup.
    Returns True if completed, False if cancelled at any step.
    """
    from app.settings import set_api_key, get_api_key
    from app.llm import call_model
    from app.prompts import ensure_rules_dir

    _bring_to_front()

    # step 1: welcome
    result = rumps.alert(
        title="Welcome to Brand Voice",
        message=(
            "This tool rewrites your support messages to match the team's brand voice.\n\n"
            "Select text anywhere → press Cmd+Ctrl+G → text gets rewritten.\n\n"
            "Let's get you set up. You'll need your Lightning AI API key."
        ),
        ok="Let's go",
        cancel="Skip Setup",
    )
    if result == 0:
        return False

    # step 2: API key
    win = rumps.Window(
        message="Paste your Lightning AI API key (starts with sk-lit-...):",
        title="API Key",
        default_text="",
        ok="Save",
        cancel="Skip",
        dimensions=(400, 24),
    )
    resp = win.run()
    if resp.clicked == 1 and resp.text.strip():
        set_api_key(resp.text.strip())
    elif resp.clicked == 0:
        return False

    # step 3: test rewrite (if they entered a key)
    api_key = get_api_key()
    if api_key:
        result = rumps.alert(
            title="Test Connection",
            message="Want to test a quick rewrite to make sure everything works?",
            ok="Test Now",
            cancel="Skip",
        )
        if result == 1:
            try:
                test_input = "hi we see ur issue and are looking into it will get back to u"
                from app.config import DEFAULT_MODEL
                from app.prompts import get_system_prompt
                test_output = call_model(test_input, DEFAULT_MODEL, get_system_prompt("Brand Voice"))
                rumps.alert(
                    title="It works!",
                    message=f"Input: {test_input}\n\nOutput: {test_output}",
                )
            except Exception as e:
                rumps.alert(
                    title="Connection Failed",
                    message=f"Error: {e}\n\nCheck your API key and try again from Settings.",
                )

    # step 4: auto-start + permissions
    import sys
    import subprocess
    python_path = sys.executable

    result = rumps.alert(
        title="Run at Login?",
        message=(
            "Want Brand Voice to start automatically when you log in?\n\n"
            "This means you won't need to open Terminal to use it — "
            "it'll always be in your menu bar."
        ),
        ok="Yes, auto-start",
        cancel="No, I'll launch it manually",
    )
    if result == 1:
        from app.settings import read_state, write_state
        state = read_state()
        state["auto_start"] = True
        write_state(state)
        # the tray app will pick this up and install the LaunchAgent

    # resolve symlinks so macOS gets the real binary
    import os
    real_python = os.path.realpath(python_path)

    go_to_tip = (
        "In the file picker:\n"
        "1. Press Cmd+Shift+G (Go to Folder)\n"
        "2. Paste with Cmd+V (the path is already on your clipboard)\n"
        "3. Press Enter, then click Open"
    )

    # step 5: open Accessibility pane
    pyperclip.copy(real_python)
    subprocess.Popen([
        "open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
    ])
    rumps.alert(
        title="Step 1 of 2 — Accessibility",
        message=(
            "I've opened the Accessibility settings pane and copied "
            "the Python path to your clipboard.\n\n"
            f"Path: {real_python}\n\n"
            "Click the + button, then:\n\n"
            f"{go_to_tip}\n\n"
            "Flip the switch ON, then click OK here."
        ),
    )

    # step 6: open Input Monitoring pane
    pyperclip.copy(real_python)
    subprocess.Popen([
        "open", "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
    ])
    rumps.alert(
        title="Step 2 of 2 — Input Monitoring",
        message=(
            "Now I've opened Input Monitoring and copied the path again.\n\n"
            f"Path: {real_python}\n\n"
            "Same thing — click +, then:\n\n"
            f"{go_to_tip}\n\n"
            "Flip the switch ON, then click OK here."
        ),
    )

    # step 6: done
    rumps.alert(
        title="You're Set Up",
        message=(
            "Select text anywhere and press Cmd+Ctrl+G to rewrite.\n\n"
            "Cmd+Ctrl+M cycles between modes.\n"
            "Cmd+Ctrl+Z undoes the last rewrite.\n\n"
            "Edit rules and change settings from the BV menu bar icon."
        ),
    )

    ensure_rules_dir()
    log("Onboarding completed")
    return True
