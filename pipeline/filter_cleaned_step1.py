#!/usr/bin/env python3
"""
filter_cleaned_step1.py
Step 1 — cleaned modern × Gallica corpus (477,501 alignments).
Filters: phrase blocklist, position paratext, passage too short, OCR noise.
Same-author intentionally skipped (Voltaire et al. self-plagiarise legitimately).
"""

import lz4.frame, json, re, ahocorasick, os, time

BASE         = "/path/to/alignements/modern_gallica/cleaned/output/results"
INPUT_FILE   = os.path.join(BASE, "alignments.jsonl.lz4")
OUTPUT_FILE  = os.path.join(BASE, "alignments_clean1.jsonl")
REPORT_FILE  = os.path.join(BASE, "filter_report_step1.txt")
PHRASE_FILE  = "/path/to/alignements/modern_gallica/filter_new_phrases.txt"

POS_HIGH     = 90.0
POS_LOW      = 10.0
MIN_WORDS    = 5
ALPHA_THRESH = 0.75

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
    non_space = text.replace(" ", "")
    if not non_space:
        return 0.0
    return len(re.findall(r"[a-zA-ZÀ-ÿ]", non_space)) / len(non_space)

print("Building phrase automaton...", flush=True)
A = build_automaton(PHRASE_FILE)

REJECTED_SAMPLE = os.path.join(BASE, "alignments_clean1_rejected_sample.jsonl")
SAMPLE_SIZE = 100   # reservoir sample of rejected records

counts = {"total": 0, "kept": 0, "phrase": 0, "position": 0, "short": 0, "ocr": 0}
rejected_reservoir = []   # reservoir sample of rejected records
rejected_count = 0
t0 = time.time()
print("Processing alignments...", flush=True)

with lz4.frame.open(INPUT_FILE, "rb") as fin, open(OUTPUT_FILE, "wb") as fout:
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
            print(f"  {counts['total']:,} processed | kept {counts['kept']:,} "
                  f"| {time.time()-t0:.0f}s", flush=True)

        sp = rec.get("source_passage") or ""
        tp = rec.get("target_passage") or ""
        reject = None

        # 1. Phrase blocklist
        if next(A.iter((sp + " " + tp).lower()), None) is not None:
            reject = "phrase"; counts["phrase"] += 1

        # 2. Position paratext (exempt long passages — genuine quotations can appear anywhere)
        if not reject:
            se = safe_float(rec.get("source_end_position"))
            te = safe_float(rec.get("target_end_position"))
            ss = safe_float(rec.get("source_start_position"))
            ts = safe_float(rec.get("target_start_position"))
            if (se > POS_HIGH and te > POS_HIGH) or (ss < POS_LOW and ts < POS_LOW):
                if len(sp.split()) < 100 and len(tp.split()) < 100:
                    reject = "position"; counts["position"] += 1

        # 3. Too short
        if not reject and len(sp.split()) < MIN_WORDS:
            reject = "short"; counts["short"] += 1

        # 4. Same author — skipped (legitimate self-reuse in this corpus)

        # 5. OCR noise
        if not reject and min(alpha_ratio(sp), alpha_ratio(tp)) < ALPHA_THRESH:
            reject = "ocr"; counts["ocr"] += 1

        if not reject:
            fout.write(raw + b"\n")
            counts["kept"] += 1
        else:
            # Reservoir sample of rejected records (tagged with reject reason)
            rec["_reject_reason"] = reject
            rejected_count += 1
            if len(rejected_reservoir) < SAMPLE_SIZE:
                rejected_reservoir.append(rec)
            else:
                import random
                j = random.randint(0, rejected_count - 1)
                if j < SAMPLE_SIZE:
                    rejected_reservoir[j] = rec

# Write rejected sample
with open(REJECTED_SAMPLE, "w", encoding="utf-8") as fs:
    for rec in rejected_reservoir:
        fs.write(json.dumps(rec, ensure_ascii=False) + "\n")
print(f"Rejected sample ({len(rejected_reservoir)} records) → {REJECTED_SAMPLE}", flush=True)

elapsed = time.time() - t0
total = counts["total"]
pct = lambda n: f"{n/total*100:.1f}%" if total else "—"

lines = [
    "Step 1 filter — cleaned modern × Gallica",
    "=" * 52,
    f"Input:   {INPUT_FILE}",
    f"Output:  {OUTPUT_FILE}",
    "",
    f"Total:             {total:>10,}",
    f"Kept:              {counts['kept']:>10,}  ({pct(counts['kept'])})",
    "",
    "Rejected:",
    f"  Phrase blocklist:  {counts['phrase']:>10,}  ({pct(counts['phrase'])})",
    f"  Position paratext: {counts['position']:>10,}  ({pct(counts['position'])})",
    f"  Passage too short: {counts['short']:>10,}  ({pct(counts['short'])})",
    f"  OCR noise:         {counts['ocr']:>10,}  ({pct(counts['ocr'])})",
    f"  Total removed:     {total-counts['kept']:>10,}  ({pct(total-counts['kept'])})",
    "",
    f"Runtime: {elapsed:.1f}s",
]
report = "\n".join(lines)
print("\n" + report, flush=True)
with open(REPORT_FILE, "w", encoding="utf-8") as fh:
    fh.write(report + "\n")
