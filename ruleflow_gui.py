#!/usr/bin/env python3
"""
RuleFlow Pipeline GUI
Graphical front-end for: rulest_v2.py → concentrator.py → ranker.py
Run: python ruleflow_gui.py
"""

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import subprocess, threading, os, sys, glob, shlex, re, queue

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

BG      = "#1a1b1e"
SURFACE = "#25262b"
CARD    = "#2c2d33"
BORDER  = "#373a40"
FG      = "#e8e8e8"
FG2     = "#909296"
ACCENT  = "#4dabf7"
SUCCESS = "#51cf66"
WARNING = "#ffd43b"
DANGER  = "#ff6b6b"
MONO    = ("Courier New", 10) if sys.platform == "win32" else ("Courier", 10)

# ── ANSI → tkinter tag mapping ────────────────────────────────────────────────
ANSI_COLOURS = {
    "30": "#2c2d33", "31": "#ff6b6b", "32": "#51cf66", "33": "#ffd43b",
    "34": "#4dabf7", "35": "#cc5de8", "36": "#22d3ee", "37": "#e8e8e8",
    "90": "#909296", "91": "#ff8787", "92": "#69db7c", "93": "#ffe066",
    "94": "#74c0fc", "95": "#da77f2", "96": "#38bdf8", "97": "#f8f9fa",
}
ANSI_RE = re.compile(r'\x1b\[([0-9;]*)m')

def parse_ansi(text):
    """Split text+ANSI into list of (chunk, hex_colour|None)."""
    segments = []
    pos = 0
    current_fg = None
    for m in ANSI_RE.finditer(text):
        if m.start() > pos:
            segments.append((text[pos:m.start()], current_fg))
        codes = m.group(1).split(";") if m.group(1) else ["0"]
        for code in codes:
            if code == "0" or code == "":
                current_fg = None
            elif code in ANSI_COLOURS:
                current_fg = ANSI_COLOURS[code]
        pos = m.end()
    if pos < len(text):
        segments.append((text[pos:], current_fg))
    return segments


# ── Widgets ───────────────────────────────────────────────────────────────────

class SectionFrame(tk.LabelFrame):
    def __init__(self, parent, title, **kw):
        super().__init__(parent, text=f"  {title}  ",
                         bg=SURFACE, fg=ACCENT,
                         font=("TkDefaultFont", 9, "bold"),
                         bd=1, relief="flat",
                         highlightbackground=BORDER, highlightthickness=1,
                         padx=10, pady=8, **kw)


class FileRow(tk.Frame):
    def __init__(self, parent, label, **kw):
        super().__init__(parent, bg=SURFACE, **kw)
        tk.Label(self, text=label, bg=SURFACE, fg=FG2,
                 font=("TkDefaultFont", 9), width=22, anchor="w").pack(side="left")
        self.var = tk.StringVar()
        tk.Entry(self, textvariable=self.var, bg=CARD, fg=FG,
                 insertbackground=FG, relief="flat", bd=0,
                 highlightbackground=BORDER, highlightthickness=1,
                 font=MONO, width=42).pack(side="left", padx=(0, 6), ipady=3)
        tk.Button(self, text="Browse", bg=CARD, fg=ACCENT, relief="flat",
                  activebackground=BORDER, activeforeground=ACCENT,
                  cursor="hand2", bd=0, padx=8, pady=3,
                  command=self._browse).pack(side="left")

    def _browse(self):
        p = filedialog.askopenfilename()
        if p:
            self.var.set(p)

    def get(self):
        return self.var.get().strip()


