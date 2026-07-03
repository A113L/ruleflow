#!/usr/bin/env python3
"""
RCR v0.3  —  RuleFlow Chain Runner
Graphical front-end for: rulest_v2.py -> concentrator.py -> ranker.py
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import subprocess
import threading
import os
import sys
import glob
import shlex
import re
import queue
import time
import gc
import select
from dataclasses import dataclass
from typing import Optional, List, Tuple, Callable

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_TITLE = "RCR v0.3 - RuleFlow Chain Runner"

# ── Theme ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Theme:
    bg: str = "#0f1115"
    surface: str = "#181a20"
    card: str = "#1e2128"
    elevated: str = "#252830"
    border: str = "#2f333c"
    fg: str = "#e4e6eb"
    fg2: str = "#8b909e"
    accent: str = "#58a6ff"
    accent_hover: str = "#79b8ff"
    success: str = "#3fb950"
    warning: str = "#d29922"
    danger: str = "#f85149"
    info: str = "#a371f7"

THEME = Theme()
MONO = ("JetBrains Mono", 9) if sys.platform != "win32" else ("Consolas", 9)

# ── ANSI → tkinter mapping ───────────────────────────────────────────────────

ANSI_COLOURS = {
    "30": "#2f333c", "31": "#f85149", "32": "#3fb950", "33": "#d29922",
    "34": "#58a6ff", "35": "#bc8cff", "36": "#39c5cf", "37": "#e4e6eb",
    "90": "#6e7681", "91": "#ff7b72", "92": "#7ee787", "93": "#ffa657",
    "94": "#79b8ff", "95": "#d2a8ff", "96": "#56d4dd", "97": "#ffffff",
}
ANSI_RE = re.compile(r'\x1b\[([0-9;]*)m')


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def parse_ansi_segments(text: str) -> List[Tuple[str, Optional[str]]]:
    """Split text into (chunk, colour_hex) segments."""
    segments = []
    pos = 0
    current_fg = None
    for m in ANSI_RE.finditer(text):
        if m.start() > pos:
            segments.append((text[pos:m.start()], current_fg))
        codes = m.group(1).split(";") if m.group(1) else ["0"]
        for code in codes:
            if code in ("0", ""):
                current_fg = None
            elif code in ANSI_COLOURS:
                current_fg = ANSI_COLOURS[code]
        pos = m.end()
    if pos < len(text):
        segments.append((text[pos:], current_fg))
    return segments


OOM_PATTERNS = re.compile(
    r"memoryerror|out of memory|bad_alloc|allocation failed|"
    r"failed to allocate|cl_mem|clerror|memory allocation failed|"
    r"gpu memory allocation failed|killed\b",
    re.IGNORECASE,
)


# ── Memory Monitor ───────────────────────────────────────────────────────────

class MemoryMonitor:
    def __init__(self, threshold_mb: float = 6144.0):
        self.threshold_mb = threshold_mb
        self._have_psutil = False
        try:
            import psutil
            self._have_psutil = True
            self._psutil = psutil
            self._self_proc = psutil.Process()
        except ImportError:
            self._psutil = None
            self._self_proc = None
        self._child_pid: Optional[int] = None

    def set_child_pid(self, pid: Optional[int]):
        self._child_pid = pid

    def current_mb(self) -> float:
        if not self._have_psutil:
            return 0.0
        total = 0.0
        try:
            total += self._self_proc.memory_info().rss
        except Exception:
            pass
        if self._child_pid:
            try:
                p = self._psutil.Process(self._child_pid)
                total += p.memory_info().rss
                for c in p.children(recursive=True):
                    try:
                        total += c.memory_info().rss
                    except Exception:
                        pass
            except Exception:
                pass
        return total / (1024 * 1024)

    def is_under_pressure(self) -> bool:
        return self.current_mb() > self.threshold_mb

    def format(self) -> str:
        mb = self.current_mb()
        if not self._have_psutil:
            return "n/a (psutil not installed)"
        if mb > 1024:
            return f"{mb/1024:.2f} GB"
        return f"{mb:.0f} MB"


# ── Bounded Log Queue ────────────────────────────────────────────────────────

class BoundedLogQueue:
    def __init__(self, maxsize: int = 4000):
        self._queue: queue.Queue = queue.Queue(maxsize=maxsize)
        self._dropped = 0
        self._lock = threading.Lock()

    def put(self, item, block: bool = False, timeout: float = 0.1) -> bool:
        try:
            self._queue.put(item, block=block, timeout=timeout)
            return True
        except queue.Full:
            with self._lock:
                self._dropped += 1
            return False

    def get_nowait(self):
        return self._queue.get_nowait()

    def clear_dropped(self) -> int:
        with self._lock:
            d = self._dropped
            self._dropped = 0
            return d


# ── Process Wrapper ──────────────────────────────────────────────────────────

class ManagedProcess:
    def __init__(self):
        self._proc: Optional[subprocess.Popen] = None
        self._terminated = False
        self._lock = threading.Lock()

    @property
    def pid(self) -> Optional[int]:
        return self._proc.pid if self._proc else None

    def start(self, cmd: List[str], cwd: str, env: dict) -> bool:
        with self._lock:
            if self._proc is not None:
                return False
            try:
                self._proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=0,
                    cwd=cwd,
                    env=env,
                )
                self._terminated = False
                return True
            except Exception as e:
                print(f"Failed to start process: {e}", file=sys.stderr)
                return False

    def iter_events(self, timeout: float = 0.3, chunk_size: int = 4096):
        """Yield ('line', text) for every chunk separated by either \r or \n."""
        if self._proc is None or self._proc.stdout is None:
            return
        fd = self._proc.stdout.fileno()
        buf = ""
        decoder_leftover = b""

        while True:
            if self._terminated:
                break
            ready, _, _ = select.select([fd], [], [], timeout)
            if not ready:
                if self._proc.poll() is not None:
                    break
                continue
            try:
                raw = os.read(fd, chunk_size)
            except OSError:
                break
            if not raw:
                if self._proc.poll() is not None:
                    break
                continue

            raw = decoder_leftover + raw
            try:
                text = raw.decode("utf-8")
                decoder_leftover = b""
            except UnicodeDecodeError as e:
                text = raw[:e.start].decode("utf-8", errors="replace")
                decoder_leftover = raw[e.start:]

            buf += text
            while True:
                # Find the earliest line break: \r or \n
                idx_n = buf.find("\n")
                idx_r = buf.find("\r")
                idx = -1
                if idx_n != -1 and idx_r != -1:
                    idx = min(idx_n, idx_r)
                elif idx_n != -1:
                    idx = idx_n
                elif idx_r != -1:
                    idx = idx_r
                if idx == -1:
                    break
                piece = buf[:idx]
                # Remove the delimiter (one char)
                buf = buf[idx+1:]
                if piece:
                    yield ("line", piece)   # Always treat as a normal line

        if buf:
            yield ("line", buf)

    def terminate(self, wait: float = 3.0) -> None:
        with self._lock:
            self._terminated = True
            if self._proc is None:
                return
            try:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.wait(timeout=wait)
            except Exception:
                pass
            finally:
                if self._proc.stdout:
                    try:
                        self._proc.stdout.close()
                    except Exception:
                        pass
                self._proc = None

    @property
    def returncode(self) -> Optional[int]:
        with self._lock:
            if self._proc is None:
                return None
            return self._proc.poll()


# ── UI Helpers ───────────────────────────────────────────────────────────────

class ModernButton(tk.Button):
    def __init__(self, master, text="", command=None, variant="primary",
                 font=None, padx=None, pady=None, **kw):
        self.variant = variant
        colors = {
            "primary": (THEME.accent, "#0a0a0a", THEME.accent_hover),
            "danger": (THEME.danger, "#0a0a0a", "#ff7b72"),
            "secondary": (THEME.surface, THEME.fg, THEME.elevated),
            "ghost": (THEME.bg, THEME.fg2, THEME.surface),
        }
        bg, fg, hover_bg = colors.get(variant, colors["primary"])
        btn_font = font or ("Segoe UI", 10, "bold" if variant == "primary" else "normal")
        btn_padx = padx if padx is not None else 14
        btn_pady = pady if pady is not None else 7
        super().__init__(
            master, text=text, command=command,
            bg=bg, fg=fg, activebackground=hover_bg, activeforeground=fg,
            disabledforeground="#5c6270",
            relief="flat", bd=0, cursor="hand2",
            font=btn_font, padx=btn_padx, pady=btn_pady,
            **kw
        )
        if variant != "primary":
            self.config(highlightbackground=THEME.border, highlightthickness=1)
        self._hover_bg = hover_bg
        self._base_bg = bg
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _event=None):
        if self.cget("state") != "disabled":
            self.config(bg=self._hover_bg)

    def _on_leave(self, _event=None):
        if self.cget("state") != "disabled":
            self.config(bg=self._base_bg)


class Section(tk.Frame):
    def __init__(self, master, title: str, **kw):
        super().__init__(
            master, bg=THEME.card,
            highlightbackground=THEME.border, highlightthickness=1,
            padx=14, pady=10, **kw
        )
        tk.Label(
            self, text=title, bg=THEME.card, fg=THEME.accent,
            font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", pady=(0, 8))
        self.body = tk.Frame(self, bg=THEME.card)
        self.body.pack(fill="both", expand=True)


class Expander(tk.Frame):
    def __init__(self, master, title: str, subtitle: str = "", start_open: bool = False, **kw):
        super().__init__(
            master, bg=THEME.card,
            highlightbackground=THEME.border, highlightthickness=1, **kw
        )
        self._open = tk.BooleanVar(value=start_open)

        head = tk.Frame(self, bg=THEME.card, cursor="hand2")
        head.pack(fill="x", padx=12, pady=8)

        self._arrow = tk.Label(head, text="▸", bg=THEME.card, fg=THEME.accent,
                                font=("Segoe UI", 10, "bold"), width=2)
        self._arrow.pack(side="left")

        titles = tk.Frame(head, bg=THEME.card)
        titles.pack(side="left", fill="x", expand=True)
        tk.Label(titles, text=title, bg=THEME.card, fg=THEME.fg,
                 font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x")
        if subtitle:
            tk.Label(titles, text=subtitle, bg=THEME.card, fg=THEME.fg2,
                      font=("Segoe UI", 8), anchor="w").pack(fill="x")

        self.body = tk.Frame(self, bg=THEME.card, padx=12, pady=10)

        for w in (head, self._arrow, titles):
            w.bind("<Button-1>", self._toggle)
        for child in titles.winfo_children():
            child.bind("<Button-1>", self._toggle)

        if start_open:
            self.body.pack(fill="x")
            self._arrow.config(text="▾")

    def _toggle(self, _=None):
        if self._open.get():
            self.body.pack_forget()
            self._arrow.config(text="▸")
        else:
            self.body.pack(fill="x")
            self._arrow.config(text="▾")
        self._open.set(not self._open.get())


class FilePicker(tk.Frame):
    def __init__(self, master, label: str, **kw):
        super().__init__(master, bg=THEME.card, **kw)
        tk.Label(self, text=label, bg=THEME.card, fg=THEME.fg2,
                 font=("Segoe UI", 9), width=18, anchor="w").pack(side="left")
        self.var = tk.StringVar()
        self.entry = tk.Entry(
            self, textvariable=self.var, bg=THEME.surface, fg=THEME.fg,
            insertbackground=THEME.accent, relief="flat", bd=0,
            highlightbackground=THEME.border, highlightthickness=1,
            font=MONO
        )
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 8), ipady=4)
        ModernButton(self, text="Browse", command=self._browse, variant="secondary").pack(side="left")

    def _browse(self):
        p = filedialog.askopenfilename()
        if p:
            self.var.set(p)

    def get(self) -> str:
        return self.var.get().strip()

    def set(self, value: str):
        self.var.set(value)


class ModernSlider(tk.Frame):
    def __init__(self, master, label: str, from_: float, to: float,
                 resolution: float, default: float, is_float: bool = False,
                 unit: str = "", **kw):
        super().__init__(master, bg=THEME.card, **kw)
        self.is_float = is_float
        tk.Label(self, text=label, bg=THEME.card, fg=THEME.fg2,
                 font=("Segoe UI", 9), width=24, anchor="w").pack(side="left")
        self.var = tk.DoubleVar(value=default)
        self.scale = tk.Scale(
            self, variable=self.var, from_=from_, to=to, resolution=resolution,
            orient="horizontal", bg=THEME.card, fg=THEME.fg, troughcolor=THEME.surface,
            highlightthickness=0, showvalue=False, bd=0,
            activebackground=THEME.accent, length=150, command=self._on_scale
        )
        self.scale.pack(side="left", padx=(0, 8))
        self.entry_var = tk.StringVar(value=self._fmt(default))
        self.entry = tk.Entry(
            self, textvariable=self.entry_var, bg=THEME.surface, fg=THEME.accent,
            insertbackground=THEME.accent, relief="flat", bd=0,
            highlightbackground=THEME.border, highlightthickness=1,
            font=MONO, width=9, justify="right"
        )
        self.entry.pack(side="left")
        self.entry.bind("<FocusOut>", self._on_entry)
        self.entry.bind("<Return>", self._on_entry)
        if unit:
            tk.Label(self, text=unit, bg=THEME.card, fg=THEME.fg2,
                     font=("Segoe UI", 8)).pack(side="left", padx=(4, 0))

    def _fmt(self, v) -> str:
        v = float(v)
        return f"{v:.1f}" if self.is_float else str(int(v))

    def _on_scale(self, v):
        self.entry_var.set(self._fmt(v))

    def _on_entry(self, _=None):
        try:
            v = float(self.entry_var.get())
            self.var.set(v)
            self.entry_var.set(self._fmt(v))
        except ValueError:
            self.entry_var.set(self._fmt(self.var.get()))

    def get(self) -> float:
        try:
            return float(self.entry_var.get())
        except ValueError:
            return float(self.var.get())

    def set(self, v: float):
        self.var.set(v)
        sc_to = float(self.scale.cget("to"))
        self.scale.set(min(v, sc_to))
        self.entry_var.set(self._fmt(v))


class ModeCard(tk.Frame):
    def __init__(self, master, title: str, subtitle: str, value: str,
                 selected: bool = False, command: Optional[Callable] = None, **kw):
        super().__init__(
            master, bg=THEME.elevated if selected else THEME.card,
            highlightbackground=THEME.accent if selected else THEME.border,
            highlightthickness=2 if selected else 1,
            padx=12, pady=8, cursor="hand2", **kw
        )
        self.value = value
        self.command = command
        tk.Label(self, text=title, bg=self.cget("bg"),
                 fg=THEME.accent if selected else THEME.fg,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(self, text=subtitle, bg=self.cget("bg"), fg=THEME.fg2,
                 font=("Segoe UI", 8), justify="left").pack(anchor="w", pady=(3, 0))
        for w in [self] + list(self.winfo_children()):
            w.bind("<Button-1>", lambda _e: self.command and self.command(self.value))

    def set_selected(self, selected: bool):
        bg = THEME.elevated if selected else THEME.card
        fg = THEME.accent if selected else THEME.fg
        self.config(bg=bg, highlightbackground=THEME.accent if selected else THEME.border,
                    highlightthickness=2 if selected else 1)
        for child in self.winfo_children():
            child.config(bg=bg)
            if isinstance(child, tk.Label) and "bold" in str(child.cget("font")):
                child.config(fg=fg)


# ── Main Application ─────────────────────────────────────────────────────────

MAX_LOG_LINES = 12000
TRIM_TO_LINES = 9000


class RCRApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE}  —  RuleFlow Chain Runner")
        self.configure(bg=THEME.bg)
        self.geometry("1180x880")
        self.minsize(980, 680)

        self._running = False
        self._stage = 0
        self._process: Optional[ManagedProcess] = None
        self._log_queue = BoundedLogQueue(maxsize=3000)
        self._mem_monitor = MemoryMonitor(threshold_mb=6144.0)
        self._cancel_event = threading.Event()
        self._log_file = None
        self._log_file_path = None
        self._log_line_count = 0
        self._recent_tail: List[str] = []
        self._autoscroll = True

        self._devices: List[Tuple[str, str]] = [("auto", "Auto-detect (recommended)")]
        self._dev_var = tk.StringVar(value="auto")

        self._build_ui()
        self._start_polling()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI Construction ─────────────────────────────────────────────

    def _build_ui(self):
        main = tk.Frame(self, bg=THEME.bg)
        main.pack(fill="both", expand=True, padx=16, pady=12)

        self._build_header(main)

        paned = tk.PanedWindow(main, orient="vertical", bg=THEME.bg, bd=0,
                                sashwidth=6, sashrelief="flat")
        paned.pack(fill="both", expand=True, pady=(10, 0))

        top = tk.Frame(paned, bg=THEME.bg)
        self._build_tabs(top)
        paned.add(top, stretch="always", minsize=200)

        bottom = tk.Frame(paned, bg=THEME.bg)
        self._build_log_panel(bottom)
        paned.add(bottom, height=180, minsize=100)

        self._build_footer(main)

    def _build_header(self, master):
        hdr = tk.Frame(master, bg=THEME.bg)
        hdr.pack(fill="x")

        title_grp = tk.Frame(hdr, bg=THEME.bg)
        title_grp.pack(side="left")
        tk.Label(title_grp, text=f"◈ {APP_TITLE}", bg=THEME.bg, fg=THEME.fg,
                 font=("Segoe UI", 17, "bold")).pack(anchor="w")
        tk.Label(title_grp, text="rulest  →  concentrator  →  ranker", bg=THEME.bg,
                 fg=THEME.fg2, font=("Segoe UI", 10)).pack(anchor="w", pady=(1, 0))

        self._stage_frame = tk.Frame(hdr, bg=THEME.bg)
        self._stage_frame.pack(side="right")
        self._stage_dots = []
        for i, name in enumerate(["rulest", "concentrator", "ranker"], 1):
            dot = tk.Label(self._stage_frame, text=f"  {i}  ", bg=THEME.surface, fg=THEME.fg2,
                            font=("Segoe UI", 9, "bold"), padx=8, pady=4)
            dot.pack(side="left", padx=(0, 6))
            self._stage_dots.append(dot)

        self._mem_label = tk.Label(hdr, text="RAM: —", bg=THEME.bg, fg=THEME.fg2, font=("Segoe UI", 9))
        self._mem_label.pack(side="right", padx=(0, 16))

    def _build_tabs(self, master):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("RCR.TNotebook", background=THEME.bg, borderwidth=0)
        style.configure("RCR.TNotebook.Tab", background=THEME.surface, foreground=THEME.fg2,
                        padding=(16, 8), font=("Segoe UI", 10, "bold"))
        style.map("RCR.TNotebook.Tab",
                  background=[("selected", THEME.card)],
                  foreground=[("selected", THEME.accent)])

        self._nb = ttk.Notebook(master, style="RCR.TNotebook")
        self._nb.pack(fill="both", expand=True)

        tab_pipeline = tk.Frame(self._nb, bg=THEME.bg)
        tab_ranker = tk.Frame(self._nb, bg=THEME.bg)
        tab_advanced = tk.Frame(self._nb, bg=THEME.bg)

        self._nb.add(tab_pipeline, text="  Pipeline  ")
        self._nb.add(tab_ranker, text="  Output & Ranker  ")
        self._nb.add(tab_advanced, text="  Advanced  ")

        self._build_pipeline_tab(tab_pipeline)
        self._build_ranker_tab(tab_ranker)
        self._build_advanced_tab(tab_advanced)

    def _make_scrollable_container(self, parent):
        canvas = tk.Canvas(parent, bg=THEME.bg, highlightthickness=0)
        vsb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        wrap = tk.Frame(canvas, bg=THEME.bg)
        win = canvas.create_window((0, 0), window=wrap, anchor="nw")
        wrap.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        def _on_mousewheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        return wrap

    # -- Tab: Pipeline -----------------------------------------------

    def _build_pipeline_tab(self, root):
        wrap = self._make_scrollable_container(root)

        files = Section(wrap, "Step 1 — Input Files")
        files.pack(fill="x", pady=(0, 10))
        self._base_wl = FilePicker(files.body, "Base wordlist"); self._base_wl.pack(fill="x", pady=3)
        self._tgt_wl = FilePicker(files.body, "Target wordlist"); self._tgt_wl.pack(fill="x", pady=3)
        self._cracked = FilePicker(files.body, "Cracked passwords"); self._cracked.pack(fill="x", pady=3)

        row = tk.Frame(files.body, bg=THEME.card)
        row.pack(fill="x", pady=(6, 0))
        tk.Label(row, text="Output directory", bg=THEME.card, fg=THEME.fg2,
                 font=("Segoe UI", 9), width=18, anchor="w").pack(side="left")
        self._outdir_var = tk.StringVar(value=os.getcwd())
        tk.Entry(row, textvariable=self._outdir_var, bg=THEME.surface, fg=THEME.fg,
                 insertbackground=THEME.accent, relief="flat", bd=0,
                 highlightbackground=THEME.border, highlightthickness=1,
                 font=MONO).pack(side="left", fill="x", expand=True, padx=(0, 8), ipady=4)
        ModernButton(row, text="Browse", variant="secondary",
                     command=lambda: self._outdir_var.set(filedialog.askdirectory() or self._outdir_var.get())
                     ).pack(side="left")

        mode = Section(wrap, "Step 2 — Pipeline Mode")
        mode.pack(fill="x", pady=(0, 10))
        self._mode_var = tk.StringVar(value="balanced")
        row2 = tk.Frame(mode.body, bg=THEME.card)
        row2.pack(fill="x")
        self._mode_cards = {}
        for value, title, subtitle in [
            ("maximum", "Maximum Quality", "Depth 10, full genetic run,\nextensive token-strip."),
            ("balanced", "Balanced", "Depth 6, genetic enabled,\nrecommended default."),
            ("fast", "Fast", "Depth 3, lighter genetic,\nquick results for testing."),
            ("custom", "Custom", "Full manual control over\nevery parameter."),
        ]:
            mc = ModeCard(row2, title, subtitle, value, selected=(value == "balanced"), command=self._set_mode)
            mc.pack(side="left", fill="both", expand=True, padx=(0, 8))
            self._mode_cards[value] = mc

        device = Section(wrap, "OpenCL Device")
        device.pack(fill="x")
        top = tk.Frame(device.body, bg=THEME.card)
        top.pack(fill="x")
        tk.Label(top, text="GPU / Accelerator", bg=THEME.card, fg=THEME.fg2,
                 font=("Segoe UI", 9), width=18, anchor="w").pack(side="left")
        self._dev_combo = ttk.Combobox(top, textvariable=self._dev_var,
                                        values=[d[1] for d in self._devices], state="readonly", width=38)
        self._dev_combo.set(self._devices[0][1])
        self._dev_combo.pack(side="left", padx=(0, 8))
        ModernButton(top, text="⟳ Scan", command=self._scan_devices, variant="secondary").pack(side="left")
        self._dev_status = tk.Label(device.body,
            text="Click 'Scan' to detect OpenCL hardware. Auto-detect works for most setups.",
            bg=THEME.card, fg=THEME.fg2, font=("Segoe UI", 9), anchor="w")
        self._dev_status.pack(fill="x", pady=(8, 0))

    # -- Tab: Output & Ranker -----------------------------------------

    def _build_ranker_tab(self, root):
        wrap = self._make_scrollable_container(root)

        conc = Section(wrap, "Step 3 — Concentrator Output")
        conc.pack(fill="x", pady=(0, 10))
        self._concfmt_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            conc.body, text="Expanded format (space-separated operators)",
            variable=self._concfmt_var, bg=THEME.card, fg=THEME.fg, selectcolor=THEME.surface,
            activebackground=THEME.card, activeforeground=THEME.fg, font=("Segoe UI", 9)
        ).pack(anchor="w")
        tk.Label(
            conc.body,
            text="Expanded: each operator and argument is separated by spaces — easier to read and debug.\n"
                 "Compact: rules on single lines — slightly faster for hashcat to load.",
            bg=THEME.card, fg=THEME.fg2, font=("Segoe UI", 9), justify="left"
        ).pack(anchor="w", pady=(8, 0))

        rk = Section(wrap, "Step 4 — Ranker Strategy")
        rk.pack(fill="x")
        self._legacy_var = tk.BooleanVar(value=True)

        leg_frame = tk.Frame(rk.body, bg=THEME.card, padx=12, pady=12,
                              highlightbackground=THEME.accent, highlightthickness=2)
        leg_frame.pack(fill="x", pady=(0, 8))
        tk.Radiobutton(
            leg_frame, text="Legacy (Exhaustive) — RECOMMENDED for most dictionaries",
            variable=self._legacy_var, value=True, bg=THEME.card, fg=THEME.accent,
            selectcolor=THEME.surface, activebackground=THEME.card, activeforeground=THEME.accent,
            font=("Segoe UI", 10, "bold")
        ).pack(anchor="w")
        tk.Label(
            leg_frame,
            text="Every rule is tested straight through against the wordlist — no bandit bookkeeping.\n"
                 "• Usually the FASTER option in practice: no per-batch statistics, elimination passes,\n"
                 "  or Thompson-sampling overhead to pay for on every iteration\n"
                 "• Best fit for balanced dictionaries — where rule effectiveness is fairly evenly spread\n"
                 "  and there's little to be gained by skipping candidates early\n"
                 "• Maximum statistical accuracy — no rule is ever skipped\n"
                 "• Lower, flatter RAM usage — no bandit state arrays to maintain",
            bg=THEME.card, fg=THEME.fg2, font=("Segoe UI", 9), justify="left"
        ).pack(anchor="w", pady=(8, 0))

        mab_frame = tk.Frame(rk.body, bg=THEME.card, padx=12, pady=12,
                              highlightbackground=THEME.border, highlightthickness=1)
        mab_frame.pack(fill="x")
        tk.Radiobutton(
            mab_frame, text="MAB (Multi-Armed Bandit) — for very large / imbalanced rule sets",
            variable=self._legacy_var, value=False, bg=THEME.card, fg=THEME.fg,
            selectcolor=THEME.surface, activebackground=THEME.card, activeforeground=THEME.fg,
            font=("Segoe UI", 10)
        ).pack(anchor="w")
        tk.Label(
            mab_frame,
            text="Adaptive sampling that tries to spend less time on rules that look unpromising early.\n"
                 "• Pays off mainly on very large (10k+) or heavily skewed / imbalanced rule sets, where\n"
                 "  a large share of rules are genuinely useless and early elimination avoids real work\n"
                 "• On smaller or already-balanced dictionaries the sampling/statistics overhead can\n"
                 "  make it SLOWER than Legacy, not faster — there's less waste for it to cut\n"
                 "• Slightly lower statistical confidence for very rare rules\n"
                 "• Keeps extra bandit state (per-rule counters) in RAM for the whole run",
            bg=THEME.card, fg=THEME.fg2, font=("Segoe UI", 9), justify="left"
        ).pack(anchor="w", pady=(8, 0))

    # -- Tab: Advanced -----------------------------------------------

    def _build_advanced_tab(self, root):
        canvas = tk.Canvas(root, bg=THEME.bg, highlightthickness=0)
        vsb = ttk.Scrollbar(root, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True, padx=4, pady=8)

        wrap = tk.Frame(canvas, bg=THEME.bg)
        win = canvas.create_window((0, 0), window=wrap, anchor="nw")
        wrap.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        exp1 = Expander(wrap, "Rulest Core", "Depth, genetic algorithm, time budget", start_open=True)
        exp1.pack(fill="x", pady=(0, 8))
        self._adv_depth = ModernSlider(exp1.body, "Max depth", 1, 31, 1, 3); self._adv_depth.pack(fill="x", pady=2)
        self._adv_gg = ModernSlider(exp1.body, "Genetic generations", 20, 1000, 10, 300); self._adv_gg.pack(fill="x", pady=2)
        self._adv_gp = ModernSlider(exp1.body, "Genetic population", 50, 2000, 50, 600); self._adv_gp.pack(fill="x", pady=2)
        self._adv_th = ModernSlider(exp1.body, "Target hours", 0.5, 12, 0.5, 2.0, is_float=True, unit="h"); self._adv_th.pack(fill="x", pady=2)

        exp2 = Expander(wrap, "Bloom Filter & Token-Strip", "Stage-0 preprocessing")
        exp2.pack(fill="x", pady=(0, 8))
        self._adv_bm = ModernSlider(exp2.body, "Bloom filter size", 100, 4000, 100, 256, unit="MB"); self._adv_bm.pack(fill="x", pady=2)
        self._adv_s0 = ModernSlider(exp2.body, "Stage-0 workers (0=auto)", 0, 64, 1, 0); self._adv_s0.pack(fill="x", pady=2)
        self._adv_tp = ModernSlider(exp2.body, "Token-strip max prefix", 1, 12, 1, 4); self._adv_tp.pack(fill="x", pady=2)
        self._adv_ts = ModernSlider(exp2.body, "Token-strip max suffix", 1, 12, 1, 4); self._adv_ts.pack(fill="x", pady=2)

        exp3 = Expander(wrap, "Ranker MAB Tuning", "Only used when MAB strategy is selected")
        exp3.pack(fill="x", pady=(0, 8))
        self._adv_rk = ModernSlider(exp3.body, "Top rules to keep (K)", 1000, 100000, 1000, 75000); self._adv_rk.pack(fill="x", pady=2)
        self._adv_ms = ModernSlider(exp3.body, "MAB screening trials", 1, 30, 1, 4); self._adv_ms.pack(fill="x", pady=2)
        self._adv_mf = ModernSlider(exp3.body, "MAB final trials", 1, 50, 1, 8); self._adv_mf.pack(fill="x", pady=2)

        exp4 = Expander(wrap, "Memory Preset", "Applies to the ranker stage", start_open=True)
        exp4.pack(fill="x", pady=(0, 8))
        tk.Label(exp4.body,
                 text="If a stage crashes with an out-of-memory error, switch to Low and re-run —\n"
                      "the app will also suggest this automatically when it detects one.",
                 bg=THEME.card, fg=THEME.fg2, font=("Segoe UI", 8), justify="left").pack(anchor="w", pady=(0, 6))
        preset_frame = tk.Frame(exp4.body, bg=THEME.card)
        preset_frame.pack(anchor="w")
        self._preset_var = tk.StringVar(value="medium_memory")
        for val, lbl in [("low_memory", "Low (≤4GB VRAM)"), ("medium_memory", "Medium (4-8GB)"),
                          ("high_memory", "High (>8GB)")]:
            tk.Radiobutton(preset_frame, text=lbl, variable=self._preset_var, value=val,
                           bg=THEME.card, fg=THEME.fg, selectcolor=THEME.surface,
                           activebackground=THEME.card, activeforeground=THEME.fg,
                           font=("Segoe UI", 9)).pack(side="left", padx=(0, 16))

    # ── Log Panel ─────────────────────────────────────────────────────

    def _build_log_panel(self, root):
        card = tk.Frame(root, bg=THEME.card, highlightbackground=THEME.border,
                         highlightthickness=1, padx=10, pady=8)
        card.pack(fill="both", expand=True)

        toolbar = tk.Frame(card, bg=THEME.card)
        toolbar.pack(fill="x", pady=(0, 6))

        tk.Label(toolbar, text="Execution Log", bg=THEME.card, fg=THEME.accent,
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        self._log_status = tk.Label(toolbar, text="Ready", bg=THEME.card, fg=THEME.fg2, font=("Segoe UI", 9))
        self._log_status.pack(side="left", padx=(12, 0))

        self._follow_btn = ModernButton(toolbar, text="⏷ Following", variant="secondary",
                                         command=self._toggle_follow)
        self._follow_btn.pack(side="right", padx=(6, 0))
        ModernButton(toolbar, text="Open log file", variant="ghost", command=self._open_log_file).pack(side="right", padx=(6, 0))
        ModernButton(toolbar, text="Clear", variant="ghost", command=self._clear_log).pack(side="right", padx=(6, 0))

        search_row = tk.Frame(card, bg=THEME.card)
        search_row.pack(fill="x", pady=(0, 6))
        tk.Label(search_row, text="Search:", bg=THEME.card, fg=THEME.fg2, font=("Segoe UI", 9)).pack(side="left")
        self._search_var = tk.StringVar()
        search_entry = tk.Entry(search_row, textvariable=self._search_var, bg=THEME.surface, fg=THEME.fg,
                                 insertbackground=THEME.accent, relief="flat", bd=0,
                                 highlightbackground=THEME.border, highlightthickness=1, font=MONO)
        search_entry.pack(side="left", fill="x", expand=True, padx=(6, 6), ipady=3)
        search_entry.bind("<Return>", lambda _e: self._search_log(1))
        ModernButton(search_row, text="↑ Prev", variant="secondary", command=lambda: self._search_log(-1)).pack(side="left", padx=(0, 4))
        ModernButton(search_row, text="↓ Next", variant="secondary", command=lambda: self._search_log(1)).pack(side="left")

        self._log = scrolledtext.ScrolledText(
            card, bg="#0d0f14", fg=THEME.fg, insertbackground=THEME.accent,
            font=MONO, relief="flat", bd=0,
            highlightbackground=THEME.border, highlightthickness=1,
            wrap="word", state="disabled"
        )
        self._log.pack(fill="both", expand=True)
        self._log.tag_config("search_hit", background=THEME.info, foreground="#0a0a0a")

        self._log.bind("<MouseWheel>", self._on_log_scroll)
        self._log.bind("<Button-4>", self._on_log_scroll)
        self._log.bind("<Button-5>", self._on_log_scroll)
        self._log.bind("<Prior>", lambda _e: self._set_follow(False))
        self._log.bind("<Up>", lambda _e: self._set_follow(False))

        for name, colour in [
            ("accent", THEME.accent), ("success", THEME.success),
            ("warning", THEME.warning), ("danger", THEME.danger),
            ("info", THEME.info), ("muted", THEME.fg2),
        ]:
            self._log.tag_config(name, foreground=colour)
        self._colour_tags = {"accent", "success", "warning", "danger", "info", "muted"}

    def _toggle_follow(self):
        self._set_follow(not self._autoscroll)

    def _set_follow(self, on: bool):
        self._autoscroll = on
        self._follow_btn.config(text="⏷ Following" if on else "⏸ Paused (scroll to end to resume)")
        if on:
            self._log.see("end")

    def _on_log_scroll(self, _event=None):
        self.after(50, self._check_scroll_position)

    def _check_scroll_position(self):
        try:
            top_frac, bottom_frac = self._log.yview()
        except Exception:
            return
        at_bottom = bottom_frac > 0.999
        if at_bottom and not self._autoscroll:
            self._set_follow(True)
        elif not at_bottom and self._autoscroll:
            self._set_follow(False)

    def _search_log(self, direction: int):
        term = self._search_var.get()
        if not term:
            return
        self._log.tag_remove("search_hit", "1.0", "end")
        start = self._log.index("insert")
        if direction > 0:
            idx = self._log.search(term, start, stopindex="end", nocase=True)
            if not idx:
                idx = self._log.search(term, "1.0", stopindex="end", nocase=True)
        else:
            idx = self._log.search(term, start, stopindex="1.0", backwards=True, nocase=True)
            if not idx:
                idx = self._log.search(term, "end", stopindex="1.0", backwards=True, nocase=True)
        if idx:
            end_idx = f"{idx}+{len(term)}c"
            self._log.tag_add("search_hit", idx, end_idx)
            self._log.mark_set("insert", end_idx)
            self._log.see(idx)
            self._set_follow(False)

    def _open_log_file(self):
        if not self._log_file_path or not os.path.isfile(self._log_file_path):
            messagebox.showinfo("Log file", "No log file yet — run the pipeline first.")
            return
        folder = os.path.dirname(self._log_file_path)
        try:
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception:
            messagebox.showinfo("Log file location", self._log_file_path)

    # ── Footer ────────────────────────────────────────────────────────

    def _build_footer(self, master):
        # Top separator line
        tk.Frame(master, bg=THEME.border, height=1).pack(side="bottom", fill="x")

        # Action bar
        bar = tk.Frame(master, bg=THEME.surface, padx=24, pady=18)
        bar.pack(side="bottom", fill="x")

        # Status indicator (left)
        status_box = tk.Frame(bar, bg=THEME.surface)
        status_box.pack(side="left")
        self._status_dot = tk.Label(
            status_box, text="●", bg=THEME.surface, fg=THEME.success,
            font=("Segoe UI", 10)
        )
        self._status_dot.pack(side="left", padx=(0, 8))
        self._status_label = tk.Label(
            status_box, text="Ready to start", bg=THEME.surface,
            fg=THEME.fg2, font=("Segoe UI", 10)
        )
        self._status_label.pack(side="left")

        # Action buttons (right)
        btn_box = tk.Frame(bar, bg=THEME.surface)
        btn_box.pack(side="right")

        self._stop_btn = ModernButton(
            btn_box, text="⏹  Stop", command=self._stop, variant="danger",
            font=("Segoe UI", 11, "bold"), padx=28, pady=12
        )
        self._stop_btn.pack(side="right", padx=(12, 0))
        self._stop_btn.config(state="disabled")

        self._run_btn = ModernButton(
            btn_box, text="▶  Run Pipeline", command=self._run, variant="primary",
            font=("Segoe UI", 11, "bold"), padx=28, pady=12
        )
        self._run_btn.pack(side="right")

    def _set_status(self, text: str, color: str):
        self._status_label.config(text=text, fg=color)
        self._status_dot.config(fg=color)

    # ── Mode Management ─────────────────────────────────────────────

    def _set_mode(self, mode: str):
        self._mode_var.set(mode)
        for value, card in self._mode_cards.items():
            card.set_selected(value == mode)
        presets = {
            "maximum": dict(depth=10, gg=300, gp=600, th=2.0, bm=256, tp=10, ts=10, rk=100000, ms=5, mf=10, pr="medium_memory"),
            "balanced": dict(depth=6, gg=300, gp=600, th=1.0, bm=256, tp=6, ts=6, rk=75000, ms=4, mf=8, pr="medium_memory"),
            "fast": dict(depth=3, gg=300, gp=600, th=0.5, bm=256, tp=3, ts=3, rk=50000, ms=3, mf=5, pr="medium_memory"),
        }
        if mode in presets and hasattr(self, "_adv_depth"):
            p = presets[mode]
            self._adv_depth.set(p["depth"]); self._adv_gg.set(p["gg"]); self._adv_gp.set(p["gp"])
            self._adv_th.set(p["th"]); self._adv_bm.set(p["bm"]); self._adv_rk.set(p["rk"])
            self._adv_ms.set(p["ms"]); self._adv_mf.set(p["mf"]); self._adv_tp.set(p["tp"]); self._adv_ts.set(p["ts"])
            self._preset_var.set(p["pr"])

    def _apply_low_memory(self):
        self._preset_var.set("low_memory")
        self._adv_bm.set(min(self._adv_bm.get(), 128))
        self._adv_rk.set(min(self._adv_rk.get(), 8000))
        self._adv_gp.set(min(self._adv_gp.get(), 300))
        self._adv_ms.set(min(self._adv_ms.get(), 3))
        self._adv_mf.set(min(self._adv_mf.get(), 5))
        self._nb.select(2)
        self._log_system("Applied Low-Memory settings (preset=low_memory, bloom≤128MB, K≤8000, "
                          "genetic population≤300, MAB trials reduced). Re-run when ready.")

    # ── Device Scanning ─────────────────────────────────────────────

    def _scan_devices(self):
        self._dev_status.config(text="Scanning…", fg=THEME.warning)
        self._log_system("Scanning for OpenCL devices…")
        threading.Thread(target=self._scan_thread, daemon=True).start()

    def _scan_thread(self):
        py = sys.executable
        rulest_py = os.path.join(SCRIPT_DIR, "rulest_v2.py")
        try:
            result = subprocess.run([py, rulest_py, "--list-devices"], capture_output=True, text=True, timeout=30)
            raw = result.stdout + result.stderr
        except Exception as e:
            self.after(0, lambda: self._scan_failed(str(e)))
            return
        clean = strip_ansi(raw)
        devices = [("auto", "Auto-detect (recommended)")]
        for line in clean.splitlines():
            m = re.search(r'\[?\b(\d+)\]?\s*[:\-]?\s*(.+)', line)
            if m and any(k in line.lower() for k in ["nvidia", "amd", "intel", "gpu", "geforce", "radeon"]):
                dev_id = m.group(1)
                desc = m.group(2).strip()
                devices.append((dev_id, f"[{dev_id}] {desc}"))
        self.after(0, lambda: self._scan_complete(devices, raw))

    def _scan_failed(self, error: str):
        self._dev_status.config(text=f"Scan failed: {error}", fg=THEME.danger)
        self._log_error(f"Device scan failed: {error}")

    def _scan_complete(self, devices: List[Tuple[str, str]], raw: str):
        self._devices = devices
        self._dev_combo["values"] = [d[1] for d in devices]
        self._dev_combo.set(devices[0][1])
        count = len(devices) - 1
        if count > 0:
            self._dev_status.config(text=f"Found {count} device(s). Auto-detect recommended.", fg=THEME.success)
        else:
            self._dev_status.config(text="No OpenCL devices found. CPU fallback will be used.", fg=THEME.warning)
        self._log_system(f"Device scan complete. {count} device(s) found.")
        self._log_muted(strip_ansi(raw))

    # ── Log Writing ─────────────────────────────────────────────────

    def _log_system(self, text: str):
        self._log_queue.put(("system", f"[{time.strftime('%H:%M:%S')}] {text}\n"))

    def _log_error(self, text: str):
        self._log_queue.put(("error", f"[{time.strftime('%H:%M:%S')}] ERROR: {text}\n"))

    def _log_muted(self, text: str):
        self._log_queue.put(("muted", text + "\n"))

    def _log_line(self, text: str):
        self._log_queue.put(("ansi_line", text + "\n"))

    def _clear_log(self):
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")
        self._log_line_count = 0

    def _open_log_stream(self):
        os.makedirs(self._outdir_var.get(), exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        self._log_file_path = os.path.join(self._outdir_var.get(), f"rcr_run_{ts}.log")
        try:
            self._log_file = open(self._log_file_path, "a", encoding="utf-8", errors="replace")
        except Exception as e:
            self._log_file = None
            self._log_error(f"Could not open log file for writing: {e}")

    def _close_log_stream(self):
        if self._log_file:
            try:
                self._log_file.close()
            except Exception:
                pass
            self._log_file = None

    def _mirror_to_disk(self, text: str):
        if self._log_file:
            try:
                clean = strip_ansi(text)
                self._log_file.write(clean)
            except Exception:
                pass

    def _remember_tail(self, text: str):
        self._recent_tail.append(text)
        if len(self._recent_tail) > 200:
            self._recent_tail = self._recent_tail[-200:]

    # ── Main Polling Loop ───────────────────────────────────────────

    def _start_polling(self):
        self.after(50, self._poll_loop)
        self.after(2000, self._update_memory)

    def _poll_loop(self):
        processed = 0
        while processed < 200:
            try:
                kind, content = self._log_queue.get_nowait()
            except queue.Empty:
                break
            self._apply_log_entry(kind, content)
            processed += 1

        dropped = self._log_queue.clear_dropped()
        if dropped > 0:
            self._apply_log_entry("system", f"[{time.strftime('%H:%M:%S')}] … {dropped} log lines dropped (backpressure)\n")

        self._trim_log_if_needed()
        self.after(50, self._poll_loop)

    def _trim_log_if_needed(self):
        if self._log_line_count <= MAX_LOG_LINES:
            return
        self._log.config(state="normal")
        to_delete = self._log_line_count - TRIM_TO_LINES
        self._log.delete("1.0", f"{to_delete + 1}.0")
        self._log.config(state="disabled")
        self._log_line_count = TRIM_TO_LINES

    def _apply_log_entry(self, kind: str, content: str):
        self._log.config(state="normal")

        if kind in ("ansi_line", "system", "error", "muted"):
            self._mirror_to_disk(content)
            self._remember_tail(content)
            tag = {"system": "info", "error": "danger", "muted": "muted"}.get(kind)
            if kind == "ansi_line":
                for chunk, colour in parse_ansi_segments(content):
                    if not chunk:
                        continue
                    if colour:
                        t = f"col_{colour.replace('#', '')}"
                        if t not in self._colour_tags:
                            self._log.tag_config(t, foreground=colour)
                            self._colour_tags.add(t)
                        self._log.insert("end", chunk, t)
                    else:
                        self._log.insert("end", chunk)
            else:
                self._log.insert("end", content, tag)
            self._log_line_count += content.count("\n")

        else:
            # fallback – just insert
            self._mirror_to_disk(content)
            self._log.insert("end", content)
            self._log_line_count += content.count("\n")

        if self._autoscroll:
            self._log.see("end")
        self._log.config(state="disabled")

    def _update_memory(self):
        if self._running:
            mem_str = self._mem_monitor.format()
            self._mem_label.config(text=f"RAM: {mem_str}")
            if self._mem_monitor.is_under_pressure():
                self._mem_label.config(fg=THEME.warning)
            else:
                self._mem_label.config(fg=THEME.fg2)
        self.after(2000, self._update_memory)

    # ── Pipeline Execution ────────────────────────────────────────

    def _validate(self) -> bool:
        for label, path in [
            ("Base wordlist", self._base_wl.get()),
            ("Target wordlist", self._tgt_wl.get()),
            ("Cracked passwords", self._cracked.get()),
        ]:
            if not path:
                messagebox.showerror("Missing Input", f"{label} is required.")
                return False
            if not os.path.isfile(path):
                messagebox.showerror("File Not Found", f"{label}:\n{path}\n\nFile does not exist.")
                return False
        return True

    def _run(self):
        if self._running or not self._validate():
            return
        self._running = True
        self._cancel_event.clear()
        self._stage = 0
        self._recent_tail = []
        self._run_btn.config(state="disabled")
        self._stop_btn.config(state="normal")
        self._open_log_stream()
        self._log_system(f"Pipeline starting… (full log: {self._log_file_path})")
        self._set_status("Running…", THEME.accent)
        threading.Thread(target=self._pipeline_thread, daemon=True).start()

    def _stop(self):
        if not self._running:
            return
        self._cancel_event.set()
        self._log_system("Stop requested, terminating current process…")
        if self._process:
            self._process.terminate()
            self._process = None
        self._mem_monitor.set_child_pid(None)
        self._finish(aborted=True)

    def _finish(self, aborted: bool = False, error: bool = False):
        # Prevent double-finish if user already stopped
        if not self._running:
            return
        self._running = False
        self._close_log_stream()
        gc.collect()
        self._run_btn.config(state="normal")
        self._stop_btn.config(state="disabled")
        if aborted:
            self._set_stage(-1)
            self._set_status("Stopped", THEME.warning)
            self._log_system("Pipeline stopped by user.")
        elif error:
            self._set_stage(-1)
            self._set_status("Failed", THEME.danger)
        else:
            self._set_stage(10)
            self._set_status("Complete ✓", THEME.success)
            self._log_system("Pipeline finished successfully.")

    def _set_stage(self, stage: int):
        for i, dot in enumerate(self._stage_dots, 1):
            if stage == -1:
                dot.config(bg=THEME.danger if i == self._stage else THEME.surface,
                           fg="#0a0a0a" if i == self._stage else THEME.fg2)
            elif stage == 10:
                dot.config(bg=THEME.success, fg="#0a0a0a")
            elif i < stage:
                dot.config(bg=THEME.success, fg="#0a0a0a")
            elif i == stage:
                dot.config(bg=THEME.accent, fg="#0a0a0a")
            else:
                dot.config(bg=THEME.surface, fg=THEME.fg2)

    def _device_args(self) -> List[str]:
        dev_display = self._dev_var.get()
        if not dev_display or dev_display.lower().startswith("auto"):
            return []
        m = re.search(r'\[(\d+)\]', dev_display)
        if m:
            return ["--device", m.group(1)]
        if dev_display.isdigit():
            return ["--device", dev_display]
        return ["--device", dev_display]

    def _check_for_oom(self) -> bool:
        tail = "\n".join(self._recent_tail[-100:])
        return bool(OOM_PATTERNS.search(tail))

    def _run_step(self, cmd: List[str], label: str) -> int:
        self._log_system(f"{'─' * 50}")
        self._log_system(f"Stage: {label}")
        self._log_system(f"{'─' * 50}")
        self._log_muted(f"$ {' '.join(shlex.quote(str(a)) for a in cmd)}")

        self._process = ManagedProcess()
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        if not self._process.start(cmd, self._outdir_var.get(), env):
            self._log_error("Failed to start process")
            return -1

        self._mem_monitor.set_child_pid(self._process.pid)

        # Keep a local reference so _stop() can't wipe it mid-loop
        proc = self._process
        for kind, text in proc.iter_events(timeout=0.3):
            if self._cancel_event.is_set():
                self._log_system("Cancellation detected, stopping…")
                break
            if not text:
                continue

            # Always treat as a normal line, but strip trailing \r if any
            clean_text = text.rstrip('\r') + '\n'
            self._log_line(clean_text)

        rc = proc.returncode if proc is not None else -1
        self._process = None
        self._mem_monitor.set_child_pid(None)
        gc.collect()

        if rc not in (0, None) and self._check_for_oom():
            self._log_error(
                "This looks like an out-of-memory failure (allocation error / process killed).")
            self._log_system("Suggestion: switch the Memory Preset to Low and reduce K / genetic "
                              "population / MAB trials on the Advanced tab, then re-run.")
            self.after(0, self._offer_low_memory_dialog)

        return rc if rc is not None else -1

    def _offer_low_memory_dialog(self):
        if messagebox.askyesno(
            "Possible out-of-memory failure",
            "This stage appears to have failed because it ran out of memory "
            "(host RAM or GPU VRAM).\n\n"
            "Apply the Low-Memory preset now (lower bloom filter size, K, "
            "genetic population, and MAB trial counts) so the next run is "
            "less likely to hit the same wall?"
        ):
            self._apply_low_memory()

    def _pipeline_thread(self):
        outdir = self._outdir_var.get()
        base_wl = self._base_wl.get()
        tgt_wl = self._tgt_wl.get()
        cracked = self._cracked.get()

        depth = int(self._adv_depth.get())
        gen_gen = int(self._adv_gg.get())
        gen_pop = int(self._adv_gp.get())
        th = float(self._adv_th.get())
        bm = int(self._adv_bm.get())
        s0 = int(self._adv_s0.get())
        tok_p = int(self._adv_tp.get())
        tok_s = int(self._adv_ts.get())
        rk = int(self._adv_rk.get())
        ms = int(self._adv_ms.get())
        mf = int(self._adv_mf.get())
        preset = self._preset_var.get()
        legacy = self._legacy_var.get()

        py = sys.executable
        rulest_py = os.path.join(SCRIPT_DIR, "rulest_v2.py")
        conc_py = os.path.join(SCRIPT_DIR, "concentrator.py")
        rank_py = os.path.join(SCRIPT_DIR, "ranker.py")
        dev_args = self._device_args()

        s1 = os.path.join(outdir, "stage1_raw.rule")
        self.after(0, lambda: self._set_stage(1))
        self.after(0, lambda: self._status_label.config(text="Stage 1/3: rulest…"))

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
        ] + dev_args, "rulest — rule extraction")

        if rc != 0 or self._cancel_event.is_set():
            self.after(0, lambda: self._finish(error=True))
            return

        gc.collect()
        self._log_system("Memory cleanup between stages…")

        s2b = os.path.join(outdir, "stage2_cleaned")
        self.after(0, lambda: self._set_stage(2))
        self.after(0, lambda: self._status_label.config(text="Stage 2/3: concentrator…"))

        conc_format = "expanded" if self._concfmt_var.get() else "line"
        rc = self._run_step([
            py, conc_py,
            "-p", s1,
            "--output_base_name", s2b,
            "--output-format", conc_format,
        ], "concentrator — rule optimization")

        if rc != 0 or self._cancel_event.is_set():
            self.after(0, lambda: self._finish(error=True))
            return

        expected = s2b + "_processed.rule"
        matches = [expected] if os.path.isfile(expected) else glob.glob(s2b + "*.rule")
        if not matches:
            fallback = sorted(
                [f for f in glob.glob(os.path.join(outdir, "*.rule")) if os.path.abspath(f) != os.path.abspath(s1)],
                key=os.path.getmtime, reverse=True
            )
            if fallback:
                matches = [fallback[0]]
                self._log_system(f"Using fallback output: {matches[0]}")
        if not matches:
            self._log_error(f"No concentrator output found: {s2b}*.rule")
            self.after(0, lambda: self._finish(error=True))
            return

        cleaned = matches[0]
        self._log_system(f"Using cleaned rules: {cleaned}")
        gc.collect()

        s3 = os.path.join(outdir, "stage3_ranking.csv")
        self.after(0, lambda: self._set_stage(3))
        self.after(0, lambda: self._status_label.config(text="Stage 3/3: ranker (this may take a while)…"))

        cmd3 = [py, rank_py, "-w", base_wl, "-r", cleaned, "-c", cracked, "-o", s3,
                "-k", str(rk), "--preset", preset] + dev_args
        if legacy:
            cmd3.append("--legacy")
            self._log_system("Using Legacy (exhaustive) ranker — recommended default, full accuracy.")
        else:
            cmd3 += ["--mab-screening-trials", str(ms), "--mab-final-trials", str(mf)]
            self._log_system("Using MAB (adaptive) ranker — best for very large / imbalanced rule sets.")

        rc = self._run_step(cmd3, "ranker — rule scoring & ranking")
        if rc != 0 or self._cancel_event.is_set():
            self.after(0, lambda: self._finish(error=True))
            return

        self._log_system(f"{'─' * 50}")
        self._log_system("Pipeline complete!")
        self._log_system(f"Results: {s3}")
        self._log_system(f"{'─' * 50}")
        self.after(0, self._finish)

    # ── Window Management ─────────────────────────────────────────

    def _on_close(self):
        if self._running:
            if messagebox.askyesno("Quit", "Pipeline is running. Stop and quit?"):
                self._stop()
                self.destroy()
        else:
            self._close_log_stream()
            self.destroy()


if __name__ == "__main__":
    app = RCRApp()
    app.mainloop()
