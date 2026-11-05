#!/usr/bin/env python3
"""
agent/trace_pair_through_filter.py -- READ-ONLY. Every alignment the original run made between two documents, and
where each one was lost: at which filter stage, or into which set-aside table, or still live.

Dario, via Glenn, 6 Oct 2026: modern_all_align made 13 alignments between La Motte's L'Iliade (Tome 1) and Limojon
de Saint-Didier's Le Voyage du Parnasse; 6 are live; the 7 others are good and were lost to the post-alignment
filtering (the 'small passage' filter, Glenn thinks).

Reads, in order: the RAW run (alignments.jsonl.lz4), then alignments_clean1..6.jsonl (run_filter_pipeline.py:
1 phrase/position/short/OCR, 2 group banality, 3 theatre markers, 4 excluded filenames, 5 title-echo/citation,
6 content density = fragments/name lists/dates). A record matches when one side matches --a and the other --b
(case-insensitive substrings of author + title + filename). Each raw record is keyed on the natural key
(source_filename, source_start_byte, target_filename, target_start_byte) and followed: LAST STAGE it appears in,
then whether that key is in combined_align or a set-aside table today. For records that died at step 6 it also
re-runs TODAY's is_low_content / is_date_time_reference on both passages, because the fragment test was changed
(OR -> AND) after some runs were filtered: a record the current code would keep was lost to a superseded rule.

Usage (from cleaned/):
  nohup python3 agent/trace_pair_through_filter.py --a "iliade" --a2 "motte" --b "voyage du parnasse" \
      > agent/trace_iliade_parnasse.out 2>&1 &
"""
import argparse, configparser, json, os, subprocess, sys
import psycopg2
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import corpus_source as CS
import run_filter_pipeline as RF

ap = argparse.ArgumentParser()
ap.add_argument("--run", default="/path/to/alignements/modern_all_align/output/results")
ap.add_argument("--raw", default="alignments.jsonl.lz4")
ap.add_argument("--a", required=True, help="substring for document A (author/title/filename)")
ap.add_argument("--a2", default="", help="a second substring A must ALSO match (e.g. the author)")
ap.add_argument("--b", required=True)
ap.add_argument("--b2", default="")
ap.add_argument("--chars", type=int, default=300)
ap.add_argument("--text", default="", help="only records whose source OR target passage contains this (case-insensitive), e.g. neptune")
ap.add_argument("--keys-out", default="", help="write the natural keys of records in NO table (lost to the pipeline) as a TSV for restore_blocked_alignments.py --keys")
a = ap.parse_args()

cfg = configparser.ConfigParser(); cfg.read("/etc/text-pair/global_settings.ini"); D = cfg["DATABASE"]
cn = psycopg2.connect(user=D["database_user"], password=D["database_password"], database=D["database_name"])
cur = cn.cursor()
tabs = []
for t in ["combined_align"] + CS.KNOWN_SETASIDE:
    cur.execute("SELECT to_regclass(%s)", (t,))
    if cur.fetchone()[0]: tabs.append(t)

# Resolve each document to its FILENAMES through the corpus's own metadata: the raw run's records may carry other
# title/author strings (or none), but the filename is the half of the natural key that never changes.
def resolve(x, x2):
    found = {}
    for t in tabs:
        for s in ("source", "target"):
            cur.execute(f"""SELECT DISTINCT {s}_filename, {s}_author, {s}_title FROM {t}
                             WHERE lower(coalesce({s}_author,'') || ' ' || coalesce({s}_title,'') || ' ' || {s}_filename) LIKE %s
                               AND lower(coalesce({s}_author,'') || ' ' || coalesce({s}_title,'') || ' ' || {s}_filename) LIKE %s""",
                        (f"%{x.lower()}%", f"%{x2.lower()}%"))
            for f, au, ti in cur.fetchall(): found[f] = (au, ti)
    return found
A, B = resolve(a.a, a.a2), resolve(a.b, a.b2)
for lab, d in (("A", A), ("B", B)):
    print(f"  document {lab}: {len(d)} file(s)")
    for f, (au, ti) in sorted(d.items()): print(f"     {f}  | {au} | {str(ti)[:70]}")
if not A or not B: sys.exit("a document did not resolve -- adjust --a/--b")
bA = {os.path.basename(f) for f in A}; bB = {os.path.basename(f) for f in B}
def match(rec):
    s, t = os.path.basename(str(rec.get("source_filename") or "")), os.path.basename(str(rec.get("target_filename") or ""))
    if not ((s in bA and t in bB) or (s in bB and t in bA)): return False
    if a.text:
        blob = ((rec.get("source_passage") or "") + " " + (rec.get("target_passage") or "")).lower()
        return a.text.lower() in blob
    return True
