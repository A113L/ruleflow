
🔐 Interactive Hashcat Rule Pipeline 2026

> An automated, interactive pipeline for generating, cleaning, and ranking Hashcat rules using genetic algorithms, bloom filters, and multi-armed bandit optimization.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Bash](https://img.shields.io/badge/Bash-4.0%2B-green.svg)](https://www.gnu.org/software/bash/)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)

---

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
  - [Quick Start](#quick-start)
  - [Pipeline Modes](#pipeline-modes)
  - [Advanced Configuration](#advanced-configuration)
- [Pipeline Stages](#pipeline-stages)
  - [1. Rulest](#1-rulest)
  - [2. Concentrator](#2-concentrator)
  - [3. Ranker](#3-ranker)
- [Parameters Reference](#parameters-reference)
- [Output Files](#output-files)
- [Example Workflow](#example-workflow)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Overview

This pipeline automates the creation of high-quality Hashcat rules through a three-stage process:

1. **Rulest** — Generates raw rules using token-stripping and genetic algorithms
2. **Concentrator** — Cleans and deduplicates the rule set
3. **Ranker** — Ranks rules by effectiveness using Multi-Armed Bandit (MAB) screening

The script provides an interactive terminal interface with preset modes for different performance/quality trade-offs.

---

## Features

- **4 Preset Modes**: Maximum Quality, Balanced, Fast & Light, or Full Custom Control
- **Genetic Algorithm**: Evolves rules over multiple generations for optimal coverage
- **Bloom Filter**: Memory-efficient duplicate detection during rule generation
- **MAB Ranking**: Multi-Armed Bandit trials for statistically robust rule ranking
- **Token Stripping**: Automatic prefix/suffix tokenization for better rule derivation
- **Interactive UI**: Color-coded terminal prompts with sensible defaults
- **Auto-Detection**: Automatically locates concentrator output files

---

## Requirements

### System Dependencies
- `bash` 4.0+
- `python` 3.8+
- `hashcat` (for rule testing/validation)

### Python Scripts
The following scripts must be present in the working directory:

| Script | Purpose |
|--------|---------|
| `rulest_v2.py` | Rule generation engine |
| `concentrator.py` | Rule deduplication & cleaning |
| `ranker.py` | Rule ranking & evaluation |

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

wget https://raw.githubusercontent.com/A113L/rulest/refs/heads/main/rulest_v2.py
wget https://raw.githubusercontent.com/A113L/concentrator/refs/heads/main/concentrator.py
wget https://github.com/A113L/ranker/raw/refs/heads/main/ranker.py

# Ensure Python scripts are executable
chmod +x rulest_v2.py concentrator.py ranker.py

# Run the ruleflow
chmod +x ruleflow.sh
./ruleflow.sh
```

---

## Usage

### Quick Start

Simply run the script and follow the interactive prompts:

```bash
./ruleflow.sh
```

You will be prompted for:
1. **Base wordlist path** — Your source dictionary
2. **Target wordlist path** — Words you want to crack
3. **Cracked passwords list** — Previous cracks for ranking calibration
4. **Pipeline mode** — Select preset or custom configuration

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
- `Max Depth` — Rule derivation depth (3-4)
- `Genetic Generations` — Evolution iterations (40-120)
- `Genetic Population` — Population size per generation (100-400)
- `Target Hours` — Time budget for rule generation (0.5-5.0)

#### Bloom & Stage 0
- `Bloom Filter Size` — Memory allocation in MB (400-2000)
- `Stage 0 Processes` — Parallel workers (0 = auto)
- `Token-Strip Prefix/Suffix` — Max token lengths to strip

#### Ranker Settings
- `Top-K Rules` — Final rules to retain (12000-25000)
- `MAB Screening Trials` — Initial exploration rounds (3-5)
- `MAB Final Trials` — Final evaluation rounds (5-10)
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
- Uses Multi-Armed Bandit algorithm for efficient evaluation
- Selects top-K performing rules

```bash
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

## Parameters Reference

### Mode Presets

| Parameter | Maximum | Balanced | Fast |
|-----------|---------|----------|------|
| `RANKER_K` | 50000 | 25000 | 12000 |
| `MAB_SCREENING` | 5 | 4 | 3 |
| `MAB_FINAL` | 10 | 8 | 5 |
| `PRESET` | `high_memory` | `medium_memory` | `low_memory` |
| `DEPTH` | 6* | 6 | 6 |
| `GEN_GENERATIONS` | 300* | 300 | 300 |
| `GENETIC_POP` | 600* | 600 | 600 |

*\*Customizable in Maximum mode*

### Default Values

| Parameter | Default | Range |
|-----------|---------|-------|
| `DEPTH` | 3 | 3-4 |
| `GEN_GENERATIONS` | 60 | 40-120 |
| `GENETIC_POP` | 200 | 100-400 |
| `TARGET_HOURS` | 2.0 | 0.5-5.0 |
| `BLOOM_MB` | 800 | 400-2000 |
| `TOKEN_STRIP_MAX_PREFIX` | 4 | 1-10 |
| `TOKEN_STRIP_MAX_SUFFIX` | 4 | 1-10 |

---

## Output Files

| Stage | File | Description |
|-------|------|-------------|
| 1 | `stage1_raw.rule` | Raw generated rules (may contain duplicates) |
| 2 | `stage2_cleaned*.rule` | Deduplicated, cleaned rule set |
| 3 | `stage3_ranking.csv` | Ranked rules with performance metrics |
| 4 | `stage3_ranking_optimized.rule` | Ranked optimised rules file |

---

## Example Workflow

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

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `Base or Target wordlist not found!` | Verify file paths are correct and files exist |
| `Cracked list not found!` | Ranker requires a cracked passwords file. Generate one first |
| `Could not find Concentrator output!` | Check that `concentrator.py` generated `stage2_cleaned*.rule` |
| Out of Memory | Reduce `BLOOM_MB` or switch to `low_memory` preset |
| Slow performance | Use `Fast & Light` mode or reduce `GEN_GENERATIONS`, manipulate --target-hours |

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

