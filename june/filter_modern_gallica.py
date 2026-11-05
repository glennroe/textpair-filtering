#!/usr/bin/env python3
"""
filter_modern_gallica.py
All-in-one filter for alignments_mod.jsonl.lz4 (modern × Gallica corpus).

Filters applied (in order):
  1. Phrase blocklist   — Aho-Corasick substring match on source + target passage
  2. Position paratext  — both sides >90% OR both sides <10% of document
  3. Passage too short  — source passage < 5 words
  4. Same-author        — discarded (edition variants, not intertextual reuse)
  5. OCR noise          — min(alpha_ratio(source), alpha_ratio(target)) < 0.75

Outputs:
  alignments_clean.jsonl   — passes all filters
  filter_report.txt        — summary statistics
"""

import lz4.frame
import json
import re
import ahocorasick
import sys
import os
import time

# ── Configuration ─────────────────────────────────────────────────────────────
INPUT_FILE    = "/path/to/alignements/modern_gallica/alignments_mod.jsonl.lz4"
OUTPUT_DIR    = "/path/to/alignements/modern_gallica/output"
PHRASE_FILE   = "/path/to/alignements/modern_gallica/filter_new_phrases.txt"  # already on server

POS_HIGH      = 90.0
POS_LOW       = 10.0
MIN_WORDS     = 5
ALPHA_THRESH  = 0.75
# ─────────────────────────────────────────────────────────────────────────────

os.makedirs(OUTPUT_DIR, exist_ok=True)
OUT_CLEAN   = os.path.join(OUTPUT_DIR, "alignments_clean.jsonl")
OUT_REPORT  = os.path.join(OUTPUT_DIR, "filter_report.txt")

# ── Helpers ───────────────────────────────────────────────────────────────────
def build_automaton(path):
    A = ahocorasick.Automaton()
    n = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            phrase = line.strip().lower()
            if phrase:
                A.add_word(phrase, phrase)
                n += 1
    A.make_automaton()
    print(f"  Blocklist loaded: {n:,} phrases", flush=True)
    return A

def safe_float(val, default=50.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default

def alpha_ratio(text):
    non_space = text.replace(' ', '')
    if not non_space:
        return 0.0
    return len(re.findall(r'[a-zA-ZÀ-ÿ]', non_space)) / len(non_space)

# ── Build automaton ───────────────────────────────────────────────────────────
print("Building phrase automaton...", flush=True)
A = build_automaton(PHRASE_FILE)

# ── Filter loop ───────────────────────────────────────────────────────────────
counts = {
    "total": 0, "kept": 0,
    "phrase": 0, "position": 0, "short": 0, "same_author": 0, "ocr": 0,
}

t0 = time.time()
print("Processing alignments...", flush=True)

with lz4.frame.open(INPUT_FILE, "rb") as fin, \
     open(OUT_CLEAN, "wb") as fout:

    for raw in fin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except Exception:
            continue

        counts["total"] += 1
        if counts["total"] % 100_000 == 0:
            elapsed = time.time() - t0
            print(f"  {counts['total']:,} processed | kept {counts['kept']:,} "
                  f"| {elapsed:.0f}s", flush=True)

        sp = rec.get("source_passage") or ""
        tp = rec.get("target_passage") or ""
        reject = None

        # 1. Phrase blocklist
        combined = (sp + " " + tp).lower()
        if next(A.iter(combined), None) is not None:
            reject = "phrase_blocklist"
            counts["phrase"] += 1

        # 2. Position paratext
        if not reject:
            se = safe_float(rec.get("source_end_position"))
            te = safe_float(rec.get("target_end_position"))
            ss = safe_float(rec.get("source_start_position"))
            ts = safe_float(rec.get("target_start_position"))
            if (se > POS_HIGH and te > POS_HIGH) or (ss < POS_LOW and ts < POS_LOW):
                reject = "position_paratext"
                counts["position"] += 1

        # 3. Passage too short
        if not reject and len(sp.split()) < MIN_WORDS:
            reject = "passage_too_short"
            counts["short"] += 1

        # 4. Same author — intentionally skipped for this corpus.
        # Authors like Voltaire self-plagiarise extensively; same-author
        # alignments represent genuine intertextual reuse and should be kept.

        # 5. OCR noise
        if not reject:
            if min(alpha_ratio(sp), alpha_ratio(tp)) < ALPHA_THRESH:
                reject = "ocr_noise"
                counts["ocr"] += 1

        if not reject:
            fout.write(raw + b"\n")
            counts["kept"] += 1

elapsed = time.time() - t0

# ── Report ────────────────────────────────────────────────────────────────────
total = counts["total"]
def pct(n): return f"{n/total*100:.1f}%" if total else "—"

lines = [
    "TextPAIR Alignment Filter — modern × Gallica",
    "=" * 52,
    f"Input:               {INPUT_FILE}",
    f"Phrase blocklist:    {PHRASE_FILE}",
    f"Position threshold:  <{POS_LOW}% (head) / >{POS_HIGH}% (tail), both sides",
    f"Min passage length:  {MIN_WORDS} words",
    f"OCR alpha threshold: {ALPHA_THRESH}",
    "",
    f"Total alignments:    {total:>10,}",
    f"Kept (clean):        {counts['kept']:>10,}  ({pct(counts['kept'])})",
    "",
    "Rejected:",
    f"  Phrase blocklist:  {counts['phrase']:>10,}  ({pct(counts['phrase'])})",
    f"  Position paratext: {counts['position']:>10,}  ({pct(counts['position'])})",
    f"  Passage too short: {counts['short']:>10,}  ({pct(counts['short'])})",
    f"  Same author:       {counts['same_author']:>10,}  ({pct(counts['same_author'])})",
    f"  OCR noise:         {counts['ocr']:>10,}  ({pct(counts['ocr'])})",
    f"  Total removed:     {total - counts['kept']:>10,}  ({pct(total - counts['kept'])})",
    "",
    f"Runtime: {elapsed:.1f}s",
    f"Output:  {OUT_CLEAN}",
]

report = "\n".join(lines)
print("\n" + report, flush=True)
with open(OUT_REPORT, "w", encoding="utf-8") as fh:
    fh.write(report + "\n")
print(f"\nReport saved to {OUT_REPORT}")
