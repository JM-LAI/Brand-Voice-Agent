import os
import subprocess
import threading
import time

import objc
import pyperclip
import rumps

from app.config import (
    MODES, MODELS, DEFAULT_STATE, SOUND_PATH, LAUNCHAGENT_LABEL,
    LAUNCHAGENT_PATH, MODE_TO_FILENAME,
)
from app.settings import (
    read_state, write_state, log,
    get_api_key, set_api_key,
    is_first_run, add_history_entry,
)
from app.prompts import ensure_rules_dir, get_rules_path, reset_rules
from app.clipboard import copy_selection, replace_selection
from app.llm import rewrite
from app.hotkeys import HotkeyListener
from app.ui import (
    notify_success, notify_error, play_sound,
    show_preview, record_hotkey, run_onboarding,
)

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

from Foundation import NSObject

class _Trampoline(NSObject):
    """One-shot callback trampoline for dispatching to the main thread."""
    def initWithFunc_(self, fn):
        self = objc.super(_Trampoline, self).init()
        if self is None:
            return None
        self._fn = fn
        return self

    def invoke(self):
        self._fn()


def _run_on_main_thread(func, *args):
    """Dispatch a function to the main thread. Used for UI calls from background threads."""
    trampoline = _Trampoline.alloc().initWithFunc_(lambda: func(*args))
    trampoline.performSelectorOnMainThread_withObject_waitUntilDone_(
        "invoke", None, True
    )


MODE_SHORT = {
    "Brand Voice": "BV",
    "Grammar Only": "Gram",
    "Shorten": "Short",
    "Formal": "Form",
    "Casual": "Chill",
}


