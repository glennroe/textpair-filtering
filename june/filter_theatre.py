#!/usr/bin/env python3
"""
filter_theatre.py
Remove theatrical structural markers from aligned passages.
Rejects any alignment where source OR target passage contains
act/scene markers (e.g. "ACTE II", "SCÈNE III", "Fin du premier Acte").

Usage:
    python3 filter_theatre.py <input.jsonl> <output.jsonl>
"""

import json
import re
import sys

if len(sys.argv) != 3:
    print("Usage: filter_theatre.py <input.jsonl> <output.jsonl>")
    sys.exit(1)

INPUT  = sys.argv[1]
OUTPUT = sys.argv[2]

THEATRE_RE = re.compile(
    r'\b('
    r'fin\s+du\s+\w+\s+acte'                                          # Fin du premier Acte
    r'|acte\s+([ivxlcdm]+|\d+|premier|second|\w+i[eè]me)'            # ACTE II / ACTE PREMIER
    r'|sc[eè]ne\s+([ivxlcdm]+|\d+|premi[eè]re?|derni[eè]re?|\w+i[eè]me)'  # SCÈNE I / Scène première
    r')',
    re.IGNORECASE
)

kept = removed = 0

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
        else:
            fout.write(line + b"\n")
            kept += 1

        if n % 100_000 == 0:
            print(f"  {n:,} processed | kept {kept:,} removed {removed:,}", flush=True)

print(f"\nDone.")
print(f"  Input:   {kept + removed:,} records")
print(f"  Kept:    {kept:,}")
print(f"  Removed: {removed:,}  (theatrical act/scene markers)")
print(f"  Output:  {OUTPUT}")
