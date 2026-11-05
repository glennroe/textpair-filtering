#!/usr/bin/env python3
"""
audit_phrase_blocklist.py
Which entries of the phrase blocklist are chancery formulae, and which are
famous quotations? READ-ONLY.

WHY — 5 Sep 2026, and it is the day's largest finding
-------------------------------------------------------
`run_filter_pipeline.py` step 1 rejects an alignment when ANY blocklist entry
appears anywhere in either passage. Glenn asked whether *"il vaut mieux obéir
à Dieu qu'aux hommes"* had been filtered out. It had — six records in the raw
`modern_all_align` run, none after step 1 — and the reason is not collateral:

    filter_new_phrases_cleaned.txt:8786:vaut mieux obéir à Dieu qu'aux hommes

**THE PHRASE IS ON THE LIST.** Among the six removed: Bayle's *Commentaire
philosophique* quoted by Yvon's *Liberté de conscience resserrée* (1755), and
the *Mémoires de Condé* picked up by Voltaire twice. That is the toleration
debate citing itself, deleted as banality.

A blocklist built from FREQUENCY cannot tell a formula from a much-quoted
line, because a famous quotation is frequent precisely by being quoted. That
is [[rarity-spares-it-does-not-condemn]], derived a year later, and here it
sits in the first stage of the pipeline, shaping every count since.

WHAT THIS DOES, AND WHAT IT REFUSES TO DO
-------------------------------------------
It SORTS the list for reading. It does not judge: the chancery test below is
a vocabulary heuristic, and a heuristic that could separate a formula from a
quotation reliably is exactly the thing this project has twice proved does
not exist. So entries are put in two piles and the smaller pile is printed
for a human, in the annotate-able form of new_sources2.txt.

    CHANCERY   the entry carries administrative or legal vocabulary --
               roi, conseil, sceau, majesté, arrêt, ordonnons, présentes,
               parlement, and their kin. Almost certainly a formula.
    OTHER      everything else. THIS IS THE PILE TO READ. It is where a
               scriptural tag, a line of verse or a maxim will be.

With --count-against it also reports, per entry, how many raw alignments that
entry alone would reject -- attributing each record to the FIRST match, which
is what the pipeline does, so the numbers reproduce its behaviour rather than
describing an idealised one. That is the number the pipeline never logged and
the only way to size the damage per entry.

Usage:
    python3 audit_phrase_blocklist.py
    python3 audit_phrase_blocklist.py --show 200 --out blocklist_to_read.txt
    python3 audit_phrase_blocklist.py --count-against alignments.jsonl.lz4
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter

ap = argparse.ArgumentParser()
ap.add_argument("--phrases",
                default="/path/to/alignements/modern_gallica/filter_new_phrases_cleaned.txt")
ap.add_argument("--count-against", default="",
                help="a raw alignments file (.jsonl or .jsonl.lz4). Reports "
                     "rejections per entry. One full scan.")
ap.add_argument("--show", type=int, default=120)
ap.add_argument("--max-words", type=int, default=0,
                help="only entries of at most this many words. A SHORT entry "
                     "is the dangerous kind: it matches inside a long "
                     "genuine quotation. 0 = no limit.")
ap.add_argument("--out", default="")
args = ap.parse_args()

# Administrative and legal vocabulary. Deliberately generous: a false
# CHANCERY costs a missed reading, a false OTHER costs only reading time,
# and the second error is the cheaper one to make.
CHANCERY = re.compile(
    r"\b(roi|roy|majest|conseil|sceau|scell|arr[êe]t|ordonn|pr[ée]sentes|"
    r"parlement|huissier|sergent|greffi|proc[uv]reur|intendant|commissaire|"
    r"lettres patentes|[ée]dit|d[ée]claration|privil[èe]ge|libraire|imprim|"
    r"registre|enregistr|teneur|nonobstant|f[ée]aux|am[ée]s|salut|"
    r"versailles|fontainebleau|louis|navarre|tribunal|tribunaux|d[ée]cret|"
    r"assembl[ée]e|r[ée]publique|citoyen|municipalit|d[ée]partement|"
    r"google|university|library|digital)\b", re.IGNORECASE)

if not os.path.exists(args.phrases):
    sys.exit(f"\n  {args.phrases} not found. Pass --phrases.\n")

entries = []
for i, line in enumerate(open(args.phrases, encoding="utf-8",
                              errors="replace"), 1):
    p = line.rstrip("\n").strip()
    if p:
        entries.append((i, p))

# PRINT-SHOP AND THEATRE PARATEXT, which the chancery vocabulary misses and
# which dominates the alphabetical head of the list: approbations, achevé
# d'imprimer, performance notices, dedication closings, Wikisource headers.
# STRONG markers only. Misfiling an entry as paratext costs a missed reading,
# which is the expensive error here, so a weak marker like 'acte' is not in
# this list.
PARATEXT = re.compile(
    r"(approbation|achev[ée]\s+d.imprim|repr[ée]sent[ée]e?\s+(pour\s+)?"
    r"(la|le)\s+premi[èe]re\s+fois|registr[ée]e?\s+sur\s+le\s+livre|"
    r"votre\s+tr[èe]s\s+humble|vostre\s+tres[\s-]humble|serviteur|"
    r"wikisource|export[ée]\s+de|table\s+des\s+mati[èe]res|"
    r"chez\s+\w+.{0,40}\brue\b|au\s+th[ée][âa]tre\s+de\s+la\s+rue|"
    r"h[ôo]tel\s+de\s+bourgogne|com[ée]diens\s+fran[çc]ais)",
    re.IGNORECASE)


def bucket(p):
    if CHANCERY.search(p):
        return "chancery"
    if PARATEXT.search(p):
        return "paratext"
    return "other"


chancery = [(i, p) for i, p in entries if bucket(p) == "chancery"]
paratext = [(i, p) for i, p in entries if bucket(p) == "paratext"]
other = [(i, p) for i, p in entries if bucket(p) == "other"]
if args.max_words:
    other = [(i, p) for i, p in other if len(p.split()) <= args.max_words]

W = 78
print("=" * W)
print("THE PHRASE BLOCKLIST — WHAT IS ACTUALLY ON IT")
print("=" * W)
print(f"""
  file        {args.phrases}
  entries     {len(entries):,}
  chancery    {len(chancery):,}   administrative vocabulary
  paratext    {len(paratext):,}   approbations, achevé d'imprimer, performance
                        notices, printers' addresses, dedication closings
  OTHER       {len(other):,}   **THE PILE TO READ** — a scriptural tag, a
                        line of verse or a maxim will be in here
              {sum(1 for _, p in other if len(p.split()) <= 8):,} of them are
                        8 words or fewer, and LENGTH IS THE RISK: a long
                        entry is too specific to match anything but itself,
                        while a short one matches inside a real quotation.
                        Entry 8786 is seven words. Start with --max-words 8.

  Entry 8786 is 'vaut mieux obéir à Dieu qu'aux hommes'. It removed Bayle
  quoted by Yvon, and the Mémoires de Condé quoted by Voltaire twice.

  The chancery test is a VOCABULARY HEURISTIC and judges nothing. A test
  that could separate a formula from a much-quoted line is the thing this
  project has twice shown does not exist.
