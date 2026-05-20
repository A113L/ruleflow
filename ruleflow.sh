#!/bin/bash
# =============================================================================
# INTERACTIVE HASHCAT RULE PIPELINE 2026
# =============================================================================
echo -e "\033[1;36m"
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║ INTERACTIVE HASHCAT RULE PIPELINE v2026                        ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo -e "\033[0m"

# ====================== INPUT FILES ======================
echo -e "\n\033[1;33m=== Step 1: Input Files ===\033[0m"
read -p "Base wordlist path: " BASE_WORDLIST
read -p "Target wordlist path: " TARGET_WORDLIST
read -p "Cracked passwords list (required for Ranker): " CRACKED_LIST
if [ ! -f "$BASE_WORDLIST" ] || [ ! -f "$TARGET_WORDLIST" ]; then
    echo -e "\033[1;31mError: Base or Target wordlist not found!\033[0m"
    exit 1
fi
if [ ! -f "$CRACKED_LIST" ]; then
    echo -e "\033[1;31mError: Cracked list not found! Ranker requires this file.\033[0m"
    exit 1
fi

# ====================== MODE SELECTION ======================
echo -e "\n\033[1;33m=== Step 2: Pipeline Mode ===\033[0m"
echo "1) Maximum Quality"
echo "2) Balanced (Recommended)"
echo "3) Fast & Light"
echo "4) Custom (Full Control)"
read -p "Select mode (1-4) [2]: " MODE_CHOICE
MODE_CHOICE=${MODE_CHOICE:-2}

case $MODE_CHOICE in
    1) MODE="maximum" ;;
    2) MODE="balanced" ;;
    3) MODE="fast" ;;
    4) MODE="custom" ;;
    *) MODE="balanced" ;;
esac

# ====================== LEGACY MODE CHOICE (ASK EARLY) ======================
echo -e "\n\033[1;33m=== Step 3: Ranking Mode ===\033[0m"
read -p "Use legacy (exhaustive) ranker mode? (y/n) [n]: " LEGACY_CHOICE
LEGACY_CHOICE=${LEGACY_CHOICE,,}

# ====================== DEFAULT PARAMETERS ======================
DEPTH=3
GEN_GENERATIONS=300
GENETIC_POP=600
TARGET_HOURS=2.0

# Rulest Advanced
BLOOM_MB=800
STAGE0_PROCESSES=0
TOKEN_STRIP_MAX_PREFIX=4
TOKEN_STRIP_MAX_SUFFIX=4

# Ranker parameters (MAB only, used only if legacy is NOT chosen)
RANKER_K=18000          # will be overridden by mode presets
RANKER_MAB_SCREENING=4
RANKER_MAB_FINAL=8
RANKER_PRESET="medium_memory"

if [ "$MODE" = "maximum" ]; then
    RANKER_K=25000
    RANKER_MAB_SCREENING=5
    RANKER_MAB_FINAL=10
    RANKER_PRESET="high_memory"
elif [ "$MODE" = "balanced" ]; then
    RANKER_K=18000
    RANKER_MAB_SCREENING=4
    RANKER_MAB_FINAL=8
    RANKER_PRESET="medium_memory"
elif [ "$MODE" = "fast" ]; then
    RANKER_K=12000
    RANKER_MAB_SCREENING=3
    RANKER_MAB_FINAL=5
    RANKER_PRESET="low_memory"
fi