class BrandVoiceApp(rumps.App):
    def __init__(self):
        super().__init__("BV", quit_button=None)
        self.state = read_state()
        self.title = self._mode_title()
        self._undo_buffer = None  # {original, rewritten}
        self._spinning = False
        self._spinner_idx = 0
        self._preview_result = None  # shared slot for preview return value

        ensure_rules_dir()

        self.menu = self._build_menu()
        self._sync_menu_state()

        # hotkey listener in a daemon thread
        self.hotkey_listener = HotkeyListener(
            hotkey_rewrite=self.state.get("hotkey_rewrite", DEFAULT_STATE["hotkey_rewrite"]),
            hotkey_cycle=self.state.get("hotkey_cycle", DEFAULT_STATE["hotkey_cycle"]),
            hotkey_undo=self.state.get("hotkey_undo", DEFAULT_STATE["hotkey_undo"]),
            on_rewrite=self._on_rewrite,
            on_cycle=self._on_cycle,
            on_undo=self._on_undo,
        )
        self.hotkey_listener.start()

        # onboarding for first-time users — use rumps.Timer so it fires on the main thread
        if is_first_run():
            self._onboarding_timer = rumps.Timer(self._deferred_onboarding, 1.5)
            self._onboarding_timer.start()

        log("Brand Voice app started")

    def _deferred_onboarding(self, _):
        """Fires once on the main thread, then stops itself."""
        self._onboarding_timer.stop()
        self._run_onboarding()

    def _mode_title(self, mode=None):
        m = mode or self.state.get("mode", "Brand Voice")
        return MODE_SHORT.get(m, "BV")

    # -----------------------------------------------------------------------
    # Menu construction
    # -----------------------------------------------------------------------

    def _build_menu(self):
        mode_label = rumps.MenuItem(f"Mode: {self.state.get('mode', 'Brand Voice')}")
        mode_label.set_callback(None)

        return [
            mode_label,
            None,  # separator
            rumps.MenuItem("Enabled", callback=self._toggle_enabled),
            None,
            self._mode_submenu(),
            self._model_submenu(),
            None,
            self._edit_rules_submenu(),
            None,
            rumps.MenuItem("Undo Last Rewrite", callback=self._menu_undo),
            self._history_submenu(),
            None,
            rumps.MenuItem("Preview Before Paste", callback=self._toggle_preview),
            rumps.MenuItem("Sound on Complete", callback=self._toggle_sound),
            None,
            self._settings_submenu(),
            None,
            rumps.MenuItem("Restart", callback=self._restart),
            rumps.MenuItem("Quit", callback=self._quit),
        ]

    def _mode_submenu(self):
        items = []
        current = self.state.get("mode", "Brand Voice")
        for mode in MODES:
            item = rumps.MenuItem(mode, callback=self._set_mode)
            item.state = 1 if mode == current else 0
            items.append(item)
        return {"Mode": items}

    def _model_submenu(self):
        items = []
        current = self.state.get("model", "")
        for display_name, model_id in MODELS.items():
            item = rumps.MenuItem(display_name, callback=self._set_model)
            item.state = 1 if model_id == current else 0
            items.append(item)
        return {"Model": items}

    def _edit_rules_submenu(self):
        items = []
        for mode in MODES:
            item = rumps.MenuItem(f"{mode}...", callback=self._edit_rules)
            items.append(item)
        items.append(None)  # separator
        items.append(rumps.MenuItem("Reset All to Defaults", callback=self._reset_all_rules))
        return {"Edit Rules": items}

    def _history_submenu(self):
        items = []
        history = self.state.get("history", [])
        if history:
            for i, entry in enumerate(history[:20]):
                label = entry["original"][:30]
                if len(entry["original"]) > 30:
                    label += "..."
                item = rumps.MenuItem(label, callback=self._copy_from_history)
                item._bv_index = i
                items.append(item)
            items.append(None)
        items.append(rumps.MenuItem("Clear History", callback=self._clear_history))
        return {"History": items}

    def _settings_submenu(self):
        return {"Settings": [
            rumps.MenuItem("API Key...", callback=self._set_api_key),
            None,
            rumps.MenuItem("Set Rewrite Hotkey...", callback=self._set_rewrite_hotkey),
            rumps.MenuItem("Set Cycle Mode Hotkey...", callback=self._set_cycle_hotkey),
            rumps.MenuItem("Set Undo Hotkey...", callback=self._set_undo_hotkey),
            None,
            rumps.MenuItem("Auto-start at Login", callback=self._toggle_autostart),
            rumps.MenuItem("Test Connection", callback=self._test_connection),
            rumps.MenuItem("Open Logs", callback=self._open_logs),
        ]}

    # -----------------------------------------------------------------------
    # Menu state sync
    # -----------------------------------------------------------------------

    def _sync_menu_state(self):
        """Reflect current state in menu checkmarks and labels."""
        try:
            self.menu["Enabled"].state = 1 if self.state.get("enabled", True) else 0
            self.menu["Preview Before Paste"].state = 1 if self.state.get("preview") else 0
            self.menu["Sound on Complete"].state = 1 if self.state.get("sound", True) else 0

            mode_label = f"Mode: {self.state.get('mode', 'Brand Voice')}"
            # update the first menu item text
            for key in list(self.menu.keys()):
                if str(key).startswith("Mode:"):
                    self.menu[key].title = mode_label
                    break

            settings = self.menu.get("Settings")
            if settings:
                for item in settings.values():
                    if hasattr(item, 'title'):
                        if item.title == "Auto-start at Login":
                            item.state = 1 if self.state.get("auto_start") else 0
        except Exception:
            pass

    def _save_and_sync(self):
        write_state(self.state)
        self._sync_menu_state()

    # -----------------------------------------------------------------------
    # Core rewrite flow
    # -----------------------------------------------------------------------

    def _on_rewrite(self):
        """Hotkey pressed — run rewrite in a background thread."""
        if not self.state.get("enabled", True):
            return
        threading.Thread(target=self._do_rewrite, daemon=True).start()

    def _do_rewrite(self):
        self._start_spinner()
        try:
            text = copy_selection()
            if not text.strip():
                log("Nothing selected to rewrite")
                self._stop_spinner()
                return

            mode = self.state.get("mode", "Brand Voice")
            model = self.state.get("model", "")

            log(f"Rewriting {len(text.split())} words in {mode} mode")
            result = rewrite(text, mode, model)

            if not result.strip():
                _run_on_main_thread(notify_error, "Empty response from AI")
                self._stop_spinner()
                return

            # preview if enabled — must run on main thread since it shows a window
            if self.state.get("preview"):
                self._preview_result = None
                _run_on_main_thread(self._show_preview_main, text, result)
                final = self._preview_result
                if final is None:
                    log("Preview cancelled")
                    self._stop_spinner()
                    return
                result = final

            replace_selection(result)

            # undo buffer
            self._undo_buffer = {"original": text, "rewritten": result}

            # history
            add_history_entry(self.state, text, result)
            self.state = read_state()  # reload after history write

            orig_words = len(text.split())
            new_words = len(result.split())
            _run_on_main_thread(notify_success, mode, orig_words, new_words)

            if self.state.get("sound", True):
                play_sound(SOUND_PATH)

            log(f"Rewrite done: {orig_words} → {new_words} words")

        except Exception as e:
            log(f"Rewrite error: {e}")
            _run_on_main_thread(notify_error, str(e))
            self._stop_spinner()
            self.title = self._mode_title() + "!"
            return

        self._stop_spinner()

    def _show_preview_main(self, original, rewritten):
        """Wrapper for show_preview that stores result — called on main thread."""
        self._preview_result = show_preview(original, rewritten)

    def _on_cycle(self):
        """Cycle to the next mode."""
        current = self.state.get("mode", "Brand Voice")
        try:
            idx = MODES.index(current)
        except ValueError:
            idx = 0
        next_mode = MODES[(idx + 1) % len(MODES)]
        self.state["mode"] = next_mode
        write_state(self.state)
        self.title = self._mode_title()

        def _update_ui():
            self._sync_menu_state()
            try:
                mode_menu = self.menu.get("Mode")
                if mode_menu:
                    for item in mode_menu.values():
                        if hasattr(item, 'title'):
                            item.state = 1 if item.title == next_mode else 0
            except Exception:
                pass
            for key in list(self.menu.keys()):
                if str(key).startswith("Mode:"):
                    self.menu[key].title = f"Mode: {next_mode}"
                    break
            rumps.notification(title="Brand Voice", subtitle="Mode", message=next_mode)

        _run_on_main_thread(_update_ui)
        log(f"Mode cycled to: {next_mode}")

    def _on_undo(self):
        """Undo the last rewrite."""
        if not self._undo_buffer:
            return
        replace_selection(self._undo_buffer["original"])
        log("Undo: restored original text")
        self._undo_buffer = None

    # -----------------------------------------------------------------------
    # Spinner
    # -----------------------------------------------------------------------

    def _start_spinner(self):
        self._spinning = True
        self._spinner_idx = 0

        def _spin():
            while self._spinning:
                self.title = SPINNER_FRAMES[self._spinner_idx % len(SPINNER_FRAMES)]
                self._spinner_idx += 1
                time.sleep(0.1)

        threading.Thread(target=_spin, daemon=True).start()

    def _stop_spinner(self):
        self._spinning = False
        self.title = self._mode_title()

    # -----------------------------------------------------------------------
    # Menu callbacks
    # -----------------------------------------------------------------------

    def _toggle_enabled(self, sender):
        self.state["enabled"] = not self.state.get("enabled", True)
        self._save_and_sync()

    def _set_mode(self, sender):
        self.state["mode"] = sender.title
        self._save_and_sync()
        self.title = self._mode_title()

        mode_menu = self.menu.get("Mode")
        if mode_menu:
            for item in mode_menu.values():
                if hasattr(item, 'title'):
                    item.state = 1 if item.title == sender.title else 0

        for key in list(self.menu.keys()):
            if str(key).startswith("Mode:"):
                self.menu[key].title = f"Mode: {sender.title}"
                break

    def _set_model(self, sender):
        model_id = MODELS.get(sender.title, sender.title)
        self.state["model"] = model_id
        self._save_and_sync()

        model_menu = self.menu.get("Model")
        if model_menu:
            for item in model_menu.values():
                if hasattr(item, 'title'):
                    item.state = 1 if item.title == sender.title else 0

    def _toggle_preview(self, sender):
        self.state["preview"] = not self.state.get("preview", False)
        self._save_and_sync()

    def _toggle_sound(self, sender):
        self.state["sound"] = not self.state.get("sound", True)
        self._save_and_sync()

    def _edit_rules(self, sender):
        # sender.title is like "Brand Voice..." — strip the ellipsis
        mode_name = sender.title.rstrip(".")
        path = get_rules_path(mode_name)
        if path.exists():
            subprocess.Popen(["open", "-t", str(path)])
        else:
            ensure_rules_dir()
            subprocess.Popen(["open", "-t", str(path)])

    def _reset_all_rules(self, _):
        result = rumps.alert(
            title="Reset Rules",
            message="Reset all rules files to their defaults?\n\nThis will overwrite any edits you've made.",
            ok="Reset",
            cancel="Cancel",
        )
        if result == 1:
            reset_rules()
            rumps.notification(title="Brand Voice", subtitle="Rules Reset", message="All rules restored to defaults")

    def _menu_undo(self, _):
        self._on_undo()

    def _copy_from_history(self, sender):
        idx = getattr(sender, '_bv_index', 0)
        history = self.state.get("history", [])
        if idx < len(history):
            pyperclip.copy(history[idx]["rewritten"])
            rumps.notification(title="Brand Voice", subtitle="Copied", message="Rewritten text copied to clipboard")

    def _clear_history(self, _):
        self.state["history"] = []
        self._save_and_sync()

    # settings callbacks

    def _set_api_key(self, _):
        win = rumps.Window(
            message="Enter your Lightning AI API key:",
            title="API Key",
            default_text=get_api_key() or "",
            ok="Save",
            cancel="Cancel",
            dimensions=(400, 24),
        )
        resp = win.run()
        if resp.clicked == 1 and resp.text.strip():
            set_api_key(resp.text.strip())

    def _set_rewrite_hotkey(self, _):
        current = self.state.get("hotkey_rewrite", DEFAULT_STATE["hotkey_rewrite"])
        new = record_hotkey("Set Rewrite Hotkey", current)
        if new:
            self.state["hotkey_rewrite"] = new
            self._save_and_sync()
            self.hotkey_listener.update_hotkeys(
                new,
                self.state.get("hotkey_cycle", DEFAULT_STATE["hotkey_cycle"]),
                self.state.get("hotkey_undo", DEFAULT_STATE["hotkey_undo"]),
            )

    def _set_cycle_hotkey(self, _):
        current = self.state.get("hotkey_cycle", DEFAULT_STATE["hotkey_cycle"])
        new = record_hotkey("Set Cycle Mode Hotkey", current)
        if new:
            self.state["hotkey_cycle"] = new
            self._save_and_sync()
            self.hotkey_listener.update_hotkeys(
                self.state.get("hotkey_rewrite", DEFAULT_STATE["hotkey_rewrite"]),
                new,
                self.state.get("hotkey_undo", DEFAULT_STATE["hotkey_undo"]),
            )

    def _set_undo_hotkey(self, _):
        current = self.state.get("hotkey_undo", DEFAULT_STATE["hotkey_undo"])
        new = record_hotkey("Set Undo Hotkey", current)
        if new:
            self.state["hotkey_undo"] = new
            self._save_and_sync()
            self.hotkey_listener.update_hotkeys(
                self.state.get("hotkey_rewrite", DEFAULT_STATE["hotkey_rewrite"]),
                self.state.get("hotkey_cycle", DEFAULT_STATE["hotkey_cycle"]),
                new,
            )

    def _toggle_autostart(self, sender):
        self.state["auto_start"] = not self.state.get("auto_start", False)
        self._save_and_sync()

        if self.state["auto_start"]:
            self._install_launchagent()
        else:
            self._remove_launchagent()

    def _install_launchagent(self):
        """Write a LaunchAgent plist for auto-start at login."""
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        launcher = os.path.join(app_dir, "brandvoice.sh")

        plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LAUNCHAGENT_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>{launcher}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{app_dir}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{os.path.expanduser("~/Library/Logs/brand-voice-agent.stdout.log")}</string>
    <key>StandardErrorPath</key>
    <string>{os.path.expanduser("~/Library/Logs/brand-voice-agent.stderr.log")}</string>
