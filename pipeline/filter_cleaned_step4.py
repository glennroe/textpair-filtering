#!/usr/bin/env python3
"""
filter_cleaned_step4.py
Step 4 — target filename frequency filter.
Removes alignments whose target_filename is in the existing excluded list
(legal compilations, customary law collections, etc. — 95 filenames, threshold 234).
"""

import json, random

BASE            = "/path/to/alignements/modern_gallica/cleaned/output/results"
INPUT           = f"{BASE}/alignments_clean3.jsonl"
OUTPUT          = f"{BASE}/alignments_clean4.jsonl"
REJECTED_SAMPLE = f"{BASE}/alignments_clean4_rejected_sample.jsonl"
EXCL_IN         = "/path/to/alignements/excluded_filenames.json"
SAMPLE_SIZE     = 100

with open(EXCL_IN) as f:
    excluded = set(json.load(f))
print(f"Loaded {len(excluded):,} excluded filenames.", flush=True)

kept = removed = 0
reservoir = []
with open(INPUT, "rb") as fh, open(OUTPUT, "wb") as fout:
    for n, line in enumerate(fh, 1):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("target_filename", "") in excluded:
            removed += 1
            if len(reservoir) < SAMPLE_SIZE:
                reservoir.append(rec)
            else:
                j = random.randint(0, removed - 1)
                if j < SAMPLE_SIZE:
                    reservoir[j] = rec
        else:
            fout.write(line + b"\n")
            kept += 1
        if n % 100_000 == 0:
            print(f"  {n:,} processed | kept {kept:,} removed {removed:,}", flush=True)

with open(REJECTED_SAMPLE, "w", encoding="utf-8") as fs:
    for rec in reservoir:
        fs.write(json.dumps(rec, ensure_ascii=False) + "\n")

print(f"\nDone.")
print(f"  Input:   {kept+removed:,} records")
print(f"  Kept:    {kept:,}")
print(f"  Removed: {removed:,}  (target_filename in excluded list)")
print(f"  Rejected sample → {REJECTED_SAMPLE}")
print(f"  Output:  {OUTPUT}")
