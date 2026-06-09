#!/usr/bin/env python3
# =============================================================================
# INTERACTIVE HASHCAT RULE PIPELINE (Python Port) - STREAMING OUTPUT
# =============================================================================
"""
Fully cross-platform (Windows/Linux) interactive pipeline for Hashcat rule generation:
1. Rulest v2  - generates candidate rules
2. Concentrator - cleans and expands rules
3. Ranker     - ranks rules using either legacy exhaustive or MAB bandit approach

Environment variables (mirrors ruleflow.sh behaviour — set any before running
to skip the interactive prompts for that value):

  PIPE_BASE_WORDLIST          base wordlist path
  PIPE_TARGET_WORDLIST        target wordlist path
  PIPE_CRACKED_LIST           cracked passwords list
  PIPE_MODE                   maximum | balanced | fast | custom  (default: balanced)
  PIPE_LEGACY                 y | n  (default: n)
  PIPE_DEPTH                  int    (default: 3)
  PIPE_GEN_GENERATIONS        int    (default: 300)
  PIPE_GENETIC_POP            int    (default: 600)
  PIPE_TARGET_HOURS           float  (default: 2.0)
  PIPE_BLOOM_MB               int    (default: 800)
  PIPE_STAGE0_PROCESSES       int    (default: 0)
  PIPE_TOKEN_STRIP_MAX_PREFIX int    (default: 4)
  PIPE_TOKEN_STRIP_MAX_SUFFIX int    (default: 4)
  PIPE_RANKER_K               int    (default: mode preset)
  PIPE_RANKER_MAB_SCREENING   int    (default: mode preset)
  PIPE_RANKER_MAB_FINAL       int    (default: mode preset)
  PIPE_RANKER_PRESET          str    (default: mode preset)
"""

import os
import sys
import subprocess
import glob
import threading
from typing import List, Optional

# =============================================================================
# FORCE IMMEDIATE OUTPUT (no buffering)
# =============================================================================
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

print("\n[INFO] ruleflow.py started (streaming output mode)", flush=True)

# =============================================================================
# Widen the terminal on Windows so PowerShell doesn't truncate output
# =============================================================================
if sys.platform == "win32":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # Get the current console screen buffer info
        class _COORD(ctypes.Structure):
            _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]
        class _SMALL_RECT(ctypes.Structure):
            _fields_ = [("Left", ctypes.c_short), ("Top", ctypes.c_short),
                        ("Right", ctypes.c_short), ("Bottom", ctypes.c_short)]
        class _CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
            _fields_ = [("dwSize", _COORD), ("dwCursorPosition", _COORD),
                        ("wAttributes", ctypes.c_ushort), ("srWindow", _SMALL_RECT),
                        ("dwMaximumWindowSize", _COORD)]
        hStdOut = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        csbi = _CONSOLE_SCREEN_BUFFER_INFO()
        if kernel32.GetConsoleScreenBufferInfo(hStdOut, ctypes.byref(csbi)):
            desired_width = 260
            cur_width = csbi.dwSize.X
            if cur_width < desired_width:
                # First widen the buffer, then the window
                new_size = _COORD(desired_width, csbi.dwSize.Y)
                kernel32.SetConsoleScreenBufferSize(hStdOut, new_size)
                rect = csbi.srWindow
                rect.Right = rect.Left + desired_width - 1
                kernel32.SetConsoleWindowInfo(hStdOut, True, ctypes.byref(rect))
    except Exception:
        pass  # non-fatal; wide output is a convenience, not a requirement

# =============================================================================
# Cross-platform color support (with fallback)
# =============================================================================
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    HAS_COLOR = True
except ImportError:
    HAS_COLOR = False
    class Fore:
        RED     = ''
        GREEN   = ''
        YELLOW  = ''
        BLUE    = ''
        MAGENTA = ''
        CYAN    = ''
        WHITE   = ''
        RESET   = ''
    class Style:
        BRIGHT    = ''
        DIM       = ''
        NORMAL    = ''
        RESET_ALL = ''

# Force UTF-8 on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass


def cprint(text: str, color: str = Fore.WHITE, bright: bool = False, end: str = '\n') -> None:
    style = Style.BRIGHT if bright else Style.NORMAL
    if HAS_COLOR:
        print(f"{style}{color}{text}{Style.RESET_ALL}", end=end, flush=True)
    else:
        print(text, end=end, flush=True)

