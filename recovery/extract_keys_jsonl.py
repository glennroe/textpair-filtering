#!/usr/bin/env python3
"""
agent/extract_keys_jsonl.py  (READ-ONLY on the database; writes one jsonl)
Pull the records named by a keys TSV (plan_step2_waves.py output: source file,
source byte, target file, target byte) out of a run's jsonl, so they can be put
through agent/filter_new_alignments.py -- the per-row gates every live row met
(degeneracy, boilerplate, noise classifier with Latin spared) -- BEFORE ingest.
Written 10 Oct 2026: the step-2 waves were selected on a group-level SAMPLE of
the classifier (about a dozen records per run-group), never row by row.

    python3 agent/extract_keys_jsonl.py --raw <clean1.jsonl> --keys agent/step2_wave2_keys.tsv \\
        --out agent/step2_wave2/alignments_clean6.jsonl
"""
import argparse, json, os, sys
ap = argparse.ArgumentParser()
ap.add_argument("--raw", required=True); ap.add_argument("--keys", required=True); ap.add_argument("--out", required=True)
a = ap.parse_args()
K = set()
for line in open(a.keys, encoding="utf-8"):
    p = line.rstrip("\n").split("\t")
    if len(p) >= 4 and p[1].strip().lstrip("-").isdigit():
        K.add((os.path.basename(p[0]), int(p[1]), os.path.basename(p[2]), int(p[3])))
if not K: sys.exit(f"{a.keys}: no keys read")
os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
n = w = 0; seen = set()
with open(a.raw, "rb") as fh, open(a.out, "wb") as fo:
    for raw in fh:
        n += 1
        try: r = json.loads(raw)
        except Exception: continue
        try: k = (os.path.basename(str(r.get("source_filename") or "")), int(r.get("source_start_byte")),
                  os.path.basename(str(r.get("target_filename") or "")), int(r.get("target_start_byte")))
        except (TypeError, ValueError): continue
        if k in K and k not in seen:
            seen.add(k); fo.write(raw.rstrip(b"\n") + b"\n"); w += 1
print(f"  {n:,} records read; keys {len(K):,}; written {w:,}; keys not found {len(K - seen):,} -> {a.out}")
if w != len(K): print("  ** keys and records do not reconcile -- read the counts before going on")
