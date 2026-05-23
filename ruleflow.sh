#!/bin/bash
# =============================================================================
# INTERACTIVE HASHCAT RULE PIPELINE 2026
# =============================================================================
echo -e "\033[1;36m"
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║ INTERACTIVE HASHCAT RULE PIPELINE v2026                        ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo -e "\033[0m"

# ====================== DEPENDENCY CHECK ======================
echo -e "\n\033[1;33m=== Checking Required Scripts ===\033[0m"
MISSING=()
if [ ! -f "rulest_v2.py" ]; then MISSING+=("rulest_v2.py"); fi
if [ ! -f "concentrator.py" ]; then MISSING+=("concentrator.py"); fi
if [ ! -f "ranker.py" ]; then MISSING+=("ranker.py"); fi

if [ ${#MISSING[@]} -gt 0 ]; then
    echo -e "\033[1;31mMissing scripts: ${MISSING[*]}\033[0m"
    read -p "Download missing scripts? (y/n): " CONFIRM_DL
    if [[ "$CONFIRM_DL" =~ ^[Yy]$ ]]; then
        for script in "${MISSING[@]}"; do
            case "$script" in
                rulest_v2.py) URL="https://raw.githubusercontent.com/A113L/rulest/refs/heads/main/rulest_v2.py" ;;
                concentrator.py) URL="https://raw.githubusercontent.com/A113L/concentrator/refs/heads/main/concentrator.py" ;;
                ranker.py) URL="https://raw.githubusercontent.com/A113L/ranker/refs/heads/main/ranker.py" ;;
            esac
            echo -e "\033[1;34mDownloading $script...\033[0m"
            wget -q --show-progress "$URL" -O "$script" && echo -e "\033[1;32m✓ $script OK\033[0m" || exit 1
        done
    else
        echo -e "\033[1;31mCannot continue.\033[0m"
        exit 1
    fi
else
    echo -e "\033[1;32mAll scripts present.\033[0m"
fi

# ====================== INPUT FILES ======================
echo -e "\n\033[1;33m=== Step 1: Input Files ===\033[0m"
read -p "Base wordlist path: " BASE_WORDLIST
read -p "Target wordlist path: " TARGET_WORDLIST
read -p "Cracked passwords list: " CRACKED_LIST

for f in "$BASE_WORDLIST" "$TARGET_WORDLIST" "$CRACKED_LIST"; do
    [ ! -f "$f" ] && { echo -e "\033[1;31mError: $f not found!\033[0m"; exit 1; }
done

# ====================== MODE SELECTION ======================
echo -e "\n\033[1;33m=== Step 2: Pipeline Mode ===\033[0m"
echo "1) Maximum Quality"
echo "2) Balanced (Recommended)"
echo "3) Fast & Light"
echo "4) Custom"
read -p "Select mode (1-4) [2]: " MODE_CHOICE
MODE_CHOICE=${MODE_CHOICE:-2}

case $MODE_CHOICE in
    1) MODE="maximum" ;;
    2) MODE="balanced" ;;
    3) MODE="fast" ;;
    4) MODE="custom" ;;
    *) MODE="balanced" ;;
esac

# ====================== LEGACY MODE ======================
echo -e "\n\033[1;33m=== Step 3: Ranking Mode ===\033[0m"
read -p "Use legacy (exhaustive) ranker mode? (y/n) [n]: " LEGACY_CHOICE
LEGACY_CHOICE=${LEGACY_CHOICE,,}

# ====================== DEFAULT PARAMETERS ======================
DEPTH=6
GEN_GENERATIONS=300
GENETIC_POP=600
BLOOM_MB=800
STAGE0_PROCESSES=0
TOKEN_STRIP_MAX_PREFIX=6
TOKEN_STRIP_MAX_SUFFIX=6
TOKEN_STRIP_CHUNK_SIZE=0

# Target Hours per mode
case $MODE in
    maximum) TARGET_HOURS=2.0 ;;
    balanced) TARGET_HOURS=1.0 ;;
    fast) TARGET_HOURS=0.5 ;;
    *) TARGET_HOURS=1.5 ;;
esac

# Ranker defaults
case $MODE in
    maximum)
        RANKER_K=50000
        RANKER_MAB_SCREENING=5
        RANKER_MAB_FINAL=10
        RANKER_PRESET="high_memory" ;;
    balanced)
        RANKER_K=25000
        RANKER_MAB_SCREENING=4
        RANKER_MAB_FINAL=8
        RANKER_PRESET="medium_memory" ;;
    fast)
        RANKER_K=12000
        RANKER_MAB_SCREENING=3
        RANKER_MAB_FINAL=5
        RANKER_PRESET="low_memory" ;;
    *)
        RANKER_K=25000
        RANKER_MAB_SCREENING=4
        RANKER_MAB_FINAL=8
        RANKER_PRESET="medium_memory" ;;
esac

# ====================== ADVANCED CONFIGURATION ======================
echo -e "\n\033[1;33m=== Advanced Configuration ===\033[0m"
read -p "Customize parameters (depth, strip, etc.)? (y/n) [y]: " CUSTOMIZE
CUSTOMIZE=${CUSTOMIZE:-y}