def key(rec):
    return (rec.get("source_filename"), int(rec.get("source_start_byte") or -1),
            rec.get("target_filename"), int(rec.get("target_start_byte") or -1))
def scan(path):
    if not os.path.exists(path): return None
    cat = ["lz4", "-dc", path] if path.endswith(".lz4") else ["cat", path]
    p1 = subprocess.Popen(cat, stdout=subprocess.PIPE)
    args = ["grep", "-F"]
    for b in sorted(bB): args += ["-e", b]
    p2 = subprocess.Popen(args, stdin=p1.stdout, stdout=subprocess.PIPE)
    out = {}
    for line in p2.stdout:
        try: rec = json.loads(line)
        except Exception: continue
        if match(rec): out[key(rec)] = rec
    p2.wait(); p1.wait()
    return out

stages = [("raw", os.path.join(a.run, a.raw))] + [(f"clean{i}", os.path.join(a.run, f"alignments_clean{i}.jsonl")) for i in range(1, 7)]
seen = {}
for name, path in stages:
    r = scan(path)
    print(f"  {name:<7} {path}: " + ("MISSING" if r is None else f"{len(r)} matching record(s)"), flush=True)
    seen[name] = r
raw = seen["raw"] or {}
if not raw: sys.exit("no matching record in the raw run -- check --a/--b against the titles")

def where(k):
    hits = []
    for t in tabs:
        # by BASENAME: the raw run may record another path prefix than the corpus tables
        cur.execute(f"""SELECT rowid, group_id FROM {t} WHERE source_filename LIKE %s AND source_start_byte = %s
                          AND target_filename LIKE %s AND target_start_byte = %s""",
                    ("%/" + os.path.basename(k[0] or ""), k[1], "%/" + os.path.basename(k[2] or ""), k[3]))
        for rid, g in cur.fetchall(): hits.append(f"{t.replace('combined_align_', '') if t != 'combined_align' else 'LIVE'} rowid {rid} group {g}")
    return hits or ["in NO table"]

STEP = {"raw": "step 1 (phrase / position / short / OCR)", "clean1": "step 2 (group banality, >=30)",
        "clean2": "step 3 (theatre markers)", "clean3": "step 4 (excluded filenames)",
        "clean4": "step 5 (title echo / citation clutter)", "clean5": "step 6 (content density: fragment / date)",
        "clean6": "survived the pipeline"}
names = [n for n, _ in stages]
print(f"\n{len(raw)} record(s) in the raw run\n")
for k, rec in sorted(raw.items(), key=lambda x: (x[0][0], x[0][1])):
    last = "raw"
    for n in names[1:]:
        if seen.get(n) is not None and k in seen[n]: last = n
    sp, tp = rec.get("source_passage") or "", rec.get("target_passage") or ""
    print(f"=== {rec.get('source_title','')[:40]} ({rec.get('source_year')}) -> {rec.get('target_title','')[:40]} ({rec.get('target_year')})")
    print(f"    bytes {k[1]} / {k[3]}   words {RF.word_count(sp)} / {RF.word_count(tp)}")
    print(f"    fate: {STEP[last]}" + ("" if last == "clean6" else f"  [lost after {last}]"))
    c1 = (seen.get("clean1") or {}).get(k)
    if c1 is not None:
        print(f"    run-group in clean1: {c1.get('group_id')}  (grep it in agent/step2_triage.tsv for its tier)")
    if last == "clean5":
        print(f"    today's step-6 code: low_content {RF.is_low_content(sp)}/{RF.is_low_content(tp)}  "
              f"date {RF.is_date_time_reference(sp)}/{RF.is_date_time_reference(tp)}")
    print(f"    now: {'; '.join(where(k))}")
    print(f"    S: {' '.join(sp.split())[:a.chars]}")
    print(f"    T: {' '.join(tp.split())[:a.chars]}\n")
if a.keys_out:
    with open(a.keys_out, "w", encoding="utf-8") as fh:
        n = 0
        for k, rec in sorted(raw.items(), key=lambda x: (x[0][0], x[0][1])):
            if where(k) == ["in NO table"]:
                fh.write(f"{os.path.basename(k[0])}\t{k[1]}\t{os.path.basename(k[2])}\t{k[3]}\n"); n += 1
    print(f"{n} lost record key(s) -> {a.keys_out}")
print("Read-only on the database.")
