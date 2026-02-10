import subprocess
import time


class TextInjector:
    def __init__(self, use_clipboard=True, typing_delay_ms=12):
        self._use_clipboard = use_clipboard
        self._typing_delay = typing_delay_ms
        self._target_window = None

    def save_active_window(self):
        """Save the currently focused window ID (call before recording starts)."""
        try:
            result = subprocess.run(
                ["xdotool", "getactivewindow"],
                capture_output=True, text=True, check=True,
            )
            self._target_window = result.stdout.strip()
        except Exception:
            self._target_window = None

    def inject(self, text: str):
        """Inject text at the cursor in the saved target window."""
        if not text:
            return

        # Re-focus the target window before injecting
        if self._target_window:
            subprocess.run(
                ["xdotool", "windowactivate", "--sync", self._target_window],
                check=False,
            )
            time.sleep(0.05)

        if self._use_clipboard:
            self._inject_via_clipboard(text)
        else:
            self._inject_via_xdotool(text)

    def _inject_via_clipboard(self, text: str):
        """Copy text to clipboard via xclip, then Ctrl+V."""
        proc = subprocess.Popen(
            ["xclip", "-selection", "clipboard"],
            stdin=subprocess.PIPE,
        )
        proc.communicate(input=text.encode("utf-8"))
        time.sleep(0.05)
        subprocess.run(
            ["xdotool", "key", "--clearmodifiers", "ctrl+v"],
            check=False,
        )

    def _inject_via_xdotool(self, text: str):
        """Type text directly via xdotool."""
        subprocess.run(
            [
                "xdotool", "type", "--clearmodifiers",
                "--delay", str(self._typing_delay),
                "--", text,
            ],
            check=False,
        )
