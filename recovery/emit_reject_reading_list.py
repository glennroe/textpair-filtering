#!/usr/bin/env python3
"""
emit_reject_reading_list.py
The filter's rejected samples, laid out to be READ and judged, in the form of
new_sources2.txt. READ-ONLY.

WHY THERE IS NO ALTERNATIVE TO READING — 5 Sep 2026
-----------------------------------------------------
`run_filter_pipeline.py` step 1 rejected 216,004 alignments on a phrase
blocklist and 223,142 on position, 41.5% of everything, before any other
judgement. **No label in this project can adjudicate those**: Martial
annotated rows that had already survived the filter, so the removed material
has no labels and never will. `measure_pattern_precision.py` cannot reach it
either, for the same reason. Reading the samples is the only instrument.

WHAT TO WATCH FOR, PER REASON
-------------------------------
    phrase      the blocklist matches ANY entry anywhere in either passage,
                and rejects on a single hit. This project later ruled the
                other way -- [[condemn-on-density-not-on-a-hit]], MIN_DENSITY
                6.5 -- after measuring. A short blocklist entry inside a long
                real quotation is the failure mode.
    position    both passages in the last 10% of their documents, or both in
                the FIRST 10%, under 100 words. Back matter is a fair target.
                **The first 10% is where epigraphs, dedications and
                title-page quotations live**, and an epigraph is reuse of
                precisely the kind this project exists to find.
    short       under --min-words. Low risk.
    ocr         alpha ratio below 0.75 on the weaker side.

THE SAMPLE IS A RESERVOIR, AND THAT MATTERS
---------------------------------------------
`reservoir_add` keeps 100 records uniformly at random from everything that
step rejected, so the sample IS representative of the reject population -- but
it is 100 of 449,056, so a rate read off it carries a wide interval. It is
enough to answer "is there a problem", not "how big". Say which you are
asking before quoting a number from it.

Usage:
    python3 emit_reject_reading_list.py --in alignments_clean1_rejected_sample.jsonl
    python3 emit_reject_reading_list.py --in ... --reason position --out pos.txt
"""

import argparse
import json
import os
import sys
from collections import Counter

ap = argparse.ArgumentParser()
ap.add_argument("--in", dest="src", required=True, action="append",
                help="a *_rejected_sample.jsonl. Repeatable.")
ap.add_argument("--reason", default="",
                help="only this _reject_reason (phrase, position, short, ocr).")
ap.add_argument("--chars", type=int, default=420)
ap.add_argument("--out", default="")
args = ap.parse_args()

recs = []
for path in args.src:
    if not os.path.exists(path):
        print(f"  ** {path} not found — skipped.", file=sys.stderr)
        continue
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            r["_file"] = os.path.basename(path)
            recs.append(r)

if not recs:
    sys.exit("\n  Nothing read. Check the paths.\n")

by_reason = Counter(r.get("_reject_reason", "(none recorded)") for r in recs)
if args.reason:
    recs = [r for r in recs if r.get("_reject_reason") == args.reason]

out = open(args.out, "w", encoding="utf-8") if args.out else sys.stdout
W = 78


def w(s=""):
    print(s, file=out)


w("=" * W)
w("WHAT THE FILTER THREW AWAY — TO READ")
w("=" * W)
w(f"""
  {len(recs):,} record(s) from {len(args.src)} sample file(s).

  by reject reason, before any --reason filter:""")
for k, n in by_reason.most_common():
    w(f"      {k:<20}{n:>6}")
w(f"""
  THE QUESTION FOR EACH ONE: should this have been removed?

      VERDICT: NOISE          correctly removed
      VERDICT: REUSE          wrongly removed — this is real text reuse
      VERDICT: ?              cannot tell from the passage alone

  These are a RESERVOIR sample, so they are representative of the reject
  population — but 100 of 449,056 answers "is there a problem", not "how
  big". Do not quote a rate off it.

  Positions are printed because the position rule fires on them: a pair in
  the FIRST 10% may be an epigraph, which is reuse, not paratext.
""")

for i, r in enumerate(recs, 1):
    w("-" * W)
    w(f"{i}. {r.get('_reject_reason', '?').upper()}   "
      f"group {r.get('group_id')}   [{r.get('_file')}]")
    for side in ("source", "target"):
        st = r.get(f"{side}_start_position")
        en = r.get(f"{side}_end_position")
        pos = ""
        try:
            pos = f"  [{float(st):.0f}%–{float(en):.0f}%]"
        except (TypeError, ValueError):
            pos = "  [position unknown]"
        w(f"  {side:<7}({r.get(side + '_year')}) "
          f"{str(r.get(side + '_author'))[:34]} — "
          f"{str(r.get(side + '_title'))[:40]}{pos}")
        txt = " ".join(str(r.get(f"{side}_passage", "")).split())
        w(f"          {txt[:args.chars]!r}")
    w()
    w("VERDICT: ")
    w()

if args.out:
    out.close()
    print(f"  {len(recs):,} block(s) written to {args.out}", file=sys.stderr)