""")

lengths = Counter(len(p.split()) for _, p in other)
print(f"      {'words in entry':<20}{'OTHER entries':>16}")
for n in sorted(lengths)[:12]:
    print(f"      {n:<20}{lengths[n]:>16,}")
print("""
  A SHORT entry is the dangerous one: three words inside a long genuine
  quotation reject the whole alignment on one hit.
""")

counts = Counter()
if args.count_against:
    path = args.count_against
    try:
        import ahocorasick
    except ImportError:
        sys.exit("\n  --count-against needs the ahocorasick module, which "
                 "run_filter_pipeline.py uses.\n")
    A = ahocorasick.Automaton()
    for i, p in entries:
        A.add_word(p.lower(), (i, p))
    A.make_automaton()
    fh = (subprocess.Popen(["lz4", "-dc", path], stdout=subprocess.PIPE).stdout
          if path.endswith(".lz4") else open(path, "rb"))
    t0, n = time.time(), 0
    for raw in fh:
        try:
            rec = json.loads(raw)
        except Exception:
            continue
        n += 1
        blob = ((rec.get("source_passage") or "") + " " +
                (rec.get("target_passage") or "")).lower()
        # A.iter() yields (end_index, value) and value is the (line, phrase)
        # tuple added above — so the phrase is hit[1][1], not hit[1].
        # 5 Sep: keyed by the tuple and looked up by the string, every count
        # came out zero and the report still announced "worst first". A
        # ranking that cannot rank must not claim to.
        hit = next(A.iter(blob), None)      # FIRST match, as the pipeline does
        if hit is not None:
            counts[hit[1][1]] += 1
        if n % 200_000 == 0:
            print(f"  {n:,} records, {time.time() - t0:.0f}s",
                  file=sys.stderr, flush=True)
    print(f"\n  scanned {n:,} record(s) in {time.time() - t0:.0f}s; "
          f"{sum(counts.values()):,} would be rejected, attributed across "
          f"{len(counts):,} entr(ies).")
    if not counts:
        print("  ** NO ATTRIBUTIONS. The ranking below is NOT damage order.")

out = open(args.out, "w", encoding="utf-8") if args.out else sys.stdout


def w(s=""):
    print(s, file=out)


w("=" * W)
w("BLOCKLIST ENTRIES THAT ARE NOT CHANCERY — TO READ")
w("=" * W)
w(f"""
  {len(other):,} entr(ies). For each: is it a FORMULA, or is it something
  people quote?

      VERDICT: FORMULA        correctly blocked
      VERDICT: QUOTATION      wrongly blocked — remove it from the list
      VERDICT: ?              cannot tell

  Where a count is shown it is how many raw alignments that entry alone
  removed, attributed to the FIRST match as the pipeline attributes it.
