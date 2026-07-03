
# 🔐 Interactive Hashcat Rule Pipeline

&gt; An automated, interactive pipeline for generating, cleaning, and ranking Hashcat rules using genetic algorithms, bloom filters, and multi-armed bandit optimization.  
&gt; Now includes **RCR** — a modern dark-themed GUI front-end for the full chain.

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

You can run the pipeline via the classic **bash script** (`ruleflow.sh`) or through **RCR** (`rcr.py`) — a dark-themed Tkinter GUI that wraps the entire chain with real-time logs, memory monitoring, device scanning, and one-click low-memory recovery.

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

### RCR GUI (New)
- **Dark modern UI** — GitHub-inspired color palette with ANSI color rendering
- **Live execution log** — Searchable, auto-trimming, with follow/pause toggle
- **Memory monitor** — Real-time RAM tracking with automatic pressure warnings
- **OpenCL device scanner** — Detects GPUs without leaving the app
- **OOM auto-recovery** — Detects out-of-memory crashes and offers one-click low-memory preset
- **Legacy vs MAB ranker** — Choose exhaustive or adaptive ranking without editing commands
- **Tabbed configuration** — Pipeline, Output & Ranker, and Advanced settings

---

## Requirements

### System Dependencies
- `bash` 4.0+
- `python` 3.8+
- `hashcat` (for rule testing/validation)
- `tkinter` 8.6+ (for RCR GUI)

### Python Scripts
The following scripts must be present in the working directory:

| Script | Purpose |
|--------|---------|
| `rulest_v2.py` | Rule generation engine |
| `concentrator.py` | Rule deduplication & cleaning |
| `ranker.py` | Rule ranking & evaluation |
| `rcr.py` | **GUI front-end** (optional) |

### Input Files

| File | Description | Required |
|------|-------------|----------|
| `Base Wordlist` | Source words for rule generation | ✅ Yes |
| `Target Wordlist` | Words to match against | ✅ Yes |
| `Cracked Passwords` | Previously cracked hashes for ranking | ✅ Yes |

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
wget https://github.com/A113L/ruleflow/raw/refs/heads/main/rcr.py

# Ensure Python scripts are executable
chmod +x rulest_v2.py concentrator.py ranker.py rcr.py

# Run the CLI pipeline
chmod +x ruleflow.sh
./ruleflow.sh

# Or launch the GUI
python rcr.py
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
python rcr.py
```

**Workflow:**
1. **Pipeline tab** — Select your three input files, output directory, and pipeline mode (Maximum / Balanced / Fast / Custom)
2. **Output & Ranker tab** — Choose concentrator format (expanded vs compact) and ranker strategy:
   - **Legacy (Exhaustive)** — Recommended default. Full accuracy, lower RAM, usually faster in practice.
   - **MAB (Multi-Armed Bandit)** — Best for very large or heavily imbalanced rule sets where early elimination pays off.
3. **Advanced tab** — Fine-tune genetic generations, bloom filter size, token-strip depth, MAB trials, and memory preset.
4. Click **▶ Run Pipeline** — Watch live logs, memory usage, and stage indicators.

**GUI Tips:**
- Click **⟳ Scan** on the Pipeline tab to detect OpenCL devices.
- If a stage crashes with an OOM error, RCR will pop up a dialog to apply the **Low-Memory preset** automatically.
- Use the log search box to find specific rules or errors in long runs.
- The log auto-trims after 12,000 lines to keep the UI responsive.

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
    -k 18000 \
    --legacy \
    --preset medium_memory

# MAB (for very large / imbalanced sets)
python ranker.py \
    -w "$BASE_WORDLIST" \
    -r "$CLEANED_RULE" \
    -c "$CRACKED_LIST" \
    -o stage3_ranking.csv \
    -k 18000 \
    --mab-screening-trials 4 \
    --mab-final-trials 8 \
    --preset medium_memory
```

**Output**: `stage3_ranking.csv`, `stage3_ranking_optimized.rule`

---

## RCR GUI Reference

| UI Element | Function |
|------------|----------|
| **Mode Cards** | One-click presets that auto-populate all advanced sliders |
| **Device Scanner** | Queries `rulest_v2.py --list-devices` and populates the GPU dropdown |
| **Memory Label** | Live RAM usage of RCR + child processes (requires `psutil`) |
| **Log Panel** | ANSI-aware colored output, search with Prev/Next, follow toggle |
| **Low-Memory Dialog** | Auto-triggered on OOM detection; applies `low_memory` preset + reduced parameters |
| **Stage Dots** | Visual progress indicator for rulest → concentrator → ranker |

---

## Parameters Reference

### Mode Presets

| Parameter | Maximum | Balanced | Fast |
|-----------|---------|----------|------|
| `RANKER_K` | 100000 | 18000 | 50000 |
| `MAB_SCREENING` | 5 | 4 | 3 |
| `MAB_FINAL` | 10 | 8 | 5 |
| `PRESET` | `medium_memory` | `medium_memory` | `medium_memory` |
| `DEPTH` | 10 | 6 | 3 |
| `GEN_GENERATIONS` | 300 | 300 | 300 |
| `GENETIC_POP` | 600 | 600 | 600 |

### Default Values

| Parameter | Default |
|-----------|---------|
| `DEPTH` | 6 |
| `GEN_GENERATIONS` | 300 |
| `GENETIC_POP` | 600 |
| `TARGET_HOURS` | 2.0 |
| `BLOOM_MB` | 256 |
| `TOKEN_STRIP_MAX_PREFIX` | 4 |
| `TOKEN_STRIP_MAX_SUFFIX` | 4 |

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
# 1. Select base.txt, target_wordlist.txt, cracked.txt
# 2. Choose "Balanced" mode
# 3. On "Output & Ranker" tab, keep "Legacy (Exhaustive)" selected
# 4. Click "▶ Run Pipeline"
# 5. Copy stage3_ranking_optimized.rule to your hashcat command
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `Base or Target wordlist not found!` | Verify file paths are correct and files exist |
| `Cracked list not found!` | Ranker requires a cracked passwords file. Generate one first |
| `Could not find Concentrator output!` | Check that `concentrator.py` generated `stage2_cleaned*.rule` |
| Out of Memory | Reduce `BLOOM_MB`, switch to `low_memory` preset, or use **Fast** mode |
| Slow performance | Use **Fast & Light** mode, reduce `GEN_GENERATIONS`, or lower `TARGET_HOURS` |
| RCR GUI won't start | Ensure `tkinter` is installed (`sudo apt install python3-tk` on Debian/Ubuntu) |
| RCR shows "n/a" for RAM | Install `psutil` (`pip install psutil`) for live memory tracking |

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
