# 🔐 Interactive Hashcat Rule Pipeline

> An automated, interactive pipeline for generating, cleaning, and ranking Hashcat rules using genetic algorithms, bloom filters, and multi-armed bandit optimization.
> Now includes **RCR** — a modern dark/light-themed GUI front-end for the full chain.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Bash](https://img.shields.io/badge/Bash-4.0%2B-green.svg)](https://www.gnu.org/software/bash/)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![Tkinter](https://img.shields.io/badge/Tkinter-8.6%2B-purple.svg)](https://docs.python.org/3/library/tkinter.html)

---

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
  - [Quick Start (CLI)](#quick-start-cli)
  - [RCR GUI](#rcr-gui)
  - [Pipeline Modes](#pipeline-modes)
  - [Advanced Configuration](#advanced-configuration)
- [Pipeline Stages](#pipeline-stages)
  - [1. Rulest](#1-rulest)
  - [2. Concentrator](#2-concentrator)
  - [3. Ranker](#3-ranker)
- [RCR GUI Reference](#rcr-gui-reference)
- [Parameters Reference](#parameters-reference)
- [Output Files](#output-files)
- [Example Workflow](#example-workflow)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Overview

This project automates the creation of high-quality Hashcat rules through a three-stage process:

1. **Rulest** — Generates raw rules using token-stripping and genetic algorithms
2. **Concentrator** — Cleans and deduplicates the rule set
3. **Ranker** — Ranks rules by effectiveness using exhaustive or Multi-Armed Bandit (MAB) screening

You can run the pipeline via the classic **bash script** (`ruleflow.sh`) or through **RCR** (`rcr.py`) — a Tkinter GUI that wraps the entire chain with real-time logs, memory monitoring, device scanning, selective stage execution, and one-click low-memory recovery.

---

## Features

### Core Pipeline
- **4 Preset Modes**: Maximum Quality, Balanced, Fast & Light, or Full Custom Control
- **Genetic Algorithm**: Evolves rules over multiple generations for optimal coverage
- **Bloom Filter**: Memory-efficient duplicate detection during rule generation
- **MAB Ranking**: Multi-Armed Bandit trials for statistically robust rule ranking
- **Token Stripping**: Automatic prefix/suffix tokenization for better rule derivation
- **Interactive UI**: Color-coded terminal prompts with sensible defaults (bash)
- **Auto-Detection**: Automatically locates concentrator output files

### RCR GUI
- **Dark & Light themes** — Toggle between a GitHub-inspired dark palette and a matching light palette at runtime; all widgets and log colors (including live ANSI output) re-theme instantly
- **Selective stage execution** — Run any combination of rulest / concentrator / ranker. Skipping rulest lets you feed in an external `.rule` file instead
- **Advanced concentrator filtering** — Five independent post-processing filters (min occurrence, top-N cap, functional redundancy, inverse cut-off, hashcat rule validation) applied by concentrator.py itself, so the GUI and CLI always agree on the result
- **Live execution log** — Searchable (Prev/Next), with a follow/pause toggle; nothing is ever trimmed or dropped — the full run is kept on screen and mirrored to disk
- **Memory monitor** — Real-time RAM tracking (RCR + child processes) with automatic pressure warnings
- **OpenCL device scanner** — Detects GPUs without leaving the app
- **OOM auto-recovery** — Detects out-of-memory crashes and offers a one-click Low-Memory preset dialog
- **Legacy vs MAB ranker** — Choose exhaustive or adaptive ranking without editing commands, with in-app guidance on which fits your rule set
- **Tabbed configuration** — Pipeline, Output & Ranker, and Advanced settings

[![ruleflow.jpg](https://i.postimg.cc/nzp8pZRb/ruleflow.jpg)](https://postimg.cc/kV1YyrPf)

## Requirements

### System Dependencies
- `bash` 4.0+
- `python` 3.8+
- `hashcat` (for rule testing/validation)
- `tkinter` 8.6+ (for RCR GUI)
- `psutil` (optional, enables live RAM tracking in RCR)

### Python Scripts
The following scripts must be present in the working directory:

| Script | Purpose |
|--------|---------|
| `rulest_v2.py` | Rule generation engine |
| `concentrator.py` | Rule deduplication & cleaning |
| `ranker.py` | Rule ranking & evaluation |
| `RCR` | **GUI front-end** (optional) |

### Input Files

| File | Description | Required |
|------|-------------|----------|
| `Base Wordlist` | Source words for rule generation | ✅ Yes (when running rulest or ranker) |
| `Target Wordlist` | Words to match against | ✅ Yes (when running rulest) |
| `Cracked Passwords` | Previously cracked hashes for ranking | ✅ Yes (when running ranker) |
| `External Rules File` | Pre-built `.rule` file | Only if rulest is skipped |

---

## Installation

```bash
# Clone or download the repository
git clone https://github.com/A113L/ruleflow.git
cd ruleflow

# Download the three core engines
wget https://raw.githubusercontent.com/A113L/rulest/refs/heads/main/rulest_v2.py
wget https://raw.githubusercontent.com/A113L/concentrator/refs/heads/main/concentrator.py
wget https://github.com/A113L/ranker/raw/refs/heads/main/ranker.py

# Download the GUI front-end (optional)
wget -O rcr.py https://github.com/A113L/ruleflow/raw/refs/heads/main/RCR

# Ensure Python scripts are executable
chmod +x rulest_v2.py concentrator.py ranker.py RCR

# Run the CLI pipeline
chmod +x ruleflow.sh
./ruleflow.sh

# Or launch the GUI
python RCR
```

---

## Usage

### Quick Start (CLI)

Simply run the script and follow the interactive prompts:

```bash
./ruleflow.sh
```

You will be prompted for:
1. **Base wordlist path** — Your source dictionary
2. **Target wordlist path** — Words you want to crack
3. **Cracked passwords list** — Previous cracks for ranking calibration
4. **Pipeline mode** — Select preset or custom configuration

### RCR GUI

Launch the graphical runner:

```bash
python RCR
```

**Workflow:**
1. **Pipeline tab**
   - **Step 0 — Select Stages to Run**: tick/untick rulest, concentrator, and ranker independently. If rulest is unticked, an "External Rules Input" file picker appears — its `.rule` file is fed directly into whichever of concentrator/ranker remain enabled.
   - **Step 1 — Input Files**: base wordlist, target wordlist, cracked passwords, and output directory (only the files needed by your selected stages are required).
   - **Step 2 — Pipeline Mode**: Maximum / Balanced / Fast / Custom.
2. **Output & Ranker tab**
   - **Step 3 — Concentrator Output**: choose expanded (space-separated operators, easier to read/debug) vs compact (single line, slightly faster for hashcat to load) rule format.
   - **Step 3b — Advanced Filtering**: five independent, optional post-processing filters, each passed straight through to `concentrator.py`'s own `--filter-*` flags so the GUI and CLI always produce identical results:
     1. **Minimum occurrence** — drop rules that occur fewer than N times
     2. **Maximum number of rules (top N)** — keep only the top N rules
     3. **Functional redundancy** *(RAM intensive)* — keep one rule per functional signature
     4. **Inverse mode** — keep rules *below* the cut-off rank instead of above it
     5. **Hashcat cleanup** — validate rules against hashcat's own rule syntax, on CPU or GPU
   - **Step 4 — Ranker Strategy**:
     - **Legacy (Exhaustive)** — Recommended default. Tests every rule straight through; no bandit bookkeeping overhead, flatter RAM usage, maximum statistical accuracy. Usually the faster choice on balanced dictionaries.
     - **MAB (Multi-Armed Bandit)** — Adaptive sampling that skips rules that look unpromising early. Pays off mainly on very large (10k+) or heavily imbalanced rule sets; on smaller/balanced ones it can be slower than Legacy due to sampling overhead.
3. **Advanced tab** — Fine-tune genetic generations, bloom filter size, token-strip depth, MAB trials, and memory preset.
4. Click **▶ Run Pipeline** — Watch live logs, memory usage, and stage indicators.

**GUI Tips:**
- Click **⟳ Scan** on the Pipeline tab to detect OpenCL devices.
- All five Step 3b filters are optional and independent — leave them all unchecked for concentrator's default behavior, or combine any subset.
- If a stage crashes with an OOM error, RCR will pop up a dialog to apply the **Low-Memory preset** automatically.
- Use the log search box (with Prev/Next) to find specific rules or errors in long runs.
- The execution log is never trimmed — every line from the run is kept on screen and mirrored to the log file on disk, so nothing is lost even on very long runs.
- Toggle **☀ Light mode / 🌙 Dark mode** in the top-right corner at any time, including mid-run.

### Pipeline Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| **1) Maximum Quality** | Highest accuracy, memory-intensive | Small target sets, maximum yield |
| **2) Balanced** *(Default)* | Best trade-off between speed and quality | General purpose cracking |
| **3) Fast & Light** | Quick results with reduced precision | Large-scale or time-constrained ops |
| **4) Custom** | Full manual control over all parameters | Fine-tuning specific scenarios |

### Advanced Configuration

When selecting **Maximum Quality** or **Custom** mode, you can configure:

#### Rulest Core Settings
- `Max Depth` — Rule derivation depth (1-31)
- `Genetic Generations` — Evolution iterations (20-1000)
- `Genetic Population` — Population size per generation (50-2000)
- `Target Hours` — Time budget for rule generation (0.5-12.0)

#### Bloom & Stage 0
- `Bloom Filter Size` — Memory allocation in MB (100-4000)
- `Stage 0 Processes` — Parallel workers (0 = auto)
- `Token-Strip Prefix/Suffix` — Max token lengths to strip (1-12)

#### Ranker Settings
- `Top-K Rules` — Final rules to retain (1,000-100,000)
- `MAB Screening Trials` — Initial exploration rounds (1-30)
- `MAB Final Trials` — Final evaluation rounds (1-50)
- `Memory Preset` — `low_memory` / `medium_memory` / `high_memory`

---

## Pipeline Stages

### 1. Rulest

Generates candidate rules using:
- **Token Stripping**: Removes common prefixes/suffixes to find core patterns
- **Genetic Evolution**: Breeds successful rules across generations
- **Bloom Filtering**: Prevents duplicate rule generation efficiently

```bash
python rulest_v2.py "$BASE_WORDLIST" "$TARGET_WORDLIST" \
    -o stage1_raw.rule \
    --max-depth 3 \
    --token-strip \
    --genetic \
    --genetic-generations 60 \
    --genetic-pop 200 \
    --target-hours 2.0 \
    --bloom-mb 800
```

**Output**: `stage1_raw.rule`

*(This stage can be skipped entirely in the RCR GUI by unticking "1. rulest" and supplying an external `.rule` file instead.)*

### 2. Concentrator

Cleans the raw rule set by:
- Removing duplicates
- Normalizing rule syntax
- Filtering invalid/ineffective rules

```bash
python concentrator.py -p stage1_raw.rule \
    --output_base_name stage2_cleaned \
    --output-format line
```

**Output**: `stage2_cleaned*.rule` (auto-detected)

**Optional advanced filters** (independent, can be combined; the RCR GUI's Step 3b checkboxes map directly to these):

```bash
python concentrator.py -p stage1_raw.rule \
    --output_base_name stage2_cleaned \
    --output-format line \
    --filter-min-occ 10 \
    --filter-max-rules 10000 \
    --filter-func-redundancy --yes \
    --filter-inverse 1000 \
    --filter-hashcat-cleanup cpu
```

| Flag | Effect |
|------|--------|
| `--filter-min-occ N` | Drop rules occurring fewer than `N` times |
| `--filter-max-rules N` | Keep only the top `N` rules |
| `--filter-func-redundancy` | Keep one rule per functional signature (RAM intensive) |
| `--filter-inverse N` | Keep rules *below* the cut-off rank `N` instead of above it |
| `--filter-hashcat-cleanup {cpu,gpu}` | Validate rules against hashcat's rule syntax |

### 3. Ranker

Ranks rules by empirical performance:
- Tests rules against cracked passwords
- Uses **Legacy (exhaustive)** or **MAB** algorithm for evaluation
- Selects top-K performing rules

```bash
# Legacy (recommended)
python ranker.py \
    -w "$BASE_WORDLIST" \
    -r "$CLEANED_RULE" \
    -c "$CRACKED_LIST" \
    -o stage3_ranking.csv \
    -k 75000 \
    --legacy \
    --preset medium_memory

# MAB (for very large / imbalanced sets)
python ranker.py \
    -w "$BASE_WORDLIST" \
    -r "$CLEANED_RULE" \
    -c "$CRACKED_LIST" \
    -o stage3_ranking.csv \
    -k 75000 \
    --mab-screening-trials 4 \
    --mab-final-trials 8 \
    --preset medium_memory
```

**Output**: `stage3_ranking.csv`, `stage3_ranking_optimized.rule`

---

## RCR GUI Reference

| UI Element | Function |
|------------|----------|
| **Stage Checkboxes** | Enable/disable rulest, concentrator, and ranker independently for this run |
| **External Rules Input** | Appears only when rulest is disabled; supplies the `.rule` file that feeds the remaining stages |
| **Mode Cards** | One-click presets that auto-populate all advanced sliders |
| **Advanced Filtering (Step 3b)** | Five optional concentrator post-processing filters (min occurrence, top-N, functional redundancy, inverse, hashcat cleanup), each independently toggleable |
| **Theme Toggle** | Switches the whole UI (and log colors) between dark and light palettes |
| **Device Scanner** | Queries `rulest_v2.py --list-devices` and populates the GPU dropdown |
| **Memory Label** | Live RAM usage of RCR + child processes (requires `psutil`) |
| **Log Panel** | ANSI-aware colored output, search with Prev/Next, follow/pause toggle, never trimmed |
| **Low-Memory Dialog** | Auto-triggered on OOM detection; applies `low_memory` preset + reduced parameters |
| **Stage Dots** | Visual progress indicator for rulest → concentrator → ranker |

---

## Parameters Reference

### Mode Presets

| Parameter | Maximum | Balanced | Fast |
|-----------|---------|----------|------|
| `RANKER_K` | 100000 | 75000 | 50000 |
| `MAB_SCREENING` | 5 | 4 | 3 |
| `MAB_FINAL` | 10 | 8 | 5 |
| `PRESET` | `medium_memory` | `medium_memory` | `medium_memory` |
| `DEPTH` | 10 | 6 | 3 |
| `GEN_GENERATIONS` | 500 | 300 | 150 |
| `GENETIC_POP` | 1000 | 600 | 300 |
| `TARGET_HOURS` | 2.0 | 1.0 | 0.5 |
| `TOKEN_STRIP_PREFIX/SUFFIX` | 10 | 6 | 3 |

### Default Values (Balanced mode, applied at startup)

| Parameter | Default |
|-----------|---------|
| `DEPTH` | 6 |
| `GEN_GENERATIONS` | 300 |
| `GENETIC_POP` | 600 |
| `TARGET_HOURS` | 1.0 |
| `BLOOM_MB` | 256 |
| `TOKEN_STRIP_MAX_PREFIX` | 6 |
| `TOKEN_STRIP_MAX_SUFFIX` | 6 |
| `RANKER_K` | 75000 |
| `MEMORY_PRESET` | `medium_memory` |

---

## Output Files

| Stage | File | Description |
|-------|------|-------------|
| 1 | `stage1_raw.rule` | Raw generated rules (may contain duplicates) |
| 2 | `stage2_cleaned*.rule` | Deduplicated, cleaned rule set |
| 3 | `stage3_ranking.csv` | Ranked rules with performance metrics |
| 3 | `stage3_ranking_optimized.rule` | Final optimized rules file for hashcat |
| — | `rcr_run_YYYYMMDD_HHMMSS.log` | Full execution log (RCR only) |

---

## Example Workflow

### CLI
```bash
# 1. Prepare your files
ls -la
# base.txt  target_wordlist.txt  cracked.txt  pipeline.sh rulest_v2.py concentrator.py ranker.py

# 2. Run the pipeline
./pipeline.sh

# === Step 1: Input Files ===
# Base wordlist path: base.txt
# Target wordlist path: target_wordlist.txt
# Cracked passwords list: cracked.txt

# === Step 2: Pipeline Mode ===
# Select mode (1-4) [2]: 2

# [1/3] Rulest... (genetic evolution running)
# [2/3] Concentrator... (cleaning rules)
# → Using: stage2_cleaned_line.rule
# [3/3] Ranker... (MAB optimization)

# 3. Use the final ranked rules with Hashcat
hashcat -m 0 -a 0 target_hashes.txt rockyou.txt -r stage3_ranking_optimized.rule
```

### GUI
```bash
python rcr.py
# 1. (Optional) In "Step 0 — Select Stages to Run", untick any stage you want to skip
# 2. Select base.txt, target_wordlist.txt, cracked.txt (or an external .rule file if rulest is skipped)
# 3. Choose "Balanced" mode
# 4. On "Output & Ranker" tab, keep "Legacy (Exhaustive)" selected
# 5. Click "▶ Run Pipeline"
# 6. Copy stage3_ranking_optimized.rule to your hashcat command
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `Base or Target wordlist not found!` | Verify file paths are correct and files exist |
| `Cracked list not found!` | Ranker requires a cracked passwords file. Generate one first |
| `Could not find Concentrator output!` | Check that `concentrator.py` generated `stage2_cleaned*.rule` |
| `Missing Rules File` (GUI) | You unticked rulest but didn't provide an external `.rule` file in "External Rules Input" |
| `No Stage Selected` (GUI) | At least one of rulest / concentrator / ranker must remain enabled |
| Out of Memory | Reduce `BLOOM_MB`, switch to `low_memory` preset, or use **Fast** mode |
| Slow performance | Use **Fast & Light** mode, reduce `GEN_GENERATIONS`, or lower `TARGET_HOURS` |
| RCR GUI won't start | Ensure `tkinter` is installed (`sudo apt install python3-tk` on Debian/Ubuntu) |
| RCR shows "n/a" for RAM | Install `psutil` (`pip install psutil`) for live memory tracking |

---

## Credits

@Shooter3k

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