def print_header() -> None:
    cprint("\n╔════════════════════════════════════════════════════════════════╗", Fore.CYAN, bright=True)
    cprint("║ INTERACTIVE HASHCAT RULE PIPELINE       (Python)               ║", Fore.CYAN, bright=True)
    cprint("╚════════════════════════════════════════════════════════════════╝", Fore.CYAN, bright=True)

def print_step(step_num: int, name: str) -> None:
    cprint(f"\n[{step_num}/3] {name}...", Fore.BLUE, bright=True)

def print_error(msg: str) -> None:
    cprint(f"Error: {msg}", Fore.RED, bright=True)

def print_success(msg: str) -> None:
    cprint(f"→ {msg}", Fore.GREEN, bright=True)

def print_info(msg: str) -> None:
    cprint(f"→ {msg}", Fore.CYAN)

def print_warning(msg: str) -> None:
    cprint(f"→ {msg}", Fore.YELLOW)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _env(key: str) -> Optional[str]:
    v = os.environ.get(key, "").strip()
    return v if v else None


def get_input(prompt: str, default: Optional[str] = None, env_key: Optional[str] = None) -> str:
    if env_key:
        env_val = _env(env_key)
        if env_val is not None:
            cprint(f"  {prompt}: {env_val}  (from {env_key})", Fore.MAGENTA)
            return env_val

    display_prompt = f"{prompt} [{default}]: " if default is not None else f"{prompt}: "
    sys.stdout.flush()
    value = input(display_prompt).strip()
    if value == "" and default is not None:
        return default
    return value


def file_exists(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.R_OK)


def _build_env() -> dict:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _stream_and_wait(proc: subprocess.Popen, description: str, timeout_seconds: int) -> bool:
    """Stream stdout of a running process, enforce timeout, return True on rc==0."""
    timed_out = threading.Event()

    def _kill():
        timed_out.set()
        proc.kill()

    timer = threading.Timer(timeout_seconds, _kill)
    timer.daemon = True
    timer.start()

    for line in proc.stdout:
        print(line, end='', flush=True)

    proc.wait()
    timer.cancel()

    if timed_out.is_set():
        print_error(f"{description} killed after {timeout_seconds}s timeout")
        return False
    if proc.returncode == 0:
        print_success(f"{description} completed successfully")
        return True
    print_error(f"{description} failed with exit code {proc.returncode}")
    return False


def _open_console_stdin():
    """
    Return a file object connected to the real keyboard even when ruleflow's
    own stdin is a pipe or DEVNULL.
      Windows : CONIN$   — Win32 console input buffer
      Unix    : /dev/tty — controlling terminal
    Returns None when no real console exists (pure CI / no-TTY environment).
    """
    if sys.platform == "win32":
        try:
            return open("CONIN$", "rb", buffering=0)
        except OSError:
            return None
    else:
        try:
            return open("/dev/tty", "rb", buffering=0)
        except OSError:
            return None


def run_command_streaming(cmd: List[str], description: str, timeout_seconds: int = 3600) -> bool:
    """
    Run a command with real-time streaming output and a timeout.

    stdin is wired to the real console (CONIN$ / /dev/tty) so that
    interactive keystrokes (p/r/q in rulest) reach the child process even
    though ruleflow's own stdin may be a pipe or DEVNULL.
    Falls back to DEVNULL if no real console is available.

    CREATE_NO_WINDOW is intentionally NOT set — the child must share the
    console so CONIN$ / /dev/tty are reachable from inside it.
    """
    cprint(f"\n→ Running: {' '.join(cmd)}", Fore.MAGENTA, bright=True)
    cprint(f"→ (output will appear below, timeout after {timeout_seconds} seconds)", Fore.CYAN)
    cprint(f"→ (keyboard: p = pause  |  r = resume  |  q = save & quit)", Fore.CYAN)
    sys.stdout.flush()

    console_fh = _open_console_stdin()
    stdin_arg  = console_fh if console_fh is not None else subprocess.DEVNULL

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=stdin_arg,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_build_env(),
            bufsize=1,
            creationflags=0,
        )
        return _stream_and_wait(proc, description, timeout_seconds)
    except FileNotFoundError:
        print_error(f"Command not found: {cmd[0]}. Ensure Python and all scripts are in PATH.")
        return False
    except Exception as e:
        print_error(f"Unexpected error running {description}: {e}")
        return False
    finally:
        if console_fh is not None:
            try:
                console_fh.close()
            except OSError:
                pass