</dict>
</plist>"""
        os.makedirs(os.path.dirname(LAUNCHAGENT_PATH), exist_ok=True)
        with open(LAUNCHAGENT_PATH, "w") as f:
            f.write(plist)
        subprocess.run(["launchctl", "load", "-w", LAUNCHAGENT_PATH],
                       capture_output=True)
        log("LaunchAgent installed for auto-start")

    def _remove_launchagent(self):
        try:
            subprocess.run(["launchctl", "unload", "-w", LAUNCHAGENT_PATH],
                           capture_output=True)
            if os.path.exists(LAUNCHAGENT_PATH):
                os.remove(LAUNCHAGENT_PATH)
            log("LaunchAgent removed")
        except Exception:
            pass

    def _test_connection(self, _):
        """Quick API test — send a one-word message, show result."""
        def _test():
            try:
                from app.llm import call_model
                from app.prompts import get_system_prompt
                from app.config import DEFAULT_MODEL
                start = time.time()
                call_model("Hello", self.state.get("model", DEFAULT_MODEL),
                           get_system_prompt("Grammar Only"))
                elapsed = time.time() - start
                _run_on_main_thread(
                    rumps.notification, "Brand Voice", "Connection OK",
                    f"Response in {elapsed:.1f}s",
                )
            except Exception as e:
                _run_on_main_thread(notify_error, f"Connection test failed: {e}")

        threading.Thread(target=_test, daemon=True).start()

    def _open_logs(self, _):
        from app.config import LOG_PATH
        if os.path.exists(LOG_PATH):
            subprocess.Popen(["open", "-a", "Console", LOG_PATH])
        else:
            rumps.alert("No log file found yet.")

    def _restart(self, _):
        """Restart the entire app by re-executing the process."""
        import sys
        self.hotkey_listener.stop()
        log("App restarting — re-exec")
        python = sys.executable
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        os.chdir(app_dir)
        os.execv(python, [python, "-m", "app.main"])

    def _quit(self, _):
        self.hotkey_listener.stop()
        log("App quit")
        rumps.quit_application()

    def _run_onboarding(self):
        run_onboarding()
        self.state = read_state()
        self._sync_menu_state()
