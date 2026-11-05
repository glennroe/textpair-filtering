#!/usr/bin/env python3
"""
agent/probe_raw_pair.py  (READ-ONLY, 10 Oct 2026)
Did a TextPAIR run PRODUCE alignments between an author and the PHI texts,
and if so, what became of them? Reads the RAW run output (never the
database for the scan), then checks each record against the corpus.

Written because combined_align and all six set-aside tables hold NO row
between Montaigne's Essais and any PHI Horace, although both sit in
modern_all and modern_all was aligned against itself.

For every raw record with AUTHOR on one side and a modern_phi file on the
other:
  - step-1 verdict, re-applied as restore_blocked_alignments.py applies it:
    blocklist / position paratext / too short / OCR (alpha) / PASSES
  - whether its passage-pair text key is in ANY of the seven tables
Output: counts by PHI author x verdict x in-corpus, and samples.

    python3 agent/probe_raw_pair.py --author Montaigne \\
        --raw /path/to/alignements/modern_all_align/output/results/alignments.jsonl.lz4
"""
import argparse, configparser, json, os, re, subprocess, sys, time
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ap = argparse.ArgumentParser()
ap.add_argument("--author", required=True)
ap.add_argument("--raw", required=True)
ap.add_argument("--phrases", default="/path/to/alignements/modern_gallica/filter_new_phrases_cleaned.txt")
ap.add_argument("--min-words", type=int, default=5)
ap.add_argument("--alpha", type=float, default=0.75)
ap.add_argument("--file-like", default="",
                help="match this substring of the FILE basename instead of the author "
                     "(use if the raw records carry no author field)")
ap.add_argument("--show", type=int, default=15)
ap.add_argument("--no-db", action="store_true")
ap.add_argument("--stages", action="store_true",
                help="also read alignments_clean1..4.jsonl beside --raw and report the LAST "
                     "filter stage each record survived (step 2 = group banality, max 30)")
args = ap.parse_args()

try:
    import ahocorasick
    A = ahocorasick.Automaton()
    for line in open(args.phrases, encoding="utf-8", errors="replace"):
        p = line.strip()
        if p: A.add_word(p.lower(), p)
    A.make_automaton(); HAVE_A = True
except Exception as e:
    print(f"  (blocklist not loaded: {e})"); HAVE_A = False

def alpha_ratio(t):
    ns = t.replace(" ", ""); return len(re.findall(r"[a-zA-ZÀ-ÿ]", ns)) / len(ns) if ns else 0.0
def sf(v, d=50.0):
    try: return float(v)
    except (TypeError, ValueError): return d
def step1(rec, sp, tp):
    if HAVE_A:
        hit = next(A.iter((sp + " " + tp).lower()), None)
        if hit is not None: return f"blocklist"
    se, te, ss, ts = (sf(rec.get(k)) for k in ("source_end_position", "target_end_position",
                                               "source_start_position", "target_start_position"))
    if ((se > 90 and te > 90) or (ss < 10 and ts < 10)) and len(sp.split()) < 100 and len(tp.split()) < 100:
        return "position paratext"
    if len(sp.split()) < args.min_words: return "too short"
    if min(alpha_ratio(sp), alpha_ratio(tp)) < args.alpha: return "OCR (alpha)"
    return "PASSES step 1"