def run_command_with_stdin(cmd: List[str], description: str,
                           stdin_input: str, timeout_seconds: int = 3600) -> bool:
    """
    Run a command that expects interactive stdin input (e.g. concentrator's menu).
    stdin_input is written to the process stdin after launch so menu prompts are
    answered non-interactively.  stdout/stderr are still streamed to the console.
    Returns True on success, False on failure or timeout.
    """
    cprint(f"\n→ Running: {' '.join(cmd)}", Fore.MAGENTA, bright=True)
    cprint(f"→ (non-interactive stdin supplied, timeout after {timeout_seconds} seconds)", Fore.CYAN)
    sys.stdout.flush()

    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_build_env(),
            bufsize=1,
            creationflags=creationflags,
        )

    # Write menu answers then close stdin so the process sees EOF after
        # it has consumed the keystrokes.  Use a thread so we don't block on
        # a process that might buffer its output before printing the prompt.
        #
        # Sequence for concentrator's interactive menu:
        #   s  → "SAVE current rules"          (main menu)
        #   1  → "Auto filename"               (save sub-menu)
        #   q  → "QUIT"                        (main menu, after save returns)
        #
        # We write all answers up-front and leave the pipe open until the
        # process exits — closing too early causes an EOFError when concentrator
        # tries to read the save sub-menu prompt after stdin is already closed.
        def _write_stdin():
            try:
                for answer in stdin_input.splitlines(keepends=True):
                    proc.stdin.write(answer)
                    proc.stdin.flush()
                # Do NOT close stdin here; let the process exit on its own.
                # The pipe is closed automatically when the process terminates.
            except (BrokenPipeError, OSError):
                pass  # process already exited — harmless

        writer = threading.Thread(target=_write_stdin, daemon=True)
        writer.start()

        return _stream_and_wait(proc, description, timeout_seconds)
    except FileNotFoundError:
        print_error(f"Command not found: {cmd[0]}. Ensure Python and all scripts are in PATH.")
        return False
    except Exception as e:
        print_error(f"Unexpected error running {description}: {e}")
        return False


# =============================================================================
# Main pipeline
# =============================================================================

