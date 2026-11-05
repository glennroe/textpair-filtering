#!/usr/bin/env python3
"""
filter_banality.py
Remove high-frequency group alignments (boilerplate / formulaic text).
Criterion: group_id appears >= 20 times in the clean corpus.
Two-pass: count group sizes, then filter.
"""

import json
from collections import Counter

INPUT  = "/path/to/alignements/modern_gallica/output/alignments_clean.jsonl"
OUTPUT = "/path/to/alignements/modern_gallica/output/alignments_clean2.jsonl"
MAX_GROUP_SIZE = 20   # groups with >= this many members are discarded

# ── Pass 1: count group sizes ─────────────────────────────────────────────────
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
remove_groups = len(group_counts) - len(keep_groups)
print(f"  {len(group_counts):,} total groups; "
      f"{len(keep_groups):,} kept, {remove_groups:,} removed (>= {MAX_GROUP_SIZE} members)", flush=True)

# ── Pass 2: filter ────────────────────────────────────────────────────────────
print("Pass 2: writing filtered output...", flush=True)
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
        if rec.get("group_id", 0) in keep_groups:
            fout.write(line + b"\n")
            kept += 1
        else:
            removed += 1

print(f"\nDone.")
print(f"  Input:   {kept + removed:,} records")
print(f"  Kept:    {kept:,}  (group size < {MAX_GROUP_SIZE})")
print(f"  Removed: {removed:,}  (group size >= {MAX_GROUP_SIZE}, formulaic boilerplate)")
print(f"  Output:  {OUTPUT}")
