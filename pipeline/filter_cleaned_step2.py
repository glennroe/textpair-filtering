#!/usr/bin/env python3
"""
filter_cleaned_step2.py
Step 2 — group-size banality filter.
Removes alignments whose group_id appears >= 20 times (formulaic boilerplate).
"""

import json, random
from collections import Counter

BASE   = "/path/to/alignements/modern_gallica/cleaned/output/results"
INPUT           = f"{BASE}/alignments_clean1.jsonl"
OUTPUT          = f"{BASE}/alignments_clean2.jsonl"
REJECTED_SAMPLE = f"{BASE}/alignments_clean2_rejected_sample.jsonl"
MAX_GROUP_SIZE  = 30
SAMPLE_SIZE     = 100

# Pass 1: count group sizes
print("Pass 1: counting group sizes...", flush=True)
group_counts = Counter()
with open(INPUT, "rb") as fh:
    for n, line in enumerate(fh, 1):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        group_counts[rec.get("group_id", 0)] += 1
        if n % 100_000 == 0:
            print(f"  {n:,} records...", flush=True)

keep_groups = {gid for gid, cnt in group_counts.items() if cnt < MAX_GROUP_SIZE}
print(f"  {len(group_counts):,} total groups; "
      f"{len(keep_groups):,} kept, {len(group_counts)-len(keep_groups):,} removed "
      f"(>= {MAX_GROUP_SIZE} members)", flush=True)

# Pass 2: filter
print("Pass 2: writing filtered output...", flush=True)
kept = removed = 0
reservoir = []
with open(INPUT, "rb") as fh, open(OUTPUT, "wb") as fout:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("group_id", 0) in keep_groups:
            fout.write(line + b"\n")
            kept += 1
        else:
            removed += 1
            if len(reservoir) < SAMPLE_SIZE:
                reservoir.append(rec)
            else:
                j = random.randint(0, removed - 1)
                if j < SAMPLE_SIZE:
                    reservoir[j] = rec

with open(REJECTED_SAMPLE, "w", encoding="utf-8") as fs:
    for rec in reservoir:
        fs.write(json.dumps(rec, ensure_ascii=False) + "\n")

print(f"\nDone.")
print(f"  Input:   {kept+removed:,} records")
print(f"  Kept:    {kept:,}  (group size < {MAX_GROUP_SIZE})")
print(f"  Removed: {removed:,}  (formulaic boilerplate)")
print(f"  Rejected sample → {REJECTED_SAMPLE}")
print(f"  Output:  {OUTPUT}")