def main() -> None:
    print_header()

    # ------------------------------------------------------------------ #
    # Step 1 — Input files                                                #
    # ------------------------------------------------------------------ #
    cprint("\n=== Step 1: Input Files ===", Fore.YELLOW, bright=True)
    base_wordlist   = get_input("Base wordlist path",                         env_key="PIPE_BASE_WORDLIST")
    target_wordlist = get_input("Target wordlist path",                       env_key="PIPE_TARGET_WORDLIST")
    cracked_list    = get_input("Cracked passwords list (required for Ranker)", env_key="PIPE_CRACKED_LIST")

    for label, path in [
        ("Base wordlist",   base_wordlist),
        ("Target wordlist", target_wordlist),
        ("Cracked list",    cracked_list),
    ]:
        if not file_exists(path):
            print_error(f"{label} not found: {path}")
            sys.exit(1)

    # ------------------------------------------------------------------ #
    # Step 2 — Pipeline mode                                              #
    # ------------------------------------------------------------------ #
    cprint("\n=== Step 2: Pipeline Mode ===", Fore.YELLOW, bright=True)
    print("1) Maximum Quality")
    print("2) Balanced (Recommended)")
    print("3) Fast & Light")
    print("4) Custom (Full Control)")
    mode_choice = get_input("Select mode (1-4)", "2", env_key="PIPE_MODE")

    mode_map = {"1": "maximum", "2": "balanced", "3": "fast", "4": "custom",
                "maximum": "maximum", "balanced": "balanced",
                "fast": "fast", "custom": "custom"}
    mode = mode_map.get(mode_choice.lower(), "balanced")

    # ------------------------------------------------------------------ #
    # Step 3 — Ranking mode                                               #
    # ------------------------------------------------------------------ #
    cprint("\n=== Step 3: Ranking Mode ===", Fore.YELLOW, bright=True)
    legacy_choice = get_input("Use legacy (exhaustive) ranker mode? (y/n)", "n", env_key="PIPE_LEGACY").lower()
    legacy_mode = (legacy_choice == "y")

    # ------------------------------------------------------------------ #
    # Default parameters (same as sh script)                              #
    # ------------------------------------------------------------------ #
    depth                   = 3
    gen_generations         = 300
    genetic_pop             = 600
    target_hours            = 2.0
    bloom_mb                = 800
    stage0_processes        = 0
    token_strip_max_prefix  = 4
    token_strip_max_suffix  = 4

    ranker_k                = 18000
    ranker_mab_screening    = 4
    ranker_mab_final        = 8
    ranker_preset           = "medium_memory"

    # Mode presets
    if mode == "maximum":
        ranker_k = 25000; ranker_mab_screening = 5; ranker_mab_final = 10; ranker_preset = "high_memory"
    elif mode == "balanced":
        ranker_k = 18000; ranker_mab_screening = 4; ranker_mab_final = 8;  ranker_preset = "medium_memory"
    elif mode == "fast":
        ranker_k = 12000; ranker_mab_screening = 3; ranker_mab_final = 5;  ranker_preset = "low_memory"

    # ------------------------------------------------------------------ #
    # Apply environment-variable overrides for numeric params             #
    # ------------------------------------------------------------------ #
    def _ei(key, current):
        v = _env(key)
        if v and v.isdigit():
            return int(v)
        return current

    def _ef(key, current):
        v = _env(key)
        if v:
            try: return float(v)
            except ValueError: pass
        return current

    def _es(key, current):
        v = _env(key)
        return v if v else current

    depth                  = _ei("PIPE_DEPTH",                   depth)
    gen_generations        = _ei("PIPE_GEN_GENERATIONS",         gen_generations)
    genetic_pop            = _ei("PIPE_GENETIC_POP",             genetic_pop)
    target_hours           = _ef("PIPE_TARGET_HOURS",            target_hours)
    bloom_mb               = _ei("PIPE_BLOOM_MB",                bloom_mb)
    stage0_processes       = _ei("PIPE_STAGE0_PROCESSES",        stage0_processes)
    token_strip_max_prefix = _ei("PIPE_TOKEN_STRIP_MAX_PREFIX",  token_strip_max_prefix)
    token_strip_max_suffix = _ei("PIPE_TOKEN_STRIP_MAX_SUFFIX",  token_strip_max_suffix)
    ranker_k               = _ei("PIPE_RANKER_K",                ranker_k)
    ranker_mab_screening   = _ei("PIPE_RANKER_MAB_SCREENING",    ranker_mab_screening)
    ranker_mab_final       = _ei("PIPE_RANKER_MAB_FINAL",        ranker_mab_final)
    ranker_preset          = _es("PIPE_RANKER_PRESET",           ranker_preset)

    # ------------------------------------------------------------------ #
    # Custom / Maximum — interactive overrides                            #
    # ------------------------------------------------------------------ #
    if mode in ("custom", "maximum"):
        cprint("\n=== Advanced Configuration ===", Fore.CYAN, bright=True)

        cprint("--- Rulest Core Settings ---", Fore.YELLOW, bright=True)
        v = get_input("Rulest Max Depth [3-4]",          str(depth))
        if v.isdigit(): depth = int(v)

        v = get_input("Genetic Generations [40-120]",    str(gen_generations))
        if v.isdigit(): gen_generations = int(v)

        v = get_input("Genetic Population [100-400]",    str(genetic_pop))
        if v.isdigit(): genetic_pop = int(v)

        v = get_input("Rulest Target Hours [0.5-5.0]",   str(target_hours))
        try: target_hours = float(v)
        except ValueError: pass

        cprint("--- Rulest Bloom & Stage 0 ---", Fore.YELLOW, bright=True)
        v = get_input("Bloom Filter Size (MB) [400-2000]", str(bloom_mb))
        if v.isdigit(): bloom_mb = int(v)

        v = get_input("Stage 0 Processes (0=auto)",      str(stage0_processes))
        if v.isdigit(): stage0_processes = int(v)

        v = get_input("Token-Strip Max Prefix Length",   str(token_strip_max_prefix))
        if v.isdigit(): token_strip_max_prefix = int(v)

        v = get_input("Token-Strip Max Suffix Length",   str(token_strip_max_suffix))
        if v.isdigit(): token_strip_max_suffix = int(v)

        cprint("--- Ranker Settings ---", Fore.YELLOW, bright=True)
        v = get_input("Final top rules to keep",         str(ranker_k))
        if v.isdigit(): ranker_k = int(v)

        if not legacy_mode:
            v = get_input("MAB Screening Trials",        str(ranker_mab_screening))
            if v.isdigit(): ranker_mab_screening = int(v)

            v = get_input("MAB Final Trials",            str(ranker_mab_final))
            if v.isdigit(): ranker_mab_final = int(v)

        v = get_input("Ranker Preset",                   ranker_preset)
        if v.strip(): ranker_preset = v.strip()

    # ------------------------------------------------------------------ #
    # Execution                                                           #
    # ------------------------------------------------------------------ #
    cprint(f"\nStarting {mode} Pipeline (Rulest → Concentrator → Ranker)...", Fore.GREEN, bright=True)

    # 1. Rulest -----------------------------------------------------------
    print_step(1, "Rulest")
    # Verify rulest_v2.py exists
    if not os.path.isfile("rulest_v2.py"):
        print_error("rulest_v2.py not found in current directory!")
        sys.exit(1)

    rulest_cmd = [
        sys.executable, "rulest_v2.py",
        base_wordlist, target_wordlist,
        "-o", "stage1_raw.rule",
        "--max-depth", str(depth),
        "--token-strip",
        "--genetic",
        "--genetic-generations", str(gen_generations),
        "--genetic-pop",         str(genetic_pop),
        "--target-hours",        str(target_hours),
        "--bloom-mb",            str(bloom_mb),
        "--token-strip-max-prefix", str(token_strip_max_prefix),
        "--token-strip-max-suffix", str(token_strip_max_suffix),
        "--token-strip-workers",    str(stage0_processes),
    ]
    if not run_command_streaming(rulest_cmd, "Rulest", timeout_seconds=7200):
        sys.exit(1)

    # Verify output
    if not os.path.isfile("stage1_raw.rule") or os.path.getsize("stage1_raw.rule") == 0:
        print_error("Rulest did not create a non‑empty 'stage1_raw.rule' file.")
        sys.exit(1)
    print_success("Rulest output verified: stage1_raw.rule")

    # 2. Concentrator -----------------------------------------------------
    print_step(2, "Concentrator")
    if not os.path.isfile("concentrator.py"):
        print_error("concentrator.py not found in current directory!")
        sys.exit(1)

    concentrator_cmd = [
        sys.executable, "concentrator.py",
        "-p", "stage1_raw.rule",
        "-ob", "stage2_cleaned",   # hyphen form that argparse normalises to
        "-f", "line",
    ]
    # Concentrator always enters its interactive menu after loading rules.
    # We drive it non-interactively by feeding:
    #   s  → "SAVE current rules" (writes stage2_cleaned*.rule)
    #   q  → "QUIT"
    # A small sleep marker (\n) before each ensures the prompt is flushed
    # before we send the next keystroke.
    concentrator_stdin = "s\n1\nq\n"
    if not run_command_with_stdin(concentrator_cmd, "Concentrator",
                                  stdin_input=concentrator_stdin,
                                  timeout_seconds=1800):
        sys.exit(1)

    # Pick the newest matching output file (guards against stale files from
    # prior runs appearing first in an unsorted glob).
    cleaned_rule_files = sorted(
        glob.glob("stage2_cleaned*.rule"),
        key=os.path.getmtime,
        reverse=True,
    )
    if not cleaned_rule_files:
        print_error("Concentrator did not produce any 'stage2_cleaned*.rule' file.")
        sys.exit(1)
    cleaned_rule = cleaned_rule_files[0]
    print_success(f"Using: {cleaned_rule}")

    # 3. Ranker -----------------------------------------------------------
    print_step(3, "Ranker")
    if not os.path.isfile("ranker.py"):
        print_error("ranker.py not found in current directory!")
        sys.exit(1)

    ranker_cmd = [
        sys.executable, "ranker.py",
        "-w", base_wordlist,
        "-r", cleaned_rule,
        "-c", cracked_list,
        "-o", "stage3_ranking.csv",
        "-k", str(ranker_k),
        "--preset", ranker_preset,
    ]

    if legacy_mode:
        print_warning("Running in LEGACY (exhaustive) mode.")
        ranker_cmd.append("--legacy")
    else:
        print_info(f"Running in MAB mode (screening={ranker_mab_screening}, final={ranker_mab_final}).")
        ranker_cmd.extend(["--mab-screening-trials", str(ranker_mab_screening)])
        ranker_cmd.extend(["--mab-final-trials",     str(ranker_mab_final)])

    if not run_command_streaming(ranker_cmd, "Ranker", timeout_seconds=14400):
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # Done                                                                #
    # ------------------------------------------------------------------ #
    cprint("\nPipeline completed successfully!", Fore.GREEN, bright=True)
    print_success("Ranking results: stage3_ranking.csv")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        cprint("\n\nPipeline interrupted by user.", Fore.YELLOW, bright=True)
        sys.exit(130)
    except Exception as e:
        print_error(f"Unhandled exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