class NumRow(tk.Frame):
    """Label + slider + editable entry — no hard upper cap."""
    def __init__(self, parent, label, from_, slider_to, resolution, default,
                 is_float=False, unit="", **kw):
        super().__init__(parent, bg=SURFACE, **kw)
        self._from = from_
        self._res  = resolution
        self._is_float = is_float
        self._unit = unit

        tk.Label(self, text=label, bg=SURFACE, fg=FG2,
                 font=("TkDefaultFont", 9), width=26, anchor="w").pack(side="left")

        self.var = tk.DoubleVar(value=default)
        self._scale = tk.Scale(self, variable=self.var, from_=from_, to=slider_to,
                               resolution=resolution, orient="horizontal",
                               bg=SURFACE, fg=FG, troughcolor=CARD,
                               highlightthickness=0, showvalue=False, bd=0,
                               activebackground=ACCENT, length=180,
                               command=self._scale_moved)
        self._scale.pack(side="left", padx=(0, 6))

        self._entry_var = tk.StringVar(value=self._fmt(default))
        self._entry = tk.Entry(self, textvariable=self._entry_var,
                               bg=CARD, fg=ACCENT, insertbackground=ACCENT,
                               relief="flat", bd=0,
                               highlightbackground=BORDER, highlightthickness=1,
                               font=MONO, width=9, justify="right")
        self._entry.pack(side="left")
        if unit:
            tk.Label(self, text=unit, bg=SURFACE, fg=FG2,
                     font=("TkDefaultFont", 8)).pack(side="left", padx=(2, 0))

        self._entry.bind("<FocusOut>", self._entry_changed)
        self._entry.bind("<Return>",   self._entry_changed)

    def _fmt(self, v):
        v = float(v)
        return f"{v:.1f}" if self._is_float else str(int(v))

    def _scale_moved(self, v):
        self._entry_var.set(self._fmt(v))

    def _entry_changed(self, _=None):
        try:
            v = float(self._entry_var.get())
            v = max(self._from, v)
            self.var.set(v)
            # clamp scale display to its range without raising error
            sc_to = float(self._scale.cget("to"))
            self._scale.set(min(v, sc_to))
            self._entry_var.set(self._fmt(v))
        except ValueError:
            self._entry_var.set(self._fmt(self.var.get()))

    def set(self, v):
        v = float(v)
        self.var.set(v)
        sc_to = float(self._scale.cget("to"))
        self._scale.set(min(v, sc_to))
        self._entry_var.set(self._fmt(v))

    def get(self):
        try:
            return float(self._entry_var.get())
        except ValueError:
            return float(self.var.get())