# ====================== CUSTOM PARAMETER SETUP ======================
if [ "$MODE" = "custom" ] || [ "$MODE" = "maximum" ]; then
    echo -e "\n\033[1;36m=== Advanced Configuration ===\033[0m"
   
    echo -e "\033[1;33m--- Rulest Core Settings ---\033[0m"
    read -p "Rulest Max Depth [3-4] ($DEPTH): " tmp; [ -n "$tmp" ] && DEPTH=$tmp
    read -p "Genetic Generations [40-120] ($GEN_GENERATIONS): " tmp; [ -n "$tmp" ] && GEN_GENERATIONS=$tmp
    read -p "Genetic Population [100-400] ($GENETIC_POP): " tmp; [ -n "$tmp" ] && GENETIC_POP=$tmp
    read -p "Rulest Target Hours [0.5-5.0] ($TARGET_HOURS): " tmp; [ -n "$tmp" ] && TARGET_HOURS=$tmp

    echo -e "\n\033[1;33m--- Rulest Bloom & Stage 0 ---\033[0m"
    read -p "Bloom Filter Size (MB) [400-2000] ($BLOOM_MB): " tmp; [ -n "$tmp" ] && BLOOM_MB=$tmp
    read -p "Stage 0 Processes (0=auto) ($STAGE0_PROCESSES): " tmp; [ -n "$tmp" ] && STAGE0_PROCESSES=$tmp
    read -p "Token-Strip Max Prefix Length ($TOKEN_STRIP_MAX_PREFIX): " tmp; [ -n "$tmp" ] && TOKEN_STRIP_MAX_PREFIX=$tmp
    read -p "Token-Strip Max Suffix Length ($TOKEN_STRIP_MAX_SUFFIX): " tmp; [ -n "$tmp" ] && TOKEN_STRIP_MAX_SUFFIX=$tmp

    echo -e "\n\033[1;33m--- Ranker Settings ---\033[0m"
    read -p "Final top rules to keep ($RANKER_K): " tmp; [ -n "$tmp" ] && RANKER_K=$tmp
    # Only ask for MAB parameters if we are NOT in legacy mode
    if [[ "$LEGACY_CHOICE" != "y" ]]; then
        read -p "MAB Screening Trials ($RANKER_MAB_SCREENING): " tmp; [ -n "$tmp" ] && RANKER_MAB_SCREENING=$tmp
        read -p "MAB Final Trials ($RANKER_MAB_FINAL): " tmp; [ -n "$tmp" ] && RANKER_MAB_FINAL=$tmp
    fi
    read -p "Ranker Preset [$RANKER_PRESET]: " tmp; [ -n "$tmp" ] && RANKER_PRESET=$tmp
fi

# ====================== EXECUTION ======================
echo -e "\n\033[1;32mStarting $MODE Pipeline (Rulest → Concentrator → Ranker)...\033[0m"

# 1. Rulest
echo -e "\n\033[1;34m[1/3] Rulest...\033[0m"
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
    --token-strip-workers $STAGE0_PROCESSES

# 2. Concentrator
echo -e "\n\033[1;34m[2/3] Concentrator...\033[0m"
python concentrator.py -p stage1_raw.rule \
    --output_base_name stage2_cleaned \
    --output-format expanded

# Auto-detect Concentrator output
CLEANED_RULE=$(ls stage2_cleaned*.rule 2>/dev/null | head -n 1)
if [ -z "$CLEANED_RULE" ]; then
    echo -e "\033[1;31mError: Could not find Concentrator output file!\033[0m"
    exit 1
fi
echo -e "\033[1;32m→ Using: $CLEANED_RULE\033[0m"

# 3. Ranker (build command based on legacy choice)
echo -e "\n\033[1;34m[3/3] Ranker...\033[0m"

# Base command (common part)
RANKER_CMD="python ranker.py -w \"$BASE_WORDLIST\" -r \"$CLEANED_RULE\" -c \"$CRACKED_LIST\" -o stage3_ranking.csv -k $RANKER_K --preset $RANKER_PRESET"

if [[ "$LEGACY_CHOICE" == "y" ]]; then
    echo -e "\033[1;33m→ Running in LEGACY (exhaustive) mode.\033[0m"
    RANKER_CMD="$RANKER_CMD --legacy"
else
    echo -e "\033[1;33m→ Running in MAB mode (screening=$RANKER_MAB_SCREENING, final=$RANKER_MAB_FINAL).\033[0m"
    RANKER_CMD="$RANKER_CMD --mab-screening-trials $RANKER_MAB_SCREENING --mab-final-trials $RANKER_MAB_FINAL"
fi

eval $RANKER_CMD

echo -e "\n\033[1;32mPipeline completed successfully!\033[0m"
echo -e "\033[1;32mRanking results: stage3_ranking.csv\033[0m"