""")
# WITHOUT --count-against THERE IS NO RANKING, and pretending otherwise sent
# Glenn to the head of the alphabet on 5 Sep. Fall back to SHORTEST FIRST,
# which is the risk ordering, and say which order is in force.
if counts:
    ranked = sorted(other, key=lambda e: (-counts.get(e[1], 0), e[0]))
    hit_n = sum(1 for _, q in other if counts.get(q))
    w(f"  ORDER: by alignments rejected, worst first. {hit_n:,} of "
      f"{len(other):,} entries were credited with any rejection at all.\n")
    w("""  FIRST-MATCH ATTRIBUTION IS FAITHFUL BUT NOT FAIR. The pipeline
  rejects on the earliest match in the passage, so an entry can be
  responsible for thousands of rejections and be credited with none because
  a chancery formula happened to appear earlier in the same text. A ZERO
  HERE IS NOT INNOCENCE. To measure one entry properly, unblock it alone
  and run restore_blocked_alignments.py, which is what gave 448 for the
  Acts 5:29 line.\n""")
else:
    ranked = sorted(other, key=lambda e: (len(e[1].split()), e[0]))
    w("  ORDER: SHORTEST FIRST — no --count-against was given, so this is "
      "risk\n  order and not damage order. Pass --count-against for the "
      "latter.\n")
# --show 0 MEANS ALL. It used to slice ranked[:0], writing an empty file and
# reporting "0 entries written" as though that were a result. A silent empty
# output is the worst kind of no-op.
shown = ranked if args.show == 0 else ranked[:args.show]
if len(shown) < len(ranked):
    w(f"  SHOWING {len(shown):,} OF {len(ranked):,} — truncated by --show. "
      f"Pass --show 0 for all.\n")
for line_no, p in shown:
    c = counts.get(p, None)
    w("-" * W)
    w(f"line {line_no}{('   rejects ' + format(c, ',')) if c else ''}")
    w(f"  {p!r}")
    w("VERDICT: ")
    w()
if len(shown) < len(ranked):
    w(f"  ... and {len(ranked) - len(shown):,} more. Pass --show 0 for all, "
      f"or narrow with --max-words.")

if args.out:
    out.close()
    print(f"  {len(shown):,} of {len(ranked):,} entr(ies) written to "
          f"{args.out}")
