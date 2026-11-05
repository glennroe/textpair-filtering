#!/usr/bin/env python3
"""
filter_source_freq.py
Step 1 — Gallica corpus:
  Count source_filename frequencies; remove alignments where
  source_filename appears > MAX_FREQ times.
  Saves the excluded filename list for use in filter_target_freq.py.

Usage:
    python3 filter_source_freq.py
"""

import json
from collections import Counter

INPUT    = "/path/to/alignements/gallica/output/alignments_clean4.jsonl"
OUTPUT   = "/path/to/alignements/gallica/output/alignments_clean5.jsonl"
EXCL_OUT = "/path/to/alignements/excluded_filenames.json"
MAX_FREQ = 234

# ── Pass 1: count ─────────────────────────────────────────────────────────────
print("Pass 1: counting source_filename frequencies...", flush=True)
freq = Counter()
total = 0
with open(INPUT, "rb") as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        freq[rec.get("source_filename", "")] += 1
        total += 1

excluded = {fn for fn, cnt in freq.items() if cnt > MAX_FREQ}
print(f"  {len(freq):,} unique source filenames across {total:,} records.")
print(f"  {len(excluded):,} filenames exceed threshold (> {MAX_FREQ} alignments) — to be removed.")

# Save exclusion list
with open(EXCL_OUT, "w") as f:
    json.dump(sorted(excluded), f, ensure_ascii=False, indent=2)
print(f"  Exclusion list saved to {EXCL_OUT}")

# ── Pass 2: filter ────────────────────────────────────────────────────────────
print("Pass 2: filtering...", flush=True)
kept = removed = 0
with open(INPUT, "rb") as fh, open(OUTPUT, "wb") as fout:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("source_filename", "") in excluded:
            removed += 1
        else:
            fout.write(line + b"\n")
            kept += 1

print(f"\nDone.")
print(f"  Input:   {kept + removed:,} records")
print(f"  Kept:    {kept:,}")
print(f"  Removed: {removed:,}  (source_filename frequency > {MAX_FREQ})")
print(f"  Output:  {OUTPUT}")
