#!/bin/bash
# run_filters_cleaned.sh
# Full filter pipeline for the cleaned modern × Gallica corpus.
# Run from the server with: bash run_filters_cleaned.sh

SCRIPTS="/path/to/alignements/modern_gallica/vert/output/results"
PYTHON="python3"

echo "========================================"
echo "Step 1: phrase blocklist + OCR noise"
echo "========================================"
nohup $PYTHON $SCRIPTS/filter_cleaned_step1.py > $SCRIPTS/step1.log 2>&1 &
wait
cat $SCRIPTS/step1.log

echo ""
echo "========================================"
echo "Step 2: group-size banality filter"
echo "========================================"
$PYTHON $SCRIPTS/filter_cleaned_step2.py

echo ""
echo "========================================"
echo "Step 3: theatre marker filter"
echo "========================================"
$PYTHON $SCRIPTS/filter_cleaned_step3.py

echo ""
echo "========================================"
echo "Step 4: target filename frequency filter"
echo "========================================"
$PYTHON $SCRIPTS/filter_cleaned_step4.py

echo ""
echo "Pipeline complete. Final output:"
echo "  /path/to/alignements/modern_gallica/cleaned/output/results/alignments_clean4.jsonl"
wc -l /path/to/alignements/modern_gallica/cleaned/output/results/alignments_clean4.jsonl
