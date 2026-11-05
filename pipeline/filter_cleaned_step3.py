#!/usr/bin/env python3
"""
filter_cleaned_step3.py
Step 3 — theatrical act/scene marker filter.
Rejects any alignment where source OR target passage contains
act/scene markers (e.g. "ACTE II", "SCÈNE III", "Fin du premier Acte").
"""

import json, re, random

BASE            = "/path/to/alignements/modern_gallica/cleaned/output/results"
INPUT           = f"{BASE}/alignments_clean2.jsonl"
OUTPUT          = f"{BASE}/alignments_clean3.jsonl"
REJECTED_SAMPLE = f"{BASE}/alignments_clean3_rejected_sample.jsonl"
SAMPLE_SIZE     = 100

THEATRE_RE = re.compile(
    r'\b('
    r'fin\s+du\s+\w+\s+acte'
    r'|acte\s+([ivxlcdm]+|\d+|premier|second|\w+i[eè]me)'
    r'|sc[eè]ne\s+([ivxlcdm]+|\d+|premi[eè]re?|derni[eè]re?|\w+i[eè]me)'
    r')',
    re.IGNORECASE
)

kept = removed = 0
reservoir = []
with open(INPUT, "rb") as fin, open(OUTPUT, "wb") as fout:
    for n, line in enumerate(fin, 1):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        sp = rec.get("source_passage") or ""
        tp = rec.get("target_passage") or ""
        if THEATRE_RE.search(sp) or THEATRE_RE.search(tp):
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
print(f"  Removed: {removed:,}  (theatrical markers)")
print(f"  Rejected sample → {REJECTED_SAMPLE}")
print(f"  Output:  {OUTPUT}")
