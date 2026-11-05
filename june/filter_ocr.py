#!/usr/bin/env python3
"""
filter_ocr.py
Remove OCR-noise alignments from alignments_clean.jsonl.
Criterion: min(alpha_ratio(source_passage), alpha_ratio(target_passage)) < 0.75
Alpha ratio = fraction of non-space characters that are letters [a-zA-ZÀ-ÿ].
"""

import json
import re
import sys

INPUT  = "/path/to/alignements/gallica/output/alignments_clean.jsonl"
OUTPUT = "/path/to/alignements/gallica/output/alignments_clean2.jsonl"
THRESHOLD = 0.75

def alpha_ratio(text):
    non_space = text.replace(' ', '')
    if not non_space:
        return 0.0
    letters = len(re.findall(r'[a-zA-ZÀ-ÿ]', non_space))
    return letters / len(non_space)

kept = 0
removed = 0

with open(INPUT, "rb") as fin, open(OUTPUT, "wb") as fout:
    for n, line in enumerate(fin, 1):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            removed += 1
            continue

        sp = rec.get("source_passage") or ""
        tp = rec.get("target_passage") or ""

        if min(alpha_ratio(sp), alpha_ratio(tp)) >= THRESHOLD:
            fout.write(line + b"\n")
            kept += 1
        else:
            removed += 1

        if n % 100_000 == 0:
            print(f"  {n:,} processed  |  kept {kept:,}  removed {removed:,}", flush=True)

print(f"\nDone.")
print(f"  Input:   {n:,} records")
print(f"  Kept:    {kept:,}")
print(f"  Removed: {removed:,}  (OCR noise, alpha-ratio < {THRESHOLD})")
print(f"  Output:  {OUTPUT}")
