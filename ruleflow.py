#!/usr/bin/env python3
# =============================================================================
# INTERACTIVE HASHCAT RULE PIPELINE (Python Port)
# =============================================================================
"""
Fully cross-platform (Windows/Linux) interactive pipeline for Hashcat rule generation:
1. Rulest v2  - generates candidate rules
2. Concentrator - cleans and expands rules
3. Ranker     - ranks rules using either legacy exhaustive or MAB bandit approach

Windows fix: forces UTF-8 I/O on all child processes so box-drawing characters
in banners (╔ ║ ╚ etc.) don't crash cp1250 / cp1252 consoles.

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
from typing import List, Optional

# -----------------------------------------------------------------------------
# Cross-platform color support
# -----------------------------------------------------------------------------
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
except ImportError:
    class Fore:
        RED     = '\033[91m'
        GREEN   = '\033[92m'
        YELLOW  = '\033[93m'
        BLUE    = '\033[94m'
        MAGENTA = '\033[95m'
        CYAN    = '\033[96m'
        WHITE   = '\033[97m'
        RESET   = '\033[0m'

    class Style:
        BRIGHT    = '\033[1m'
        DIM       = '\033[2m'
        NORMAL    = '\033[22m'
        RESET_ALL = '\033[0m'

# Force UTF-8 on Windows console so box-drawing chars don't crash cp125x
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass  # Python < 3.7 — colorama fallback handles most cases


def cprint(text: str, color: str = Fore.WHITE, bright: bool = False, end: str = '\n') -> None:
    style = Style.BRIGHT if bright else Style.NORMAL
    print(f"{style}{color}{text}{Style.RESET_ALL}", end=end)

def print_header() -> None:
    cprint("\n╔════════════════════════════════════════════════════════════════╗", Fore.CYAN, bright=True)
    cprint("║ INTERACTIVE HASHCAT RULE PIPELINE (Python)                      ║", Fore.CYAN, bright=True)
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
    """Return stripped env var value or None if unset/empty."""
    v = os.environ.get(key, "").strip()
    return v if v else None


def get_input(prompt: str, default: Optional[str] = None, env_key: Optional[str] = None) -> str:
    """
    Get user input.  Resolution order:
      1. Environment variable (env_key)
      2. Interactive prompt (with default shown)
      3. default value
    """
    if env_key:
        env_val = _env(env_key)
        if env_val is not None:
            cprint(f"  {prompt}: {env_val}  (from {env_key})", Fore.MAGENTA)
            return env_val

    display_prompt = f"{prompt} [{default}]: " if default is not None else f"{prompt}: "
    value = input(display_prompt).strip()
    if value == "" and default is not None:
        return default
    return value


def file_exists(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.R_OK)


def _child_env() -> dict:
    """Build an environment dict that forces UTF-8 in child Python processes."""
    env = os.environ.copy()
    env["PYTHONUTF8"]        = "1"   # Python 3.7+ UTF-8 mode (-X utf8)
    env["PYTHONIOENCODING"]  = "utf-8"
    return env


def run_command(cmd: List[str], description: str) -> bool:
    """
    Run a command, streaming output in real time.
    Child processes inherit a UTF-8-forced environment so their banners
    (╔ ║ ╚ …) don't crash Windows cp125x consoles.
    """
    cprint(f"\n→ Running: {' '.join(cmd)}", Fore.MAGENTA, bright=True)
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            encoding="utf-8",       # read pipe as UTF-8 in this process
            errors="replace",       # replace undecodable bytes rather than crash
            bufsize=1,
            env=_child_env()        # pass UTF-8 env to child
        )
        for line in proc.stdout:
            print(line, end='')
        proc.wait()
        if proc.returncode != 0:
            print_error(f"{description} failed with exit code {proc.returncode}")
            return False
        print_success(f"{description} completed successfully")
        return True
    except FileNotFoundError:
        print_error(f"Command not found: {cmd[0]}. Make sure Python and required scripts are in PATH.")
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

    # Accept either a digit or a name (mirrors sh behaviour)
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
    # (always honoured regardless of mode, same as setting them in sh)   #
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
    if not run_command(rulest_cmd, "Rulest"):
        sys.exit(1)

    # 2. Concentrator -----------------------------------------------------
    print_step(2, "Concentrator")
    concentrator_cmd = [
        sys.executable, "concentrator.py",
        "-p", "stage1_raw.rule",
        "--output_base_name", "stage2_cleaned",
        "--output-format", "expanded",
    ]
    if not run_command(concentrator_cmd, "Concentrator"):
        sys.exit(1)

    cleaned_rule_files = glob.glob("stage2_cleaned*.rule")
    if not cleaned_rule_files:
        print_error("Could not find Concentrator output file (stage2_cleaned*.rule)!")
        sys.exit(1)
    cleaned_rule = cleaned_rule_files[0]
    print_success(f"Using: {cleaned_rule}")

    # 3. Ranker -----------------------------------------------------------
    print_step(3, "Ranker")
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

    if not run_command(ranker_cmd, "Ranker"):
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
