#!/usr/bin/env python3
"""
agent/chrono_swap_jsonl.py -- the corpus's chronology rule, applied to an alignment FILE.
fix_source_target_chronology(_modern).py made 'source is the older side' a fact in
combined_align: every source_*/target_* pair is swapped where source_year > target_year;
ties and rows missing a year are left as they are. New alignments (e.g. Dacier run as the
TARGET against modern_all_pruned / gallica_mono) must arrive in that orientation.

Swaps every key pair source_X <-> target_X found on the record (so passages, bytes, titles,
authors, years, filenames, philo ids... travel together); other keys are untouched.
Usage (from cleaned/):
  python3 agent/chrono_swap_jsonl.py <results_dir> [--in alignments_gated.jsonl] [--out alignments_gated_chrono.jsonl]
"""
import argparse, collections, json, os, re
ap = argparse.ArgumentParser()
ap.add_argument("results_dir"); ap.add_argument("--in", dest="inp", default="alignments_gated.jsonl")
ap.add_argument("--out", default="alignments_gated_chrono.jsonl")
a = ap.parse_args()
def year(v):
    m = re.search(r"-?\d{1,4}", str(v)) if v not in (None, "") else None
    return int(m.group(0)) if m else None
c = collections.Counter(); pairs = collections.Counter()
with open(os.path.join(a.results_dir, a.inp), encoding="utf-8") as fi, \
     open(os.path.join(a.results_dir, a.out), "w", encoding="utf-8") as fo:
    for line in fi:
        r = json.loads(line); sy, ty = year(r.get("source_year")), year(r.get("target_year"))
        if sy is None or ty is None: c["kept: a year missing"] += 1
        elif sy > ty:
            for k in [k for k in r if k.startswith("source_")]:
                t = "target_" + k[len("source_"):]
                if t in r: r[k], r[t] = r[t], r[k]
            c["SWAPPED (source was later)"] += 1
            pairs[(r.get("source_filename", "").split("/")[-1], sy, ty)] += 1
        elif sy == ty: c["kept: same year"] += 1
        else: c["kept: already oldest-first"] += 1
        fo.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"{sum(c.values()):,} rows -> {a.out}")
for k, v in c.most_common(): print(f"  {k:<30} {v:>7,}")
print("  swapped, by the document now on the source side (top 10):")
for (f, sy, ty), n in pairs.most_common(10): print(f"    {n:>5}  {f}  (was source {sy} > target {ty})")