if [[ "$CUSTOMIZE" =~ ^[Yy]$ ]]; then
    echo -e "\n\033[1;36m--- Rulest Core Settings ---\033[0m"
    read -p "Max Depth ($DEPTH): " tmp; [ -n "$tmp" ] && DEPTH=$tmp
    read -p "Genetic Generations ($GEN_GENERATIONS): " tmp; [ -n "$tmp" ] && GEN_GENERATIONS=$tmp
    read -p "Genetic Population ($GENETIC_POP): " tmp; [ -n "$tmp" ] && GENETIC_POP=$tmp
    read -p "Target Hours ($TARGET_HOURS): " tmp; [ -n "$tmp" ] && TARGET_HOURS=$tmp

    echo -e "\n\033[1;36m--- Token Strip Settings ---\033[0m"
    read -p "Max Prefix Length ($TOKEN_STRIP_MAX_PREFIX): " tmp; [ -n "$tmp" ] && TOKEN_STRIP_MAX_PREFIX=$tmp
    read -p "Max Suffix Length ($TOKEN_STRIP_MAX_SUFFIX): " tmp; [ -n "$tmp" ] && TOKEN_STRIP_MAX_SUFFIX=$tmp
    read -p "Chunk Size (0=auto) ($TOKEN_STRIP_CHUNK_SIZE): " tmp; [ -n "$tmp" ] && TOKEN_STRIP_CHUNK_SIZE=$tmp

    echo -e "\n\033[1;36m--- Other Settings ---\033[0m"
    read -p "Bloom Filter (MB) ($BLOOM_MB): " tmp; [ -n "$tmp" ] && BLOOM_MB=$tmp
    read -p "Stage 0 Processes (0=auto) ($STAGE0_PROCESSES): " tmp; [ -n "$tmp" ] && STAGE0_PROCESSES=$tmp

    # Ranker settings
    echo -e "\n\033[1;36m--- Ranker Settings ---\033[0m"
    read -p "Final top rules to keep ($RANKER_K): " tmp; [ -n "$tmp" ] && RANKER_K=$tmp
    if [[ "$LEGACY_CHOICE" != "y" ]]; then
        read -p "MAB Screening Trials ($RANKER_MAB_SCREENING): " tmp; [ -n "$tmp" ] && RANKER_MAB_SCREENING=$tmp
        read -p "MAB Final Trials ($RANKER_MAB_FINAL): " tmp; [ -n "$tmp" ] && RANKER_MAB_FINAL=$tmp
    fi
fi

# ====================== EXECUTION ======================
echo -e "\n\033[1;32mStarting $MODE mode → Target: ${TARGET_HOURS}h | Depth: $DEPTH | Prefix/Suffix: $TOKEN_STRIP_MAX_PREFIX/$TOKEN_STRIP_MAX_SUFFIX | Chunk: ${TOKEN_STRIP_CHUNK_SIZE:-auto}\033[0m"

# 1. Rulest
echo -e "\n\033[1;34m[1/3] Running Rulest...\033[0m"
python rulest_v2.py "$BASE_WORDLIST" "$TARGET_WORDLIST" \
    -o stage1_raw.rule \
    --max-depth $DEPTH \
    --token-strip \
    --genetic \
    --genetic-generations $GEN_GENERATIONS \
    --genetic-pop $GENETIC_POP \
    --target-hours $TARGET_HOURS \
    --bloom-mb $BLOOM_MB \
    --token-strip-max-prefix $TOKEN_STRIP_MAX_PREFIX \
    --token-strip-max-suffix $TOKEN_STRIP_MAX_SUFFIX \
    --token-strip-chunk-size $TOKEN_STRIP_CHUNK_SIZE \
    --token-strip-workers $STAGE0_PROCESSES

# 2. Concentrator
echo -e "\n\033[1;34m[2/3] Running Concentrator...\033[0m"
python concentrator.py -p stage1_raw.rule --output_base_name stage2_cleaned --output-format line

CLEANED_RULE=$(ls stage2_cleaned*.rule 2>/dev/null | head -n 1)
[ -z "$CLEANED_RULE" ] && { echo -e "\033[1;31mError: Concentrator output not found!\033[0m"; exit 1; }

# 3. Ranker
echo -e "\n\033[1;34m[3/3] Running Ranker...\033[0m"
RANKER_CMD="python ranker.py -w \"$BASE_WORDLIST\" -r \"$CLEANED_RULE\" -c \"$CRACKED_LIST\" -o stage3_ranking.csv -k $RANKER_K --preset $RANKER_PRESET"

if [[ "$LEGACY_CHOICE" == "y" ]]; then
    RANKER_CMD="$RANKER_CMD --legacy"
else
    RANKER_CMD="$RANKER_CMD --mab-screening-trials $RANKER_MAB_SCREENING --mab-final-trials $RANKER_MAB_FINAL"
fi

eval $RANKER_CMD

echo -e "\n\033[1;32mPipeline finished successfully!\033[0m"
echo -e "\033[1;32mResults → stage3_ranking.csv\033[0m"
