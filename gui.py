"""
gui.py — Ghost Typer Tk mini-GUI (Windows-first).
Presets + WPM slider + Start/Pause/Resume/Soft-stop + progress.
"""

import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from core.controller import SessionController
from core.engine import TypingEngine
from core.focus_guard import BACKEND_AVAILABLE, FocusGuard
from core.inputs import estimate_time, preview_text
from core.profiles import PROFILE_ORDER, PROFILES, WPM_MAX, WPM_MIN, clamp_wpm, get_profile


def _load_icon(root: tk.Tk) -> None:
    for candidate in (os.path.join("assets", "icon.ico"), os.path.join("assets", "icon.png")):
        try:
            if os.path.exists(candidate):
                if candidate.endswith(".ico"):
                    root.icon_bitmap(candidate)
                else:
                    img = tk.PhotoImage(file=candidate)
                    root.iconphoto(True, img)
                    root._icon_img = img  # keep ref
                return
        except Exception:
            continue


class GhostTyperApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Ghost Typer v2.10.0 — human-like typing")
        self.geometry("560x620")
        self.resizable(True, True)
        _load_icon(self)

        self.controller = SessionController()
        self.controller.on_interference = self._on_interference
        self._status_msg = tk.StringVar(value="Paste text, pick a speed, press Start.")
        self._progress_var = tk.DoubleVar(value=0.0)
        self._table_active = False

        self._build_widgets()
        self._poll_ui()

    # ---------------- UI layout ---------------- #

    def _build_widgets(self):
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)

        # Preset row
        row1 = ttk.Frame(frm)
        row1.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(row1, text="Preset:").pack(side=tk.LEFT)
        self.preset_var = tk.StringVar(value="normal")
        preset_names = [p for p in PROFILE_ORDER if p in PROFILES]
        self.preset_box = ttk.Combobox(row1, textvariable=self.preset_var,
                                       values=preset_names, state="readonly", width=14)
        self.preset_box.pack(side=tk.LEFT, padx=6)
        self.preset_box.bind("<<ComboboxSelected>>", lambda _e: self._on_preset())
        self.preset_desc = tk.StringVar(value=PROFILES["normal"]["description"])
        ttk.Label(row1, textvariable=self.preset_desc, wraplength=300).pack(side=tk.LEFT, padx=6)

        # WPM slider row
        row2 = ttk.Frame(frm)
        row2.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(row2, text="Speed:").pack(side=tk.LEFT)
        self.wpm_var = tk.IntVar(value=65)
        self.wpm_slider = ttk.Scale(row2, from_=WPM_MIN, to=WPM_MAX, orient=tk.HORIZONTAL,
                                    variable=self.wpm_var, command=lambda _v: self._on_wpm())
        self.wpm_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self.wpm_label = tk.StringVar(value="65 WPM")
        ttk.Label(row2, textvariable=self.wpm_label, width=10).pack(side=tk.LEFT)

        # Options row
        row3 = ttk.Frame(frm)
        row3.pack(fill=tk.X, pady=(0, 6))
        self.chat_var = tk.BooleanVar(value=False)
        self.focus_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row3, text="Chat mode (Shift+Enter)", variable=self.chat_var).pack(side=tk.LEFT)
        ttk.Checkbutton(row3, text="Focus lock", variable=self.focus_var).pack(side=tk.LEFT, padx=12)
        ttk.Label(row3, text="Countdown:").pack(side=tk.LEFT)
        self.countdown_var = tk.IntVar(value=5)
        ttk.Spinbox(row3, from_=2, to=15, textvariable=self.countdown_var, width=4).pack(side=tk.LEFT, padx=4)

        # Rich-text row
        row4 = ttk.Frame(frm)
        row4.pack(fill=tk.X, pady=(0, 6))
        self.rich_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row4, text="Rich (**bold**, # headings)",
                        variable=self.rich_var).pack(side=tk.LEFT)
        ttk.Label(row4, text="App:").pack(side=tk.LEFT, padx=(12, 2))
        self.rich_app_var = tk.StringVar(value="word")
        ttk.Combobox(row4, textvariable=self.rich_app_var, values=["word", "docs"],
                     state="readonly", width=7).pack(side=tk.LEFT)
        self.keepfmt_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row4, text="Paste as-is",
                        variable=self.keepfmt_var).pack(side=tk.LEFT, padx=(12, 0))

        # Text box
        ttk.Label(frm, text="Text to type:").pack(anchor=tk.W)
        self.text_box = tk.Text(frm, height=12, wrap=tk.WORD)
        self.text_box.pack(fill=tk.BOTH, expand=True, pady=4)

        btn_row = ttk.Frame(frm)
        btn_row.pack(fill=tk.X, pady=4)
        ttk.Button(btn_row, text="Paste clipboard", command=self._paste_clipboard).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Clear", command=lambda: self.text_box.delete("1.0", tk.END)).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_row, text="Copy remaining", command=self._copy_remaining).pack(side=tk.LEFT)

        # CSV table-fill row
        csv_row = ttk.Frame(frm)
        csv_row.pack(fill=tk.X, pady=4)
        ttk.Label(csv_row, text="CSV:").pack(side=tk.LEFT)
        self.csv_var = tk.StringVar(value="")
        ttk.Entry(csv_row, textvariable=self.csv_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(csv_row, text="Browse", command=self._browse_csv).pack(side=tk.LEFT)
        self.rowkey_var = tk.StringVar(value="enter")
        ttk.Combobox(csv_row, textvariable=self.rowkey_var, values=["enter", "tab", "down"],
                     state="readonly", width=7).pack(side=tk.LEFT, padx=6)
        ttk.Button(csv_row, text="Fill table", command=self.on_fill_table_btn).pack(side=tk.LEFT)

        # Action buttons
        act = ttk.Frame(frm)
        act.pack(fill=tk.X, pady=6)
        self.start_btn = ttk.Button(act, text="Start / Resume (Ctrl+Alt+S)", command=self.on_start_btn)
        self.start_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.pause_btn = ttk.Button(act, text="Pause", command=self.on_pause_btn)
        self.pause_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self.stop_btn = ttk.Button(act, text="Stop (keeps place)", command=self.on_stop_btn)
        self.stop_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Progress
        self.progress = ttk.Progressbar(frm, variable=self._progress_var, maximum=100)
        self.progress.pack(fill=tk.X, pady=(4, 2))
        ttk.Label(frm, textvariable=self._status_msg, wraplength=520).pack(anchor=tk.W)

        # Hotkeys hint
        hint = ("Hotkeys still work globally: Ctrl+Alt+S start/resume · Ctrl+Alt+P pause · Esc soft-stop. "
                "Click your target box during countdown.")
        ttk.Label(frm, text=hint, wraplength=520, foreground="gray").pack(anchor=tk.W, pady=(6, 0))

    # ---------------- helpers ---------------- #

    def _on_preset(self):
        try:
            p = PROFILES.get(self.preset_var.get(), {})
            self.preset_desc.set(p.get("description", ""))
            if "wpm" in p:
                self.wpm_var.set(int(p["wpm"]))
                self._on_wpm()
        except Exception:
            pass

    def _on_wpm(self):
        try:
            self.wpm_label.set(f"{int(float(self.wpm_var.get()))} WPM")
        except Exception:
            pass

    def _set_status(self, msg: str):
        self._status_msg.set(msg)

    def _on_interference(self):
        self._set_status("You typed — auto-paused. Press Pause/Resume to continue.")

    def _paste_clipboard(self):
        try:
            import pyperclip
            self.text_box.insert(tk.END, pyperclip.paste())
        except Exception as e:
            messagebox.showerror("Clipboard", f"Could not paste: {e}")

    def _copy_remaining(self):
        rem = self.controller.get_remaining_text()
        if not rem:
            messagebox.showinfo("Remaining", "Nothing to resume — no soft-stopped session.")
            return
        try:
            import pyperclip
            pyperclip.copy(rem)
            self._set_status(f"Copied remaining {len(rem)} chars to clipboard.")
        except Exception as e:
            messagebox.showerror("Clipboard", f"Could not copy: {e}")

    def _current_profile(self) -> dict:
        try:
            profile = get_profile(self.preset_var.get())
        except Exception:
            profile = get_profile("normal")
        profile["wpm"] = clamp_wpm(int(float(self.wpm_var.get())))
        profile["chat_mode"] = bool(self.chat_var.get())
        return profile

    def _current_text(self) -> str:
        return self.text_box.get("1.0", tk.END).strip("\n")

    # ---------------- session ---------------- #

    def on_start_btn(self):
        if self.controller.is_typing():
            self._set_status("Already typing — Stop first to restart.")
            return
        # Resume path keeps the original buffer.
        if self.controller.has_resume():
            info = self.controller.get_resume_info()
            self._set_status(f"Resuming from word {info['word_index']}/{info['word_total']}… click target box!")
            threading.Thread(target=self._countdown_then_resume, daemon=True).start()
            return
        text = self._current_text()
        if not text.strip():
            # Fall back to clipboard so empty box isn't a dead end.
            try:
                import pyperclip
                text = (pyperclip.paste() or "").strip()
                if text:
                    self.text_box.delete("1.0", tk.END)
                    self.text_box.insert("1.0", text)
            except Exception:
                pass
        if not text.strip():
            messagebox.showwarning("No text", "Paste text first (or copy to clipboard).")
            return
        profile = self._current_profile()
        rich_app = self.rich_app_var.get() if self.rich_var.get() else None
        keep_fmt = bool(self.keepfmt_var.get())
        self._set_status(f"Starting in {self.countdown_var.get()}s — click your target box NOW!")
        threading.Thread(target=self._countdown_then_start,
                         args=(text, profile, rich_app, keep_fmt), daemon=True).start()

    def _countdown_then_start(self, text: str, profile: dict, rich_app=None,
                              keep_fmt: bool = False):
        secs = max(2, int(self.countdown_var.get() or 5))
        for i in range(secs, 0, -1):
            if self.controller.stop_flag[0]:
                return
            self._status_msg.set(f"Typing starts in {i}s — click your target box NOW!")
            time.sleep(1)
        if self.controller.stop_flag[0]:
            return
        use_focus = bool(self.focus_var.get())
        self.controller.start_session(self._run_session, text, profile,
                                      self.controller, use_focus,
                                      rich_app=rich_app, paste_through=keep_fmt)

    def _countdown_then_resume(self):
        for i in range(3, 0, -1):
            if self.controller.stop_flag[0]:
                return
            self._status_msg.set(f"Resuming in {i}s — click your target box NOW!")
            time.sleep(1)
        if self.controller.stop_flag[0]:
            return
        use_focus = bool(self.focus_var.get())
        rich_kw = {}
        if self.controller.last_rich_source:
            rich_kw = {"rich_app": self.controller.last_rich_app}
        self.controller.resume_session(
            self._run_session,
            self.controller.last_rich_source or self.controller.last_text,
            self.controller.last_profile,
            self.controller, use_focus,
            **rich_kw,
        )

    def _browse_csv(self):
        path = filedialog.askopenfilename(title="Choose CSV table",
                                          filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if path:
            self.csv_var.set(path)

    def on_fill_table_btn(self):
        if self.controller.is_typing():
            self._set_status("Already typing — Stop first.")
            return
        path = self.csv_var.get().strip()
        if not path:
            messagebox.showwarning("No CSV", "Pick a CSV file first (Browse).")
            return
        try:
            from core.tables import load_csv
            rows = load_csv(path)
        except (FileNotFoundError, ValueError) as e:
            messagebox.showerror("CSV", str(e))
            return
        profile = self._current_profile()
        profile['errors_enabled'] = False
        profile['error_rate'] = 0.0
        profile['transposition_rate'] = 0.0
        self._set_status(f"Table fill starts in {self.countdown_var.get()}s — click the FIRST cell NOW!")
        threading.Thread(target=self._countdown_then_fill,
                         args=(rows, profile), daemon=True).start()

    def _countdown_then_fill(self, rows: list, profile: dict):
        secs = max(2, int(self.countdown_var.get() or 5))
        for i in range(secs, 0, -1):
            if self.controller.stop_flag[0]:
                return
            self._status_msg.set(f"Table fill starts in {i}s — click the FIRST cell NOW!")
            time.sleep(1)
        if self.controller.stop_flag[0]:
            return
        self.controller.start_session(self._run_table, rows, profile, self.controller)

    def _run_table(self, rows: list, profile: dict, controller):
        from core.tables import fill_table
        self._table_active = True
        focus_guard = FocusGuard(controller.pause_flag, controller.stop_flag)
        if bool(self.focus_var.get()) and BACKEND_AVAILABLE:
            try:
                focus_guard.lock_to_current_window()
                focus_guard.start_watching()
            except Exception:
                pass
        engine = TypingEngine(profile, controller.stop_flag, emit_hook=controller.mark_own_emit)
        controller.start_interference_watch()

        def progress(done: int, tot: int, r: int, c: int):
            controller.wait_if_paused()
            controller.update_index(done, tot)
            self._status_msg.set(f"Table: cell {done}/{tot} (row {r + 1}/{len(rows)})")

        finished, (rr, cc) = fill_table(
            engine, rows, col_nav='tab', row_nav=self.rowkey_var.get(),
            stop_flag=controller.stop_flag,
            pause_checker=controller.wait_if_paused,
            progress_callback=progress,
        )
        try:
            focus_guard.stop_watching()
        except Exception:
            pass
        if finished:
            controller.clear_session()
            self._status_msg.set("Done! Table filled.")
        else:
            self._status_msg.set(f"Soft-stopped at row {rr + 1}, col {cc + 1} of the CSV.")
        self._table_active = False

    def _run_session(self, text, profile, controller, use_focus_lock=True, start_index=0,
                     rich_app=None, paste_through: bool = False):
        from core.richtext import strip_rich
        plain = strip_rich(text) if rich_app else text
        is_resume = start_index > 0
        if not is_resume:
            controller.save_session(plain, profile,
                                    rich_source=text if rich_app else None,
                                    rich_app=rich_app or 'word')
        else:
            controller.last_text = plain
            controller.last_profile = dict(profile)
            controller.last_total = len(plain)
            controller.update_index(start_index, len(plain))
        focus_guard = FocusGuard(controller.pause_flag, controller.stop_flag)
        if use_focus_lock and BACKEND_AVAILABLE:
            try:
                focus_guard.lock_to_current_window()
                focus_guard.start_watching()
            except Exception:
                pass
        engine = TypingEngine(profile, controller.stop_flag, emit_hook=controller.mark_own_emit)
        controller.start_interference_watch()

        if paste_through:
            self._status_msg.set("Pasting clipboard as-is — formatting preserved.")
            engine._tap_ctrl('v')
            time.sleep(0.5)
            try:
                focus_guard.stop_watching()
            except Exception:
                pass
            controller.clear_session()
            self._status_msg.set("Done! Pasted.")
            return

        def progress(cur, tot):
            controller.wait_if_paused()
            w = engine.get_word_progress()
            controller.update_index(cur, tot, w[0], w[1])

        if rich_app:
            ok = engine.type_rich(text, app=rich_app, progress_callback=progress,
                                  start_index=start_index)
        else:
            ok = engine.type_text(text, progress_callback=progress, start_index=start_index)
        try:
            focus_guard.stop_watching()
        except Exception:
            pass
        if ok:
            controller.clear_session()
            self._status_msg.set("Done!")
        else:
            info = controller.get_resume_info()
            self._status_msg.set(
                f"Soft-stopped at char {info['index']}/{info['total']} "
                f"(word {info['word_index']}/{info['word_total']}). "
                f"Press Start to resume. Next: '{info['remaining_preview']}'"
            )

    def on_pause_btn(self):
        self.controller.toggle_pause()
        self._set_status("Paused." if self.controller.is_paused() else "Resumed.")

    def on_stop_btn(self):
        info = self.controller.stop_session(soft=True)
        if info.get("total"):
            self._set_status(f"Soft-stopped at word {info['word_index']}/{info['word_total']} — Start resumes.")
        else:
            self._set_status("Stopped.")

    def _poll_ui(self):
        try:
            total = self.controller.last_total or 0
            idx = self.controller.last_index or 0
            if total > 0:
                pct = (idx / total) * 100
                self._progress_var.set(pct)
                if self.controller.is_typing() and not self._table_active:
                    wi, wt = self.controller.last_word_index, self.controller.last_word_total
                    self._set_status(f"Typing… {idx}/{total} chars, word {wi}/{wt} ({pct:.0f}%) — {preview_text(self.controller.last_text[idx:idx+60])}")
            else:
                # Show estimate for fresh text
                txt = self._current_text()
                if txt:
                    try:
                        wpm = int(float(self.wpm_var.get()))
                        self._set_status(f"Ready: {len(txt)} chars, est. {estimate_time(txt, wpm)}. {self._status_msg.get() if self.controller.is_typing() else ''}".strip())
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            self.after(200, self._poll_ui)


def launch_gui():
    app = GhostTyperApp()
    # Global hotkeys mirror CLI while GUI is open (best effort).
    try:
        def _gui_start():
            app.after(0, app.on_start_btn)

        def _gui_pause():
            app.after(0, app.on_pause_btn)

        def _gui_stop():
            app.after(0, app.on_stop_btn)

        app.controller.on_start = _gui_start
        app.controller.on_pause_toggle = None
        app.controller.on_stop = lambda _info=None: app.after(0, app.on_stop_btn)
        app.controller.start_listening()
    except Exception:
        pass
    app.mainloop()
