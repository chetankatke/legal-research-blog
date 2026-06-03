#!/bin/bash
# batch_ingest_2013_sci.sh — Batch ingest 2013 SCI PDFs into Obsidian vault.
# Strategy: skip LLM summarization for bulk ingestion; run LLM only later for curated/selected cases.

set -euo pipefail

cd /home/ubuntu/legal-research-system
SCRIPT=/home/ubuntu/legal-research-system/ingest_to_obsidian.py
VAULT=/home/ubuntu/Obsidian/legal-research
PDFDIR=/home/ubuntu/myJud/sci/2013
LANG=en

echo "=== Batch ingestion: 2013 SCI PDFs ==="
echo "PDF DIR: $PDFDIR"
echo "Vault:   $VAULT"
echo ""

# Find all PDFs sorted
PDFS=$(find "$PDFDIR" -type f -name '*.pdf' | sort)

COUNT=0
ERRORS=0
SKIPPED=0

for pdf in $PDFS; do
    COUNT=$((COUNT + 1))
    # Run without LLM to keep it fast
    MINIMAX_OFFLINE=1 /usr/bin/python3 "$SCRIPT" "$pdf" --language "$LANG" --case-slug "$(basename "$pdf" .pdf)" >/dev/null 2>&1
    rc=$?
    if [ $rc -ne 0 ]; then
        ERRORS=$((ERRORS + 1))
        echo "[ERROR] exit $rc — $(basename "$pdf")"
    fi
    # Progress every 100
    if [ $((COUNT % 100)) -eq 0 ]; then
        echo "... processed $COUNT / $(echo "$PDFS" | wc -l)"
    fi
done

echo ""
echo "=== Batch complete ==="
echo "Processed: $COUNT"
echo "Errors:    $ERRORS"
echo "Skipped:   $SKIPPED"
