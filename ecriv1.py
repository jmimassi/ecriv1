#!/usr/bin/env python3
"""ecriv1 - Voice-to-text widget for Linux (French)

System tray indicator. F4 to toggle recording. F3 to cycle STT model.
Icon turns red while recording, text is pasted at cursor when stopped.
"""

import queue
import signal
import sys

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("AppIndicator3", "0.1")
from gi.repository import Gtk, GLib, AppIndicator3

import sounddevice as sd
from pynput import keyboard

from config import (
    APP_ID, SAMPLE_RATE, BLOCK_SIZE, AUDIO_DEVICE,
    USE_CLIPBOARD_INJECTION, TYPING_DELAY_MS,
    ICON_DIR, ICON_MIC_OFF, ICON_MIC_ON, HOTKEY,
)
from text_injector import TextInjector


class Ecriv1App:
    def __init__(self):
        self._recording = False
        self._audio_queue = queue.Queue()
        self._stream = None
        self._full_text = ""
        self._injected_len = 0

        # Build engine list and load default
        self._engines = self._build_engines()
        self._engine_idx = 0
        self._engine = self._engines[0]

        print(f"Loading {self._engine.name}...")
        self._engine.load()

        # Text injector
        self._injector = TextInjector(
            use_clipboard=USE_CLIPBOARD_INJECTION,
            typing_delay_ms=TYPING_DELAY_MS,
        )

        # Detect working sample rate
        self._native_rate = self._detect_rate()
        self._need_resample = self._native_rate != SAMPLE_RATE

        # Build indicator
        self._build_indicator()

        # Global hotkeys: F4 toggle, F3 cycle model
        self._hotkeys = keyboard.GlobalHotKeys({
            HOTKEY: self._on_f4,
            "<f3>": self._on_f3,
        })
        self._hotkeys.daemon = True
        self._hotkeys.start()

        print(f"ecriv1 ready — F4: record | F3: cycle model [{self._engine.name}]")

    # ── Engine setup ──────────────────────────────────────────────

    def _build_engines(self):
        from engines.streaming_whisper import StreamingWhisper
        return [
            StreamingWhisper("medium"),
        ]

    # ── Model switching ───────────────────────────────────────────

    def _on_f3(self):
        if self._recording:
            return
        GLib.idle_add(self._cycle_model)

    def _cycle_model(self):
        next_idx = (self._engine_idx + 1) % len(self._engines)
        self._switch_to(next_idx)

    def _on_model_menu(self, radio, idx):
        if not radio.get_active() or self._recording:
            return
        if idx != self._engine_idx:
            self._switch_to(idx)

    def _switch_to(self, idx):
        engine = self._engines[idx]
        self._menu_status.set_label(f"Loading {engine.name}...")

        if not engine.loaded:
            print(f"Loading {engine.name}...")
            engine.load()

        self._engine_idx = idx
        self._engine = engine
        self._model_radios[idx].set_active(True)
        self._menu_status.set_label(f"ecriv1 — ready [{engine.name}]")
        print(f"Switched to {engine.name}")

    # ── Audio setup ───────────────────────────────────────────────

    def _detect_rate(self):
        for rate in [SAMPLE_RATE, 44100, 48000]:
            try:
                sd.check_input_settings(
                    device=AUDIO_DEVICE, channels=1,
                    dtype="int16", samplerate=rate,
                )
                return rate
            except Exception:
                continue
        raise RuntimeError(f"No supported sample rate for device {AUDIO_DEVICE}")

    # ── Indicator / menu ──────────────────────────────────────────

    def _build_indicator(self):
        self._indicator = AppIndicator3.Indicator.new(
            APP_ID,
            ICON_MIC_OFF,
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self._indicator.set_icon_theme_path(ICON_DIR)
        self._indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self._indicator.set_title("ecriv1")

        menu = Gtk.Menu()

        item_status = Gtk.MenuItem(label=f"ecriv1 — ready [{self._engine.name}]")
        item_status.set_sensitive(False)
        self._menu_status = item_status
        menu.append(item_status)

        menu.append(Gtk.SeparatorMenuItem())

        item_toggle = Gtk.MenuItem(label="Record (F4)")
        item_toggle.connect("activate", lambda _: self._on_f4())
        menu.append(item_toggle)
        self._menu_toggle = item_toggle

        menu.append(Gtk.SeparatorMenuItem())

        # Model submenu
        model_menu = Gtk.Menu()
        model_item = Gtk.MenuItem(label="Model (F3)")
        model_item.set_submenu(model_menu)
        menu.append(model_item)

        self._model_radios = []
        group = None
        for i, engine in enumerate(self._engines):
            radio = Gtk.RadioMenuItem.new_with_label_from_widget(group, engine.name)
            if group is None:
                group = radio
            if i == self._engine_idx:
                radio.set_active(True)
            radio.connect("toggled", self._on_model_menu, i)
            model_menu.append(radio)
            self._model_radios.append(radio)

        menu.append(Gtk.SeparatorMenuItem())

        item_quit = Gtk.MenuItem(label="Quit")
        item_quit.connect("activate", lambda _: Gtk.main_quit())
        menu.append(item_quit)

        menu.show_all()
        self._indicator.set_menu(menu)

    # ── Hotkey / toggle ──────────────────────────────────────────

    def _on_f4(self):
        self._injector.save_active_window()
        GLib.idle_add(self._toggle)

    def _toggle(self):
        if self._recording:
            self._stop()
        else:
            self._start()

    def _start(self):
        self._recording = True
        self._full_text = ""
        self._injected_len = 0

        if not self._engine.loaded:
            self._engine.load()

        # Icon -> red
        self._indicator.set_icon_full(ICON_MIC_ON, "Recording")
        self._menu_status.set_label(f"REC [{self._engine.name}]")
        self._menu_toggle.set_label("Stop (F4)")

        # Start engine session
        self._engine.reset()

        # Drain audio queue
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

        native_block = (int(BLOCK_SIZE * self._native_rate / SAMPLE_RATE)
                        if self._need_resample else BLOCK_SIZE)

        self._stream = sd.RawInputStream(
            samplerate=self._native_rate,
            blocksize=native_block,
            dtype="int16",
            channels=1,
            device=AUDIO_DEVICE,
            callback=self._audio_cb,
        )
        self._stream.start()
        GLib.timeout_add(80, self._process_audio)

    def _stop(self):
        self._recording = False

        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        # Flush remaining text from engine
        remaining = self._engine.finalize()
        if remaining:
            self._full_text += remaining + " "
            new = self._full_text[self._injected_len:]
            if new:
                self._injector.inject(new)

        # Icon -> grey
        self._indicator.set_icon_full(ICON_MIC_OFF, "Idle")
        self._menu_status.set_label(f"ecriv1 — ready [{self._engine.name}]")
        self._menu_toggle.set_label("Record (F4)")

    # ── Audio processing ─────────────────────────────────────────

    def _audio_cb(self, indata, frames, time_info, status):
        if self._recording:
            self._audio_queue.put(bytes(indata))

    def _process_audio(self):
        if not self._recording:
            return False

        import numpy as np

        processed = 0
        while processed < 5:
            try:
                data = self._audio_queue.get_nowait()
            except queue.Empty:
                break
            processed += 1

            if self._need_resample:
                audio = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                n_out = int(len(audio) * SAMPLE_RATE / self._native_rate)
                indices = np.linspace(0, len(audio) - 1, n_out).astype(int)
                data = audio[indices].astype(np.int16).tobytes()

            final, partial = self._engine.feed(data)

            if final:
                self._full_text += final + " "
                self._push_new_text()
            elif partial:
                candidate = self._full_text + partial + " "
                self._push_new_text(candidate)

        return True

    def _push_new_text(self, candidate=None):
        if candidate is None:
            candidate = self._full_text
        if candidate.startswith(self._full_text[:self._injected_len]) and len(candidate) > self._injected_len:
            new = candidate[self._injected_len:]
            if candidate != self._full_text:
                last_space = new.rfind(" ")
                if last_space <= 0:
                    return
                new = new[:last_space + 1]
            if new:
                self._injector.inject(new)
                self._injected_len += len(new)

    def run(self):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, Gtk.main_quit)
        Gtk.main()


def main():
    app = Ecriv1App()
    app.run()


if __name__ == "__main__":
    main()
