#!/usr/bin/env python3
"""patch_excerpts.py — Backfill full_text_excerpt into existing metadata.json files."""
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, "/home/ubuntu/legal-research-system")
from ingest_to_obsidian import extract_pdf_text

vault = Path("/home/ubuntu/Obsidian/legal-research/Cases")

case_dirs = sorted([d for d in vault.iterdir() if d.is_dir()])
patched = 0
skipped = 0
errors = 0

for case in case_dirs:
    meta_path = case / "metadata.json"
    if not meta_path.exists():
        skipped += 1
        continue
    try:
        meta = json.loads(meta_path.read_text())
    except Exception:
        skipped += 1
        continue

    # Only patch if excerpt missing or empty
    if meta.get("full_text_excerpt"):
        skipped += 1
        continue

    source_pdf = meta.get("source_pdf", "")
    if not source_pdf or not Path(source_pdf).exists():
        # Try reconstructed path
        guess = f"/home/ubuntu/myJud/sci/2013/{case.name}.pdf"
        if Path(guess).exists():
            source_pdf = guess

    if not source_pdf or not Path(source_pdf).exists():
        errors += 1
        continue

    try:
        text = extract_pdf_text(Path(source_pdf))
        meta["full_text_excerpt"] = (text or "")[:5000]
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
        patched += 1
    except Exception:
        errors += 1

    if patched % 200 == 0:
        print(f"  patched {patched}...", flush=True)

print(f"\n=== Excerpt patch complete ===")
print(f"Patched: {patched}")
print(f"Skipped: {skipped}")
print(f"Errors:  {errors}")