# ── Main app ──────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RuleFlow Pipeline  —  v2026")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(800, 700)

        self._process  = None
        self._running  = False
        self._stage    = 0
        self._log_q    = queue.Queue()
        self._devices  = []        # list of (id, description) from --list-devices
        self._dev_var  = tk.IntVar(value=-1)   # -1 = auto

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll_log()   # start log-drain loop

    # ── Log drain (runs on main thread via after()) ───────────────────

    def _poll_log(self):
        try:
            while True:
                item = self._log_q.get_nowait()
                self._do_log_write(item)
        except queue.Empty:
            pass
        self.after(40, self._poll_log)

    # ── UI ────────────────────────────────────────────────────────────

    def _build_ui(self):
        hdr = tk.Frame(self, bg=BG, pady=10)
        hdr.pack(fill="x", padx=16)
        tk.Label(hdr, text="⬡ RULEFLOW PIPELINE", bg=BG, fg=ACCENT,
                 font=("TkDefaultFont", 14, "bold")).pack(side="left")
        tk.Label(hdr, text="rulest → concentrator → ranker", bg=BG, fg=FG2,
                 font=("TkDefaultFont", 9)).pack(side="left", padx=12)

        self._stage_labels = []
        pill_frame = tk.Frame(hdr, bg=BG)
        pill_frame.pack(side="right")
        for name in ["1 · rulest", "2 · concentrator", "3 · ranker"]:
            lbl = tk.Label(pill_frame, text=name, bg=CARD, fg=FG2,
                           font=("TkDefaultFont", 8), padx=10, pady=3)
            lbl.pack(side="left", padx=3)
            self._stage_labels.append(lbl)

        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        cv = tk.Canvas(outer, bg=BG, highlightthickness=0)
        vsb = tk.Scrollbar(outer, orient="vertical", command=cv.yview,
                           bg=CARD, troughcolor=BG)
        cv.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)

        self._inner = tk.Frame(cv, bg=BG)
        wid = cv.create_window((0, 0), window=self._inner, anchor="nw")
        cv.bind("<Configure>", lambda e: [
            cv.configure(scrollregion=cv.bbox("all")),
            cv.itemconfig(wid, width=e.width)])
        self._inner.bind("<Configure>",
                         lambda e: cv.configure(scrollregion=cv.bbox("all")))

        self._build_files()
        self._build_mode()
        self._build_device()
        self._build_ranker()
        self._build_advanced()
        self._build_log()

        bar = tk.Frame(self, bg=BG, pady=8)
        bar.pack(fill="x", padx=16, side="bottom")
        self._run_btn = tk.Button(bar, text="▶  Run Pipeline",
                                  bg=ACCENT, fg="#0a0a0a",
                                  font=("TkDefaultFont", 10, "bold"),
                                  relief="flat", bd=0, padx=20, pady=7,
                                  activebackground="#74c0fc", cursor="hand2",
                                  command=self._run)
        self._run_btn.pack(side="left")
        self._stop_btn = tk.Button(bar, text="■  Stop",
                                   bg=DANGER, fg="#0a0a0a",
                                   font=("TkDefaultFont", 10, "bold"),
                                   relief="flat", bd=0, padx=14, pady=7,
                                   activebackground="#ff8787", cursor="hand2",
                                   state="disabled", command=self._stop)
        self._stop_btn.pack(side="left", padx=(8, 0))
        self._status_lbl = tk.Label(bar, text="Ready", bg=BG, fg=FG2,
                                    font=("TkDefaultFont", 9))
        self._status_lbl.pack(side="right")

    # ── Sections ──────────────────────────────────────────────────────

    def _build_files(self):
        sec = SectionFrame(self._inner, "Step 1 — Input Files")
        sec.pack(fill="x", pady=(0, 8))
        self._base_wl = FileRow(sec, "Base wordlist");   self._base_wl.pack(fill="x", pady=3)
        self._tgt_wl  = FileRow(sec, "Target wordlist"); self._tgt_wl.pack(fill="x", pady=3)
        self._cracked = FileRow(sec, "Cracked passwords"); self._cracked.pack(fill="x", pady=3)

        row = tk.Frame(sec, bg=SURFACE); row.pack(fill="x", pady=(6, 0))
        tk.Label(row, text="Output directory", bg=SURFACE, fg=FG2,
                 font=("TkDefaultFont", 9), width=22, anchor="w").pack(side="left")
        self._outdir_var = tk.StringVar(value=os.getcwd())
        tk.Entry(row, textvariable=self._outdir_var, bg=CARD, fg=FG,
                 insertbackground=FG, relief="flat", bd=0,
                 highlightbackground=BORDER, highlightthickness=1,
                 font=MONO, width=42).pack(side="left", padx=(0, 6), ipady=3)
        tk.Button(row, text="Browse", bg=CARD, fg=ACCENT, relief="flat",
                  activebackground=BORDER, cursor="hand2", bd=0, padx=8, pady=3,
                  command=lambda: self._outdir_var.set(
                      filedialog.askdirectory() or self._outdir_var.get())
                  ).pack(side="left")

    def _build_mode(self):
        sec = SectionFrame(self._inner, "Step 2 — Pipeline Mode")
        sec.pack(fill="x", pady=(0, 8))
        self._mode_var = tk.StringVar(value="balanced")
        self._mode_btns = {}
        bf = tk.Frame(sec, bg=SURFACE); bf.pack(fill="x")
        for label, val, sub in [
            ("Maximum", "maximum", "Best quality"),
            ("Balanced", "balanced", "Recommended"),
            ("Fast", "fast", "Light & quick"),
            ("Custom", "custom", "Full control"),
        ]:
            f = tk.Frame(bf, bg=CARD, relief="flat",
                         highlightbackground=BORDER, highlightthickness=1,
                         padx=12, pady=6, cursor="hand2")
            f.pack(side="left", padx=(0, 8))
            tk.Label(f, text=label, bg=CARD, fg=FG,
                     font=("TkDefaultFont", 10, "bold")).pack()
            tk.Label(f, text=sub, bg=CARD, fg=FG2,
                     font=("TkDefaultFont", 8)).pack()
            for w in (f, *f.winfo_children()):
                w.bind("<Button-1>", lambda e, v=val: self._set_mode(v))
            self._mode_btns[val] = f
        self._set_mode("balanced")

    def _build_device(self):
        sec = SectionFrame(self._inner, "OpenCL Device")
        sec.pack(fill="x", pady=(0, 8))

        top = tk.Frame(sec, bg=SURFACE); top.pack(fill="x")
        tk.Label(top, text="Device", bg=SURFACE, fg=FG2,
                 font=("TkDefaultFont", 9), width=22, anchor="w").pack(side="left")

        self._dev_combo_var = tk.StringVar(value="Auto (let scripts decide)")
        self._dev_combo = tk.OptionMenu(top, self._dev_combo_var, "Auto (let scripts decide)")
        self._dev_combo.config(bg=CARD, fg=FG, activebackground=BORDER,
                               activeforeground=FG, relief="flat",
                               highlightbackground=BORDER, highlightthickness=1,
                               font=("TkDefaultFont", 9))
        self._dev_combo["menu"].config(bg=CARD, fg=FG, activebackground=ACCENT,
                                       activeforeground="#0a0a0a")
        self._dev_combo.pack(side="left", padx=(0, 8))

        tk.Button(top, text="⟳  Scan devices", bg=CARD, fg=ACCENT,
                  relief="flat", bd=0, padx=10, pady=3,
                  cursor="hand2", activebackground=BORDER,
                  command=self._scan_devices).pack(side="left")

        self._dev_status = tk.Label(sec, text="Click 'Scan devices' to detect OpenCL hardware",
                                    bg=SURFACE, fg=FG2, font=("TkDefaultFont", 8), anchor="w")
        self._dev_status.pack(fill="x", pady=(4, 0))

    def _build_ranker(self):
        sec = SectionFrame(self._inner, "Step 3 — Ranker Strategy")
        sec.pack(fill="x", pady=(0, 8))
        self._legacy_var = tk.BooleanVar(value=False)

        row = tk.Frame(sec, bg=SURFACE); row.pack(fill="x")
        tk.Label(row, text="Ranker mode", bg=SURFACE, fg=FG2,
                 font=("TkDefaultFont", 9), width=22, anchor="w").pack(side="left")

        def _tog():
            self._ranker_info.config(
                text="Legacy (exhaustive) — scores every rule against all cracked passwords."
                if self._legacy_var.get()
                else "MAB (adaptive) — multi-armed bandit sampling, faster & smarter.")

        tk.Checkbutton(row, text="Legacy (exhaustive) mode",
                       variable=self._legacy_var,
                       bg=SURFACE, fg=FG, selectcolor=CARD,
                       activebackground=SURFACE, activeforeground=FG,
                       command=_tog).pack(side="left")
        self._ranker_info = tk.Label(sec,
            text="MAB (adaptive) — multi-armed bandit sampling, faster & smarter.",
            bg=SURFACE, fg=FG2, font=("TkDefaultFont", 8), anchor="w")
        self._ranker_info.pack(fill="x", pady=(4, 0))

    def _build_advanced(self):
        sec = SectionFrame(self._inner, "Advanced Parameters")
        sec.pack(fill="x", pady=(0, 8))

        self._adv_visible = tk.BooleanVar(value=False)
        self._adv_body = tk.Frame(sec, bg=SURFACE)

        def _tog():
            if self._adv_visible.get():
                self._adv_body.pack(fill="x")
                self._adv_btn.config(text="▲ Hide advanced")
            else:
                self._adv_body.pack_forget()
                self._adv_btn.config(text="▼ Show advanced")

        self._adv_btn = tk.Button(sec, text="▼ Show advanced",
                                  bg=SURFACE, fg=ACCENT, relief="flat", bd=0,
                                  cursor="hand2", activebackground=SURFACE,
                                  activeforeground=ACCENT,
                                  command=lambda: [
                                      self._adv_visible.set(not self._adv_visible.get()),
                                      _tog()])
        self._adv_btn.pack(anchor="w")

        b = self._adv_body

        def sub(text):
            tk.Label(b, text=text, bg=SURFACE, fg=ACCENT,
                     font=("TkDefaultFont", 8, "bold")).pack(anchor="w", pady=(8, 2))

        def div():
            tk.Frame(b, bg=BORDER, height=1).pack(fill="x", pady=6)

        sub("Rulest core")
        self._adv_depth = NumRow(b, "Max depth (max 31)",       1,   31,   1,   3); self._adv_depth.pack(fill="x", pady=2)
        self._adv_gg    = NumRow(b, "Genetic generations",     20, 1000,  10, 300); self._adv_gg.pack(fill="x", pady=2)
        self._adv_gp    = NumRow(b, "Genetic population",      50, 2000,  50, 600); self._adv_gp.pack(fill="x", pady=2)
        self._adv_th    = NumRow(b, "Target hours",           0.5,   12, 0.5, 2.0, is_float=True, unit="h"); self._adv_th.pack(fill="x", pady=2)

        div()
        sub("Bloom & token-strip")
        self._adv_bm = NumRow(b, "Bloom filter",  100, 4000, 100, 800,  unit="MB"); self._adv_bm.pack(fill="x", pady=2)
        self._adv_s0 = NumRow(b, "Stage-0 workers (0=auto)", 0, 64, 1, 0);         self._adv_s0.pack(fill="x", pady=2)
        self._adv_tp = NumRow(b, "Token-strip max prefix",   1,  12, 1, 4);         self._adv_tp.pack(fill="x", pady=2)
        self._adv_ts = NumRow(b, "Token-strip max suffix",   1,  12, 1, 4);         self._adv_ts.pack(fill="x", pady=2)

        div()
        sub("Ranker")
        self._adv_rk = NumRow(b, "Top rules to keep (K)", 1000, 100000, 1000, 18000); self._adv_rk.pack(fill="x", pady=2)
        self._adv_ms = NumRow(b, "MAB screening trials",     1,     30,    1,     4);  self._adv_ms.pack(fill="x", pady=2)
        self._adv_mf = NumRow(b, "MAB final trials",         1,     50,    1,     8);  self._adv_mf.pack(fill="x", pady=2)

        pr = tk.Frame(b, bg=SURFACE); pr.pack(anchor="w", pady=(6, 2))
        tk.Label(pr, text="Memory preset:", bg=SURFACE, fg=FG2,
                 font=("TkDefaultFont", 9)).pack(side="left", padx=(0, 8))
        self._preset_var = tk.StringVar(value="medium_memory")
        self._preset_pills = []
        for val, lbl in [("low_memory","low"),("medium_memory","medium"),("high_memory","high")]:
            is_sel = val == "medium_memory"
            btn = tk.Button(pr, text=lbl,
                            bg=ACCENT if is_sel else CARD,
                            fg="#0a0a0a" if is_sel else FG2,
                            relief="flat", bd=0, padx=12, pady=3, cursor="hand2",
                            activebackground=ACCENT, activeforeground="#0a0a0a")
            btn.pack(side="left", padx=3)
            pill = {"btn": btn, "data": val}
            self._preset_pills.append(pill)
            btn.config(command=lambda p=pill: self._set_preset(p))

    def _build_log(self):
        sec = SectionFrame(self._inner, "Output Log")
        sec.pack(fill="both", expand=True, pady=(0, 8))

        self._log = scrolledtext.ScrolledText(
            sec, bg="#0d0d0f", fg=FG, insertbackground=FG,
            font=MONO, relief="flat", bd=0,
            highlightbackground=BORDER, highlightthickness=1,
            wrap="word", height=16, state="disabled")
        self._log.pack(fill="both", expand=True)

        # static named tags for common colours
        for name, colour in [
            ("accent",  ACCENT), ("success", SUCCESS),
            ("warning", WARNING), ("danger",  DANGER), ("muted", FG2),
        ]:
            self._log.tag_config(name, foreground=colour)

        br = tk.Frame(sec, bg=SURFACE); br.pack(fill="x", pady=(6, 0))
        tk.Button(br, text="Clear log", bg=CARD, fg=FG2,
                  relief="flat", bd=0, padx=10, pady=3, cursor="hand2",
                  activebackground=BORDER, command=self._clear_log).pack(side="right")

    # ── Helpers ───────────────────────────────────────────────────────

    def _set_mode(self, mode):
        self._mode_var.set(mode)
        presets = {
            "maximum":  dict(depth=3, gg=300, gp=600, th=2.0, bm=800, rk=25000, ms=5, mf=10, pr="high_memory"),
            "balanced": dict(depth=3, gg=300, gp=600, th=2.0, bm=800, rk=18000, ms=4, mf=8,  pr="medium_memory"),
            "fast":     dict(depth=3, gg=300, gp=600, th=2.0, bm=800, rk=12000, ms=3, mf=5,  pr="low_memory"),
        }
        for v, btn in self._mode_btns.items():
            sel = v == mode
            btn.config(highlightbackground=ACCENT if sel else BORDER,
                       highlightthickness=2 if sel else 1)
            for ch in btn.winfo_children():
                is_title = "bold" in str(ch.cget("font"))
                ch.config(fg=ACCENT if sel else (FG if is_title else FG2))

        if mode in presets and hasattr(self, "_adv_depth"):
            p = presets[mode]
            self._adv_depth.set(p["depth"]); self._adv_gg.set(p["gg"])
            self._adv_gp.set(p["gp"]);      self._adv_th.set(p["th"])
            self._adv_bm.set(p["bm"]);      self._adv_rk.set(p["rk"])
            self._adv_ms.set(p["ms"]);       self._adv_mf.set(p["mf"])
            for pill in self._preset_pills:
                is_p = pill["data"] == p["pr"]
                pill["btn"].config(bg=ACCENT if is_p else CARD,
                                   fg="#0a0a0a" if is_p else FG2)
            self._preset_var.set(p["pr"])

    def _set_preset(self, chosen):
        self._preset_var.set(chosen["data"])
        for p in self._preset_pills:
            sel = p["data"] == chosen["data"]
            p["btn"].config(bg=ACCENT if sel else CARD,
                            fg="#0a0a0a" if sel else FG2)

    def _set_stage(self, stage):
        for i, lbl in enumerate(self._stage_labels, start=1):
            if stage == -1:
                lbl.config(bg=DANGER if i == self._stage else CARD,
                           fg="#0a0a0a" if i == self._stage else FG2)
            elif stage == 10:
                lbl.config(bg=SUCCESS, fg="#0a0a0a")
            elif i < stage:
                lbl.config(bg=SUCCESS, fg="#0a0a0a")
            elif i == stage:
                lbl.config(bg=ACCENT, fg="#0a0a0a")
            else:
                lbl.config(bg=CARD, fg=FG2)

    # ── Log writing ───────────────────────────────────────────────────
    # All writes go through the queue so they run on the main thread.

    def _log_write(self, text, tag=None):
        """Thread-safe: enqueue a write."""
        self._log_q.put(("write", text, tag))

    def _do_log_write(self, item):
        """Called only from main thread via _poll_log."""
        kind = item[0]
        if kind == "write":
            _, text, tag = item
            self._log.config(state="normal")
            if tag:
                self._log.insert("end", text, tag)
            else:
                self._log.insert("end", text)
            self._log.see("end")
            self._log.config(state="disabled")
        elif kind == "write_ansi":
            _, text = item
            self._write_ansi(text)
        elif kind == "overwrite_last":
            _, text = item
            self._overwrite_last_line(text)

    def _write_ansi(self, text):
        """Parse ANSI escapes and write coloured segments."""
        self._log.config(state="normal")
        for chunk, colour in parse_ansi(text):
            if not chunk:
                continue
            if colour:
                tag = f"col_{colour.replace('#','')}"
                if tag not in self._log.tag_names():
                    self._log.tag_config(tag, foreground=colour)
                self._log.insert("end", chunk, tag)
            else:
                self._log.insert("end", chunk)
        self._log.see("end")
        self._log.config(state="disabled")

    # ── tqdm progress bar -> clean status line ───────────────────────
    _TQDM_RE = re.compile(
        r"(?P<label>[^:]+):\s*"
        r"(?P<pct>\d+)%.*?"
        r"(?P<done>\d+)/(?P<total>\d+)"
        r".*?\[(?P<elapsed>[^<]+)"
        r"<(?P<eta>[^\]]+)\]"
        r"(?P<rest>.*)"
    )
    _KV_RE = re.compile(r"([a-zA-Z_]+)=([^,]+)")

    def _format_progress(self, raw):
        """Turn a tqdm line into a compact readable status string."""
        clean = ANSI_RE.sub("", raw).strip()
        m = self._TQDM_RE.search(clean)
        if not m:
            return clean, None
        label   = m.group("label").strip()
        pct     = m.group("pct")
        done    = m.group("done")
        total   = m.group("total")
        elapsed = m.group("elapsed").strip()
        eta     = m.group("eta").strip()
        kvs     = self._KV_RE.findall(m.group("rest"))
        kv_str  = "  ".join(f"{k}: {v.strip()}" for k, v in kvs)
        line = f"  {label}  {pct}%  ({done}/{total})  elapsed {elapsed}  eta {eta}"
        if kv_str:
            line += f"  |  {kv_str}"
        colour = SUCCESS if pct == "100" else WARNING
        return line, colour

    def _overwrite_last_line(self, text):
        """Handle \r tqdm lines - replace with clean single status line."""
        clean_line, colour = self._format_progress(text)
        self._log.config(state="normal")
        idx = self._log.search("\n", "end-1c linestart", backwards=True, stopindex="1.0")
        if idx:
            self._log.delete(f"{idx}+1c", "end")
        else:
            self._log.delete("1.0", "end")
        if colour:
            tag = f"col_{colour.replace('#', '')}"
            if tag not in self._log.tag_names():
                self._log.tag_config(tag, foreground=colour)
            self._log.insert("end", clean_line, tag)
        else:
            for chunk, col in parse_ansi(text):
                if not chunk:
                    continue
                if col:
                    t = f"col_{col.replace('#', '')}"
                    if t not in self._log.tag_names():
                        self._log.tag_config(t, foreground=col)
                    self._log.insert("end", chunk, t)
                else:
                    self._log.insert("end", chunk)
        self._log.see("end")
        self._log.config(state="disabled")

    def _clear_log(self):
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")

    # ── Device scanning ───────────────────────────────────────────────

    def _scan_devices(self):
        self._dev_status.config(text="Scanning…", fg=WARNING)
        threading.Thread(target=self._scan_thread, daemon=True).start()

    def _scan_thread(self):
        py = sys.executable
        rulest_py = os.path.join(SCRIPT_DIR, "rulest_v2.py")
        try:
            result = subprocess.run(
                [py, rulest_py, "--list-devices"],
                capture_output=True, text=True, timeout=30)
            raw = result.stdout + result.stderr
        except Exception as e:
            self.after(0, lambda: self._dev_status.config(
                text=f"Scan failed: {e}", fg=DANGER))
            return

        # strip ANSI
        clean = ANSI_RE.sub("", raw)
        devices = [("auto", "Auto (let scripts decide)")]
        for line in clean.splitlines():
            # match lines like "  [0] NVIDIA GeForce ..." or "Device 0: ..."
            m = re.search(r'\[?\b(\d+)\]?\s*[:\-]?\s*(.+)', line)
            if m and any(k in line.lower() for k in ["nvidia","amd","intel","cpu","gpu","opencl","geforce","radeon","iris","hd graphics","apple"]):
                dev_id = m.group(1)
                desc   = m.group(2).strip()
                devices.append((dev_id, f"[{dev_id}] {desc}"))

        if len(devices) == 1:
            # fallback: show raw output
            devices.append(("auto", "Could not parse devices — check log"))
            self.after(0, lambda r=clean: self._log_write(r, "muted"))

        self._devices = devices
        self.after(0, lambda: self._populate_devices(devices, clean))

    def _populate_devices(self, devices, raw):
        menu = self._dev_combo["menu"]
        menu.delete(0, "end")
        for dev_id, label in devices:
            menu.add_command(
                label=label,
                command=lambda l=label, d=dev_id: [
                    self._dev_combo_var.set(l),
                    self._dev_var.set(-1 if d == "auto" else int(d))])
        self._dev_combo_var.set(devices[0][1])
        self._dev_var.set(-1)
        count = len(devices) - 1
        self._dev_status.config(
            text=f"Found {count} device(s). Select one or leave on Auto." if count > 0
            else "No devices parsed — see log for raw output.",
            fg=SUCCESS if count > 0 else WARNING)
        # dump raw to log
        self._log_write("\n── Device scan output ──\n", "muted")
        self._log_write(ANSI_RE.sub("", raw), "muted")
        self._log_write("────────────────────────\n", "muted")

    # ── Pipeline ──────────────────────────────────────────────────────

    def _validate(self):
        for label, path in [("Base wordlist", self._base_wl.get()),
                             ("Target wordlist", self._tgt_wl.get()),
                             ("Cracked passwords", self._cracked.get())]:
            if not path:
                messagebox.showerror("Missing input", f"{label} path is required.")
                return False
            if not os.path.isfile(path):
                messagebox.showerror("File not found",
                    f"{label}:\n{path}\n\nFile does not exist.")
                return False
        return True

    def _run(self):
        if self._running: return
        if not self._validate(): return
        self._running = True
        self._stage = 0
        self._run_btn.config(state="disabled")
        self._stop_btn.config(state="normal")
        self._clear_log()
        threading.Thread(target=self._pipeline_thread, daemon=True).start()

    def _stop(self):
        if self._process:
            self._log_write("\n[Stopping…]\n", "warning")
            try: self._process.terminate()
            except Exception: pass
        self._finish(aborted=True)

    def _finish(self, aborted=False, error=False):
        self._running = False
        self._process = None
        self._run_btn.config(state="normal")
        self._stop_btn.config(state="disabled")
        sep = "\u2500" * 60
        if aborted:
            self._set_stage(-1)
            self._status_lbl.config(text="Stopped", fg=WARNING)
            self._log_write(f"\n{sep}\n  Pipeline stopped by user.\n{sep}\n", "warning")
        elif error:
            self._set_stage(-1)
            self._status_lbl.config(text="Error", fg=DANGER)
            self._log_write(f"\n{sep}\n  Pipeline failed. Check output above for details.\n{sep}\n", "danger")
        else:
            self._set_stage(10)
            self._status_lbl.config(text="Done \u2713", fg=SUCCESS)

    def _run_step(self, cmd, label):
        """Run a subprocess and stream its output — handles \\r (tqdm) and ANSI."""
        self._log_q.put(("write", f"\n{'─'*60}\n", "muted"))
        self._log_q.put(("write", f"  {label}\n", "accent"))
        self._log_q.put(("write", f"{'─'*60}\n", "muted"))
        self._log_q.put(("write",
            f"$ {' '.join(shlex.quote(str(a)) for a in cmd)}\n\n", "muted"))

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"  # force line-buffered output

        try:
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,  # closed stdin -> input() raises EOFError immediately
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,           # raw bytes
                cwd=self._outdir_var.get(),
                env=env,
            )
        except FileNotFoundError as e:
            self._log_q.put(("write", f"\nError: {e}\n", "danger"))
            self._process = None
            return -1

        # Read byte-by-byte: avoids blocking on read(N) between pipeline stages.
        # tqdm writes \r to overwrite the progress line; \n advances to next line.
        line_buf = b""
        fd = self._process.stdout
        while True:
            byte = fd.read(1)
            if not byte:
                break
            if byte == b'\r':
                next_b = fd.read(1)
                if next_b == b'\n':
                    # Windows \r\n — treat as normal newline
                    line_buf += b'\n'
                    self._log_q.put(("write_ansi",
                                     line_buf.decode("utf-8", errors="replace")))
                    line_buf = b""
                else:
                    # bare \r — tqdm in-place update, overwrite last line
                    if line_buf.strip():
                        self._log_q.put(("overwrite_last",
                                         line_buf.decode("utf-8", errors="replace")))
                    line_buf = b""
                    if next_b:
                        line_buf += next_b
            elif byte == b'\n':
                line_buf += byte
                self._log_q.put(("write_ansi",
                                  line_buf.decode("utf-8", errors="replace")))
                line_buf = b""
            else:
                line_buf += byte
        if line_buf:
            self._log_q.put(("write_ansi",
                              line_buf.decode("utf-8", errors="replace")))

        self._process.wait()
        rc = self._process.returncode
        self._process = None
        return rc

    def _device_args(self):
        """Return --device N args if a specific device was chosen."""
        dev = self._dev_var.get()
        return ["--device", str(dev)] if dev >= 0 else []

    def _pipeline_thread(self):
        outdir  = self._outdir_var.get()
        base_wl = self._base_wl.get()
        tgt_wl  = self._tgt_wl.get()
        cracked = self._cracked.get()
        legacy  = self._legacy_var.get()
        depth   = int(self._adv_depth.get())
        gen_gen = int(self._adv_gg.get())
        gen_pop = int(self._adv_gp.get())
        th      = float(self._adv_th.get())
        bm      = int(self._adv_bm.get())
        s0      = int(self._adv_s0.get())
        tok_p   = int(self._adv_tp.get())
        tok_s   = int(self._adv_ts.get())
        rk      = int(self._adv_rk.get())
        ms      = int(self._adv_ms.get())
        mf      = int(self._adv_mf.get())
        preset  = self._preset_var.get()
        py      = sys.executable

        s1  = os.path.join(outdir, "stage1_raw.rule")
        s2b = os.path.join(outdir, "stage2_cleaned")
        s3  = os.path.join(outdir, "stage3_ranking.csv")

        rulest_py = os.path.join(SCRIPT_DIR, "rulest_v2.py")
        conc_py   = os.path.join(SCRIPT_DIR, "concentrator.py")
        rank_py   = os.path.join(SCRIPT_DIR, "ranker.py")
        dev_args  = self._device_args()

        # ── 1: Rulest ────────────────────────────────────────────────
        self.after(0, lambda: self._set_stage(1))
        self.after(0, lambda: self._status_lbl.config(text="Running rulest…", fg=ACCENT))
        self._stage = 1
        rc = self._run_step([
            py, rulest_py, base_wl, tgt_wl,
            "-o", s1,
            "--max-depth", str(depth),
            "--token-strip",
            "--genetic",
            "--genetic-generations", str(gen_gen),
            "--genetic-pop", str(gen_pop),
            "--target-hours", str(th),
            "--bloom-mb", str(bm),
            "--token-strip-max-prefix", str(tok_p),
            "--token-strip-max-suffix", str(tok_s),
            "--token-strip-workers", str(s0),
        ] + dev_args, "[1/3] Rulest")
        if rc != 0:
            self.after(0, lambda: self._log_write(
                f"\nRulest exited with code {rc}\n", "danger"))
            self.after(0, lambda: self._finish(error=True)); return

        # ── 2: Concentrator ──────────────────────────────────────────
        self.after(0, lambda: self._set_stage(2))
        self.after(0, lambda: self._status_lbl.config(
            text="Running concentrator…", fg=ACCENT))
        self._stage = 2
        rc = self._run_step([
            py, conc_py,
            "-p", s1,
            "--output_base_name", s2b,
            "--output-format", "expanded",
        ], "[2/3] Concentrator")
        if rc != 0:
            self.after(0, lambda: self._log_write(
                f"\nConcentrator exited with code {rc}\n", "danger"))
            self.after(0, lambda: self._finish(error=True)); return

        matches = glob.glob(s2b + "*.rule")
        if not matches:
            # EOFError auto-save path (stdin closed) writes a timestamped
            # filename instead of output_base_name -- fall back to the most
            # recently modified .rule file in the output directory.
            fallback = sorted(
                glob.glob(os.path.join(outdir, "*.rule")),
                key=os.path.getmtime, reverse=True
            )
            fallback = [f for f in fallback if os.path.abspath(f) != os.path.abspath(s1)]
            if fallback:
                matches = [fallback[0]]
                self._log_q.put(("write",
                    f"\n[!] Expected name not found; using most recent rule file instead: {matches[0]}\n",
                    "warning"))
        if not matches:
            self.after(0, lambda: self._log_write(
                f"\nCould not find concentrator output: {s2b}*.rule\n", "danger"))
            self.after(0, lambda: self._finish(error=True)); return
        cleaned = matches[0]
        self._log_q.put(("write", f"\n→ Using: {cleaned}\n", "success"))

        # ── 3: Ranker ────────────────────────────────────────────────
        self.after(0, lambda: self._set_stage(3))
        self.after(0, lambda: self._status_lbl.config(text="Running ranker…", fg=ACCENT))
        self._stage = 3
        cmd3 = [
            py, rank_py,
            "-w", base_wl,
            "-r", cleaned,
            "-c", cracked,
            "-o", s3,
            "-k", str(rk),
            "--preset", preset,
        ] + dev_args
        if legacy:
            cmd3.append("--legacy")
        else:
            cmd3 += ["--mab-screening-trials", str(ms),
                     "--mab-final-trials",      str(mf)]
        rc = self._run_step(cmd3, "[3/3] Ranker")
        if rc != 0:
            self.after(0, lambda: self._log_write(
                f"\nRanker exited with code {rc}\n", "danger"))
            self.after(0, lambda: self._finish(error=True)); return

        self._log_q.put(("write",
            f"\n{'─'*60}\n  Pipeline complete!\n  Results → {s3}\n{'─'*60}\n",
            "success"))
        self.after(0, self._finish)

    def _on_close(self):
        if self._running:
            if messagebox.askyesno("Quit", "Pipeline is running. Stop and quit?"):
                self._stop(); self.destroy()
        else:
            self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