au = args.author.lower()
proc = subprocess.Popen(["lz4", "-dc", args.raw], stdout=subprocess.PIPE) if args.raw.endswith(".lz4") else None
fh = proc.stdout if proc else open(args.raw, "rb")
hits, n, t0, keys = [], 0, time.time(), set()
fields_seen = None
for raw in fh:
    try: rec = json.loads(raw)
    except Exception: continue
    n += 1
    if fields_seen is None: fields_seen = sorted(rec.keys())
    if n % 500_000 == 0:
        print(f"  {n:,} scanned, {len(hits):,} hit(s), {time.time()-t0:.0f}s", file=sys.stderr, flush=True)
    sa, ta = str(rec.get("source_author") or ""), str(rec.get("target_author") or "")
    sf_, tf_ = str(rec.get("source_filename") or ""), str(rec.get("target_filename") or "")
    sphi, tphi = "modern_phi" in os.path.basename(sf_), "modern_phi" in os.path.basename(tf_)
    fl = args.file_like.lower()
    a_src = (fl in os.path.basename(sf_).lower()) if fl else (au in sa.lower())
    a_tgt = (fl in os.path.basename(tf_).lower()) if fl else (au in ta.lower())
    if not ((a_src and tphi) or (a_tgt and sphi)): continue
    sp, tp = rec.get("source_passage") or "", rec.get("target_passage") or ""
    phi_au = ta if tphi else sa
    k = (" ".join(sp.split()).lower(), " ".join(tp.split()).lower())
    nk = (os.path.basename(sf_), str(rec.get("source_start_byte")), os.path.basename(tf_), str(rec.get("target_start_byte")))
    hits.append((phi_au, step1(rec, sp, tp), k, sp[:80], tp[:80], os.path.basename(sf_ if sphi else tf_), nk, rec.get("group_id")))
    keys.add(k)
print(f"  scanned {n:,} raw record(s) in {time.time()-t0:.0f}s; fields: {fields_seen}")
print(f"  records pairing {args.author!r} with a modern_phi file: {len(hits):,}")
inc = set()
if hits and not args.no_db:
    import psycopg2, corpus_source as CS
    cfg = configparser.ConfigParser(); cfg.read("/etc/text-pair/global_settings.ini"); D = cfg["DATABASE"]
    cn = psycopg2.connect(user=D["database_user"], password=D["database_password"], database=D["database_name"])
    cn.set_session(readonly=True); cur = cn.cursor(); cur.execute("SET statement_timeout = 0")
    for t in ["combined_align"] + CS.KNOWN_SETASIDE:
        cur.execute("SELECT to_regclass(%s)", (t,))
        if cur.fetchone()[0] is None: continue
        cur.execute(f"""SELECT lower(regexp_replace(source_passage,'\\s+',' ','g')),
                               lower(regexp_replace(target_passage,'\\s+',' ','g')) FROM {t}
                         WHERE source_author ILIKE %s OR target_author ILIKE %s""",
                    (f"%{args.author}%", f"%{args.author}%"))
        for s, tt in cur.fetchall():
            k = ((s or "").strip(), (tt or "").strip())
            if k in keys: inc.add((t, k))
STAGE = {}
if args.stages and hits:
    base = os.path.dirname(args.raw); want = {h[6] for h in hits}
    for i in (1, 2, 3, 4):
        f = os.path.join(base, f"alignments_clean{i}.jsonl")
        if not os.path.exists(f):
            print(f"  (no {f})"); continue
        seen = 0
        for raw in open(f, "rb"):
            try: r = json.loads(raw)
            except Exception: continue
            nk = (os.path.basename(str(r.get("source_filename") or "")), str(r.get("source_start_byte")),
                  os.path.basename(str(r.get("target_filename") or "")), str(r.get("target_start_byte")))
            if nk in want: STAGE[nk] = i; seen += 1
        print(f"  clean{i}: {seen:,} of the {len(want):,} records present")
tabof = defaultdict(set)
for t, k in inc: tabof[k].add(t)
def stage_of(h):
    if not args.stages: return ""
    st = STAGE.get(h[6], 0)
    return {0: "dropped by step 1", 1: "dropped by STEP 2 (banality)", 2: "dropped by step 3 (theatre)",
            3: "dropped by step 4 (excl. files)", 4: "survived all 4"}[st]
tab = Counter((h[0].split(" (")[0][:28], h[1], ",".join(sorted(tabof.get(h[2], {"NOT IN CORPUS"}))), stage_of(h)) for h in hits)
print(f"\n  PHI author x step-1 verdict x where it is now")
for (a, v, w, st), c in tab.most_common(80):
    print(f"    {c:>6,}  {a:<28} {v:<16} {w:<16} {st}")
print("\n  samples:")
for h in hits[:args.show]:
    print(f"    [{h[1]}] {h[0][:24]} {h[5]} | {h[3]!r} | {h[4]!r}")
