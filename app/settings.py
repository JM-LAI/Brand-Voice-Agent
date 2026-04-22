import json
import os
import subprocess
import time

from app.config import (
    APP_SUPPORT, STATE_PATH, LOG_PATH, DEFAULT_STATE,
    KEYCHAIN_ACCOUNT, KEYCHAIN_API_KEY_SERVICE, KEYCHAIN_AGENT_TOKEN_SERVICE,
)


def log(message: str):
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {message}\n")
    except Exception:
        pass


def read_state() -> dict:
    os.makedirs(APP_SUPPORT, exist_ok=True)
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            merged = {**DEFAULT_STATE, **saved}
            return merged
        except Exception:
            pass
    return dict(DEFAULT_STATE)


def write_state(data: dict):
    os.makedirs(APP_SUPPORT, exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _keychain_get(service: str) -> str | None:
    """Read a password from macOS Keychain."""
    try:
        result = subprocess.run(
            ["security", "find-generic-password",
             "-a", KEYCHAIN_ACCOUNT, "-s", service, "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _keychain_set(service: str, secret: str):
    """Write a password to macOS Keychain. Overwrites if exists."""
    # delete existing entry first (ignore errors if it doesn't exist)
    subprocess.run(
        ["security", "delete-generic-password",
         "-a", KEYCHAIN_ACCOUNT, "-s", service],
        capture_output=True, timeout=5,
    )
    subprocess.run(
        ["security", "add-generic-password",
         "-a", KEYCHAIN_ACCOUNT, "-s", service, "-w", secret],
        capture_output=True, timeout=5,
    )


def get_api_key() -> str | None:
    return _keychain_get(KEYCHAIN_API_KEY_SERVICE)


def set_api_key(key: str):
    _keychain_set(KEYCHAIN_API_KEY_SERVICE, key)
    log("API key updated in Keychain")


def get_agent_token() -> str | None:
    return _keychain_get(KEYCHAIN_AGENT_TOKEN_SERVICE)


def set_agent_token(token: str):
    _keychain_set(KEYCHAIN_AGENT_TOKEN_SERVICE, token)
    log("Agent auth token updated in Keychain")


def is_first_run() -> bool:
    return get_api_key() is None


def add_history_entry(state: dict, original: str, rewritten: str):
    """Append a rewrite to history, cap at MAX_HISTORY."""
    from app.config import MAX_HISTORY
    entry = {
        "original": original,
        "rewritten": rewritten,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    history = state.get("history", [])
    history.insert(0, entry)
    state["history"] = history[:MAX_HISTORY]
    write_state(state)
