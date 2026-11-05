#!/usr/bin/env python3
"""
restore_blocked_alignments.py
Put back the alignments that step 1 rejected on blocklist entries now judged
wrong. MUTATING; dry run by default; --commit required.

WHY — 5 Sep 2026
------------------
`filter_new_phrases_cleaned.txt:8786` is 'vaut mieux obéir à Dieu qu'aux
hommes'. Step 1 rejects an alignment when ANY entry matches anywhere in
either passage, so that line removed six records from the modern_all_align
run, among them Bayle's *Commentaire philosophique* quoted by Yvon (1755) and
the *Mémoires de Condé* quoted by Voltaire twice. The toleration debate
citing itself, deleted as banality.

**THIS IS AN INGEST, NOT A RESTORATION.** `restore_rows.py` moves rows back
from a set-aside table; these rows never entered the corpus and have no rowid
and no group. So the seven-table invariant CHANGES here, deliberately, and
the new baseline is printed at the end to be recorded the same day.

WHAT IT WILL NOT DO
-------------------
It will not restore a record that another step-1 rule would also have caught.
A record rejected on an unblocked phrase AND sitting in the paratext position
band, or under the word floor, or below the OCR threshold, stays out — the
full rule set is re-applied and only the phrase test is relaxed. Restoring on
one rule's reversal while ignoring the others would smuggle in material no
one judged.

It will not insert a row the corpus already holds. The live sixteen rows for
that fragment come from all runs; this file is one run. Dedup is on the
PASSAGE-PAIR TEXT KEY, the same key `martial_label_map` joins on, because
alignment_id is not our rowid -- 0 of 470 sampled rows agreed.

GROUP IDS, AND IT IS A DATA-MODEL DECISION
--------------------------------------------
Restored rows arrive without groups. They are given fresh ids from
max(group_id)+1 upward, one per (source_doc, target_doc, passage) locus, and
every assignment is written to the manifest. **They come in as NEW GROUPS on
purpose**: the blocking and merge machinery already exists to join them to
their relatives, and a wrong new group costs a merge, where a wrong
attachment corrupts a group that was already correct.

Note that ids above the modern bands decode as an unnamed band in
`probe_source_by_subcorpus.band()`. That is visible rather than wrong, and
extending BANDS is a one-line change once the range is known.

READING THE VERDICTS
--------------------
`--verdicts` takes the annotated `blocklist_to_read.txt`: any block whose
VERDICT line says QUOTATION has its entry unblocked. `--unblock-line` and
`--unblock-text` name entries directly, for a single case like 8786 before
the full reading is done.

Usage:
    python3 restore_blocked_alignments.py --unblock-line 8786 \\
        --raw /path/to/alignements/modern_all_align/output/results/alignments.jsonl.lz4
    python3 restore_blocked_alignments.py --verdicts blocklist_to_read.txt \\
        --raw ... --commit
"""

import argparse
import configparser
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict

import psycopg2
import corpus_source as CS

ap = argparse.ArgumentParser()
ap.add_argument("--raw", required=True,
                help="the RAW alignments file for one run (.jsonl or .lz4).")
ap.add_argument("--phrases",
                default="/path/to/alignements/modern_gallica/filter_new_phrases_cleaned.txt")
ap.add_argument("--verdicts", default="",
                help="an annotated blocklist_to_read.txt; entries whose "
                     "VERDICT is QUOTATION are unblocked.")
ap.add_argument("--unblock-line", action="append", type=int, default=[])
ap.add_argument("--unblock-text", action="append", default=[])
ap.add_argument("--table", default="combined_align")
ap.add_argument("--min-words", type=int, default=5)
ap.add_argument("--pos-high", type=float, default=90.0)
ap.add_argument("--pos-low", type=float, default=10.0)
ap.add_argument("--alpha", type=float, default=0.75)
ap.add_argument("--no-position", action="store_true")
ap.add_argument("--locus-key", default="phrase",
                choices=("phrase", "source-passage", "doc-pair", "run-group", "span"),
                help="how restored rows are grouped. 'phrase' (default) puts "
                     "every row matching one unblocked entry into ONE group: "
                     "they share a locus by construction, and an over-large "
                     "group is one object split_group_loci.py can refine "
                     "where 440 singletons are 440 nobody will ever merge. "
                     "'source-passage' groups by the FOLDED source passage. "
                     "'doc-pair' is the original and splits obéïr from "
                     "obéir.")
ap.add_argument("--allow-new-corpus-value", action="store_true",
                help="permit writing a `corpus` value the table has never "
                     "held. Refused by default: a new value in a column "
                     "others filter on makes a population invisible.")
ap.add_argument("--keys", default="",
                help="6 Oct 2026: restore NAMED records instead of blocklist "
                     "rejects. A TSV of natural keys -- source basename, "
                     "source_start_byte, target basename, target_start_byte "
                     "(agent/trace_pair_through_filter.py --keys-out writes "
                     "one). Records are taken whatever step rejected them, "
                     "because a human has read them; the step-1 rules are "
                     "REPORTED for each, not applied. Dedup is unchanged.")
ap.add_argument("--why", default="",
                help="with --keys: the reading that justifies the ingest, "
                     "written into the manifest. Required with --keys.")
ap.add_argument("--span-max", type=int, default=1500,
                help="--locus-key span: a row-side longer than this many bytes does not link loci")
ap.add_argument("--attach", action="store_true",
                help="--locus-key span only: join restored rows to the ONE live group sharing their span; "
                     "families meeting 2+ live groups come in new and are listed (Glenn, 10 Oct 2026)")
ap.add_argument("--attach-held", default="agent/attach_held.tsv")
ap.add_argument("--bridge-words", type=int, default=60,
                help="--attach: passages longer than this are not used by the locus test (group_loci.py's rule)")
ap.add_argument("--locus-passages", type=int, default=12,
                help="--attach: longest passages per side given to locus_test.compare()")
ap.add_argument("--span-loose", dest="span_mutual", action="store_false",
                help="revert to overlap >= half of the SHORTER span (the 10 Oct morning rule, which chained)")
ap.add_argument("--dominant-min", type=float, default=0.5,
                help="--attach: a row confirming 2+ live groups takes the one whose passages it matches at this share or more (0 = off, dry9 behaviour)")
ap.add_argument("--attach-prefer", default="agent/attach_prefer.tsv",
                help="lines 'PREFERRED OTHER [OTHER...]': where a row qualifies for both, OTHER yields (Glenn's rulings on duplicate live groups)")
ap.add_argument("--audit-share", type=float, default=0.25,
                help="--attach: list attaching rows matching under this share of their group's passages (0 = off)")
ap.add_argument("--audit-file", default="agent/attach_thin.tsv")
ap.add_argument("--no-principal-gate", dest="principal_gate", action="store_false",
                help="--attach: let thin rows attach even when they miss the group's principal locus")
ap.add_argument("--dominant-ratio", type=float, default=2.0, help="... and at least this many times the runner-up's share")
ap.add_argument("--dominant-passages", type=int, default=40, help="passages per group sampled for the share")
ap.add_argument("--no-long-propose", dest="long_propose", action="store_false",
                help="--attach: ignore row-sides longer than --span-max for proposals too (dry8 behaviour)")
ap.add_argument("--live-proposal", choices=("shorter", "mutual"), default="shorter",
                help="--attach: overlap a live row-side needs to PROPOSE its group (confirmed by the locus test)")
ap.add_argument("--show-attach", type=int, action="append", default=[], help="report this live group's attachments")
ap.add_argument("--manifest", default="restored_blocked_manifest.tsv")
ap.add_argument("--show", type=int, default=12)
ap.add_argument("--commit", action="store_true")
ap.add_argument("--config", default="/etc/text-pair/global_settings.ini")
args = ap.parse_args()

# ---------------------------------------------------------------- the list
entries = {}
for i, line in enumerate(open(args.phrases, encoding="utf-8",
                              errors="replace"), 1):
    p = line.rstrip("\n").strip()
    if p:
        entries[i] = p

unblock_lines = set(args.unblock_line)
if args.verdicts:
    cur_line = None
    for line in open(args.verdicts, encoding="utf-8"):
        m = re.match(r"\s*line (\d+)", line)
        if m:
            cur_line = int(m.group(1))
        elif line.startswith("VERDICT:") and cur_line is not None:
            if "QUOTATION" in line.upper():
                unblock_lines.add(cur_line)
            cur_line = None
unblock = {entries[i] for i in unblock_lines if i in entries}
unblock |= set(args.unblock_text)
KEYS = set()
if args.keys:
    if not args.why.strip():
        sys.exit("\n  --keys needs --why: an ingest without a recorded reading is indistinguishable from an accident.\n")
    for line in open(args.keys, encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) >= 4 and p[1].strip().lstrip("-").isdigit():
            KEYS.add((os.path.basename(p[0]), int(p[1]), os.path.basename(p[2]), int(p[3])))
    if not KEYS:
        sys.exit(f"\n  {args.keys}: no keys read.\n")
    if args.locus_key == "phrase":
        args.locus_key = "source-passage"   # no phrase in keys mode: one group per distinct passage
if not unblock and not KEYS:
    sys.exit("\n  Nothing to unblock. Give --unblock-line, --unblock-text or "
             "an annotated --verdicts file.\n")

keep_block = [p for i, p in entries.items() if p not in unblock]

try:
    import ahocorasick
except ImportError:
    sys.exit("\n  needs the ahocorasick module, as run_filter_pipeline.py "
             "does.\n")
A = ahocorasick.Automaton()
for p in keep_block:
    A.add_word(p.lower(), p)
A.make_automaton()
U = ahocorasick.Automaton()
for p in unblock:
    U.add_word(p.lower(), p)
if unblock:
    U.make_automaton()   # empty in --keys mode, and never consulted there

W = 78
print("=" * W)
print("RESTORE ALIGNMENTS BLOCKED BY ENTRIES NOW JUDGED WRONG")
print("=" * W)
print(f"""
  blocklist        {len(entries):,} entr(ies)
  UNBLOCKED        {len(unblock):,}
  still blocking   {len(keep_block):,}
  raw file         {args.raw}
  mode             {'COMMIT' if args.commit else 'DRY RUN'}
""")
for p in sorted(unblock)[:args.show]:
    print(f"      unblocked: {p[:64]!r}")
print()


# ------------------------------------------------- step 1, faithfully re-run
def alpha_ratio(text):
    ns = text.replace(" ", "")
    return len(re.findall(r"[a-zA-ZÀ-ÿ]", ns)) / len(ns) if ns else 0.0


def safe_float(v, d=50.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def opener(path):
    if path.endswith(".lz4"):
        return subprocess.Popen(["lz4", "-dc", path],
                                stdout=subprocess.PIPE).stdout
    return open(path, "rb")


cand, why = [], Counter()
n = 0
t0 = time.time()
print(f"  scanning {args.raw} — progress every 200,000 records ...",
      file=sys.stderr, flush=True)
for rawline in opener(args.raw):
    try:
        rec = json.loads(rawline)
    except Exception:
        continue
    n += 1
    if n % 200_000 == 0:
        print(f"  {n:,} scanned, {len(cand):,} candidate(s), "
              f"{time.time() - t0:.0f}s", file=sys.stderr, flush=True)
    sp = rec.get("source_passage") or ""
    tp = rec.get("target_passage") or ""
    blob = (sp + " " + tp).lower()

    if KEYS:
        try:
            k = (os.path.basename(str(rec.get("source_filename") or "")), int(rec.get("source_start_byte") or -1),
                 os.path.basename(str(rec.get("target_filename") or "")), int(rec.get("target_start_byte") or -1))
        except (TypeError, ValueError):
            continue
        if k in KEYS:
            notes = []
            if next(A.iter(blob), None) is not None: notes.append("blocklist")
            if len(sp.split()) < args.min_words: notes.append("short")
            if min(alpha_ratio(sp), alpha_ratio(tp)) < args.alpha: notes.append("OCR")
            why["named by --keys" + (" (step-1 would flag: " + ", ".join(notes) + ")" if notes else "")] += 1
            cand.append(rec)
        continue

    # it must have been rejected by an UNBLOCKED entry ...
    if next(U.iter(blob), None) is None:
        continue
    # ... and must not be caught by anything still blocking ...
    if next(A.iter(blob), None) is not None:
        why["still on the blocklist"] += 1
        continue
    # ... nor by the other three rules, re-applied in full.
    if not args.no_position:
        se, te = safe_float(rec.get("source_end_position")), safe_float(rec.get("target_end_position"))
        ss, ts = safe_float(rec.get("source_start_position")), safe_float(rec.get("target_start_position"))
        if ((se > args.pos_high and te > args.pos_high)
                or (ss < args.pos_low and ts < args.pos_low)):
            if len(sp.split()) < 100 and len(tp.split()) < 100:
                why["position paratext"] += 1
                continue
    if len(sp.split()) < args.min_words:
        why["too short"] += 1
        continue
    if min(alpha_ratio(sp), alpha_ratio(tp)) < args.alpha:
        why["OCR"] += 1
        continue
    cand.append(rec)

print(f"  scanned {n:,} record(s) in {time.time() - t0:.0f}s")
print(f"  matched an unblocked entry and PASS every other step-1 rule: "
      f"{len(cand):,}")
for k, v in why.most_common():
    print(f"      held back — {k:<28}{v:>8,}")

if not cand:
    sys.exit("\n  Nothing to restore.\n")

# ------------------------------------------------------------ dedup, by text
cfg = configparser.ConfigParser()
cfg.read(args.config)
cn = psycopg2.connect(user=cfg["DATABASE"]["database_user"],
                      password=cfg["DATABASE"]["database_password"],
                      database=cfg["DATABASE"]["database_name"])
cur = cn.cursor()
cur.execute("SET statement_timeout = 0")


def key(rec):
    """Whitespace-collapsed, lowercased — the same normalisation the SQL side
    applies, so the two are comparable. Not folded: a restored row comes from
    the same raw data as any twin already in the corpus, so the texts are
    identical or they are different alignments."""
    s = " ".join((rec.get("source_passage") or "").split()).lower()
    t = " ".join((rec.get("target_passage") or "").split()).lower()
    return (s, t)


cur.execute("""SELECT column_name, data_type, is_nullable, column_default
                  FROM information_schema.columns
                 WHERE table_name = %s""", (args.table,))
_schema = {r[0]: {"type": r[1], "nullable": r[2] == "YES", "default": r[3]}
           for r in cur.fetchall()}
_types = {c: v["type"] for c, v in _schema.items()}
cols = set(_schema)

# ROWID IS NOT AUTOMATIC. 5 Sep: excluded as auto-generated, and the dry run
# failed on `null value in column "rowid" violates not-null constraint`. It
# is NOT NULL with no default, so the original loader assigned it and this
# one must too.
#
# AND UNIQUENESS MUST HOLD ACROSS ALL SEVEN TABLES, not just this one: rows
# MOVE between them (that is what every set-aside is), so a rowid colliding
# with a row currently sitting in classified_noise would collide the moment
# either is restored. The base is the max over the whole seven-table universe.
_rowid_col = ("rowid" if "rowid" in cols
              and not _schema["rowid"]["nullable"]
              and not _schema["rowid"]["default"] else None)
_next_rowid = None
if _rowid_col:
    _tabs = [args.table]
    try:
        _tabs += [t for t in CS.KNOWN_SETASIDE if t != args.table]
    except Exception:
        pass
    _mx = 0
    for t in _tabs:
        cur.execute("SELECT to_regclass(%s)", (t,))
        if cur.fetchone()[0] is None:
            continue
        cur.execute(f"SELECT COALESCE(max(rowid), 0) FROM {t}")
        _mx = max(_mx, cur.fetchone()[0] or 0)
    _next_rowid = _mx + 1
    print(f"  rowid is NOT NULL with no default — assigning from "
          f"{_next_rowid:,}, the max across {len(_tabs)} table(s) + 1")

# THE JSONL IS UNTYPED AND THE TABLE IS NOT. 5 Sep: a commit died on
# `invalid input syntax for type integer: "41.01"` — a position the jsonl
# carries as a decimal string against an integer column. The original loader
# must have coerced it; this one has to as well, and must SAY what it
# coerced rather than doing it silently.
_INT = {"integer", "bigint", "smallint"}
_FLOAT = {"numeric", "real", "double precision"}
_coerced = Counter()


def cast(col, v):
    if v is None or v == "":
        return None
    t = _types.get(col, "")
    try:
        if t in _INT:
            iv = int(float(v))
            if str(v) != str(iv):
                _coerced[col] += 1
            return iv
        if t in _FLOAT:
            return float(v)
        if t == "boolean":
            return v if isinstance(v, bool) else str(v).lower() in ("t", "true", "1")
    except (TypeError, ValueError):
        _coerced[col + " (UNPARSEABLE -> NULL)"] += 1
        return None
    return v
if not cols:
    sys.exit(f"  {args.table} does not exist.")

# ONE PASS, NOT ONE QUERY PER CANDIDATE. The first version ran a pair of
# unanchored LIKEs against 1.36M rows for every candidate: tolerable for the
# six of entry 8786 and hours once a whole verdicts file is unblocked. The
# keys go into a temp table and Postgres hash-joins them in a single scan.
#
# And the match is now EXACT on the whitespace-collapsed, lowercased passage
# rather than a 120-character LIKE. A row restored from the same raw data
# carries the same text, so exactness is right here; the loose form was me
# being careless and it would have called near-misses duplicates.
# NARROW BEFORE NORMALISING. Every candidate contains an unblocked phrase, so
# any duplicate already in the corpus contains it too. Filtering on a plain
# substring first turns a regexp_replace over 2.7M text values into one over a
# handful. The fragment carries no accent and no apostrophe, for the reason
# the whole day has been about.
_BREAK = re.compile(r"[^\x00-\x7f]|['\u2019\u02bc\u2018`]")
frags = []
for phrase in unblock:
    parts = [x.strip() for x in _BREAK.split(phrase)]
    best = max(parts, key=len) if parts else ""
    if len(best) >= 8:
        frags.append(f"%{best}%")
if KEYS:
    frags = sorted({f"%/{k[0]}" for k in KEYS} | {f"%/{k[2]}" for k in KEYS})
    narrow = "(source_filename LIKE ANY(%(f)s) OR target_filename LIKE ANY(%(f)s))"
    print(f"  dedup narrowed to {len(frags)} named document(s)")
elif frags:
    narrow = ("(source_passage ILIKE ANY(%(f)s) "
              "OR target_passage ILIKE ANY(%(f)s))")
    print(f"  dedup narrowed by {len(frags)} fragment(s), e.g. "
          f"{frags[0][1:-1]!r}")
else:
    narrow = "TRUE"
    print("  ** no unblocked phrase yields an ASCII fragment of 8+ chars, so\n"
          "  ** the dedup scans the whole table. This will be slow.")

cur.execute("CREATE TEMP TABLE _cand (idx int, s text, t text) ON COMMIT DROP")
from psycopg2.extras import execute_values
execute_values(cur, "INSERT INTO _cand (idx, s, t) VALUES %s",
               [(i, *key(r)) for i, r in enumerate(cand)])
# 6 Oct 2026: a btree on the passages themselves fails on long ones ("index row requires 8248 bytes, maximum
# size is 8191") -- the first wave of 5,609 step-2 records carried a 70-line passage. Index and join on md5 of the
# normalised text instead; the full-text equality is still checked, so a hash collision cannot pass as a duplicate.
cur.execute("CREATE INDEX ON _cand (md5(s), md5(t))")
t_d = time.time()
cur.execute(f"""WITH hit AS (
                  SELECT btrim(lower(regexp_replace(source_passage, '\s+', ' ', 'g')))
                           AS s,
                         btrim(lower(regexp_replace(target_passage, '\s+', ' ', 'g')))
                           AS t
                    FROM {args.table}
                   WHERE {narrow}
                )
                SELECT DISTINCT c.idx
                  FROM _cand c JOIN hit h ON md5(h.s) = md5(c.s) AND md5(h.t) = md5(c.t)
                                         AND h.s = c.s AND h.t = c.t""",
            {"f": frags} if frags else {})
print(f"  dedup join {time.time() - t_d:.0f}s")
dupe_idx = {r[0] for r in cur.fetchall()}
present = dupe_idx
fresh = [r for i, r in enumerate(cand) if i not in dupe_idx]
print(f"\n  already in {args.table} (passage-pair key): {len(present):,}")
print(f"  NEW rows to insert:                          {len(fresh):,}")

# 27 Sep 2026: ids are free only if free in EVERY table (corpus_source).
base = CS.next_free_group_id(cur, args.table)
def _foldish(t):
    import unicodedata
    t = unicodedata.normalize("NFKD", " ".join(str(t or "").split()).lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", t).strip()


def locus_of(rec):
    if args.locus_key == "run-group":
        # 6 Oct 2026: step-2 losses come back as the run's OWN groups -- the run had already grouped them, and a
        # removed run-group is one passage family by construction. Read from a clean1 file, which carries group_id.
        return ("run-group", rec.get("group_id"))
    if args.locus_key == "doc-pair":
        return (rec.get("source_filename"), rec.get("target_filename"),
                key(rec)[0])
    if args.locus_key == "source-passage":
        return _foldish(rec.get("source_passage"))
    blob = ((rec.get("source_passage") or "") + " " +
            (rec.get("target_passage") or "")).lower()
    hit = next(U.iter(blob), None)
    return hit[1] if hit else "(no phrase)"


# --locus-key span (10 Oct 2026). 'source-passage' made 12,226 groups for 18,318 rows: the same
# Horace line is cut at different bytes by every alignment, so exact passages never repeat; and
# 'run-group' rebuilds the 2,000-row welds. 'span' joins rows that share TEXT: two row-sides on
# the same file whose byte ranges overlap by at least --span-overlap of the shorter range, and a
# row's own two sides. Transitive, so every witness of one PHI line meets through the PHI span.
SPAN_OV = 0.5
SPAN_MAX = args.span_max
if args.locus_key == "span":
    # Nodes 0..n-1 are the fresh rows; nodes from n are LIVE row-sides (--attach) carrying their group_id.
    n0 = len(fresh)
    par = list(range(n0))
    node_gid = {}                      # live node -> its group_id
    def _f(i):
        while par[i] != i:
            par[i] = par[par[i]]; i = par[i]
        return i
    def _u(i, j):
        ri, rj = _f(i), _f(j)
        if ri != rj: par[max(ri, rj)] = min(ri, rj)
    sides = defaultdict(list)          # file -> [(start, end, node)]
    for i, rec in enumerate(fresh):
        for sd in ("source", "target"):
            try:
                st, en = int(rec.get(f"{sd}_start_byte")), int(rec.get(f"{sd}_end_byte"))
            except (TypeError, ValueError):
                continue
            if en - st > SPAN_MAX and not (args.attach and args.long_propose):
                continue               # a long side cannot bridge loci (long alignments weld; 21 Aug ruling)
            sides[rec.get(f"{sd}_filename")].append((st, max(en, st + 1), i))
    if args.attach:
        # --attach (Glenn, 10 Oct 2026): restored rows JOIN the live group that already holds their
        # passage, judged by the same span test against the live rows of the same files. A family that
        # meets ONE live group takes its id (an attachment: no live group changes id or loses a row);
        # one meeting TWO OR MORE is not joined to any -- that would be a merge, and merges are frozen --
        # so it comes in as a new group and is listed for reading.
        files = sorted(sides)
        t_a = time.time(); nlive = 0
        for sd in ("source", "target"):
            cur.execute(f"""SELECT {sd}_filename, {sd}_start_byte, {sd}_end_byte, group_id FROM {args.table}
                             WHERE {sd}_filename = ANY(%s) AND group_id IS NOT NULL""", (files,))
            for f, st, en, g in cur.fetchall():
                try: st, en = int(st), int(en)
                except (TypeError, ValueError): continue
                if en - st > SPAN_MAX and not args.long_propose: continue
                node = len(par); par.append(node); node_gid[node] = g; nlive += 1
                sides[f].append((st, max(en, st + 1), node))
        print(f"  --attach: {nlive:,} live row-side(s) on {len(files):,} file(s) loaded ({time.time() - t_a:.0f}s)")
    direct = defaultdict(set)          # fresh row -> live groups whose rows share its span
    for f, iv in sides.items():
        iv.sort()
        active = []                    # intervals still open, (end, start, node)
        for st, en, i in iv:
            active = [x for x in active if x[0] > st]
            for e2, s2, j in active:
                if i >= n0 and j >= n0:
                    continue           # live-live overlap is not ours to judge (the merge freeze)
                live_pair = i >= n0 or j >= n0
                if not live_pair and (en - st > SPAN_MAX or e2 - s2 > SPAN_MAX):
                    continue           # long sides never build families (21 Aug ruling); with
                                       # --long-propose they may only PROPOSE a live group (dry8:
                                       # PHI-side Georgics spans are 12-20 KB, so a quotation whose
                                       # other side is on an unaligned file could never be proposed)
                ov = min(en, e2) - st
                # MUTUAL by default (10 Oct 2026): the overlap must cover half of BOTH spans. Measured
                # on the Boileau test: 'half of the shorter' let one restored family meet Art poetique
                # III 1-4, III 5-8 and Lucretius 1.32 -- a short span contained in a longer one is a
                # different extent, and contiguous quotations chained through it.
                # A fresh-live pair only PROPOSES a candidate (10 Oct 2026, after dry8: Georgics
                # 4.221 did not reach 10900007289): half of the SHORTER span suffices, because the
                # per-row locus test confirms. Fresh-fresh pairs build families and stay MUTUAL.
                mutual = args.span_mutual and not (live_pair and args.live_proposal == "shorter")
                need = (max if mutual else min)(en - st, e2 - s2)
                if ov >= SPAN_OV * need:
                    if live_pair:
                        # ROW-LEVEL PROPOSAL (10 Oct 2026, dry7): a live row-side is NOT a union node.
                        # Unioning through live rows let one family chain Boileau III 1-4 and a
                        # Lucretius group through a live row that touched both; the fresh row
                        # records the live group as a candidate of ITS OWN instead.
                        fi, lj = (i, j) if j >= n0 else (j, i)
                        direct[fi].add(node_gid[lj])
                    else:
                        _u(i, j)
            active.append((en, st, i))
    comp_live = defaultdict(set)
    for i, gs in direct.items():
        comp_live[_f(i)] |= gs
    # CONFIRM WITH THE PROJECT'S OWN LOCUS TEST (10 Oct 2026, Glenn: "don't we have a loci tool
    # just for this?"). Byte spans only PROPOSE candidate live groups; a candidate is kept only if
    # locus_test.compare() finds shared material -- a run of 4 words or 0.80 containment -- between
    # the family's passages and the group's, both taken from passages of at most --bridge-words
    # words (group_loci.py's bridge rule: a long alignment shares wording with everything near it).
    fam_rows = defaultdict(list)
    for i in range(n0):
        fam_rows[_f(i)].append(fresh[i])
    confirmed = {}
    row_ok = {}
    if args.attach:
        import locus_test as LT
        cand = sorted({g for gs in comp_live.values() for g in gs})
        gpass = defaultdict(list)
        gsize = Counter()
        prefer = {}
        if args.attach_prefer and os.path.exists(args.attach_prefer):
            with open(args.attach_prefer, encoding="utf-8") as fh:
                for ln in fh:
                    pr = ln.split("#")[0].split()
                    if len(pr) >= 2 and pr[0].isdigit():
                        for o in pr[1:]:
                            prefer[int(o)] = int(pr[0])
            print(f"  --attach-prefer: {len(prefer)} group(s) yield to a preferred group ({args.attach_prefer})")
        if cand:
            cur.execute(f"SELECT group_id, source_passage, target_passage FROM {args.table} WHERE group_id = ANY(%s)", (cand,))
            for g, sp_, tp_ in cur.fetchall():
                gsize[g] += 1
                for t in (sp_, tp_):
                    if t and len(str(t).split()) <= args.bridge_words:
                        gpass[g].append(str(t))
        def fam_pass(rows):
            out = []
            for r in rows:
                for t in (r.get("source_passage"), r.get("target_passage")):
                    if t and len(str(t).split()) <= args.bridge_words:
                        out.append(str(t))
            return out
        # principal locus of a live group: its largest cluster, clustered as group_loci.py does
        pcache = {}
        def principal(g):
            if g in pcache:
                return pcache[g]
            seen = {}
            for t in gpass[g]:
                k = LT.keyed(t, LT.MIN_RUN)
                if k[0] and (k[0] not in seen or len(t) > len(seen[k[0]])):
                    seen[k[0]] = t
            uniq = sorted(seen.values(), key=len, reverse=True)
            par_ = list(range(len(uniq)))
            def fd(x):
                while par_[x] != x:
                    par_[x] = par_[par_[x]]; x = par_[x]
                return x
            bysh = defaultdict(list)
            for j, t in enumerate(uniq):
                for shg in LT.keyed(t, LT.MIN_RUN)[3]:
                    bysh[shg].append(j)
            for m in bysh.values():
                for j in m[1:]:
                    a, b = fd(m[0]), fd(j)
                    if a != b: par_[a] = b
            cl = defaultdict(list)
            for j in range(len(uniq)): cl[fd(j)].append(j)
            reps = [max(c, key=lambda j: len(uniq[j])) for c in cl.values()]
            for a in range(len(reps)):
                for b in range(a + 1, len(reps)):
                    if fd(reps[a]) == fd(reps[b]): continue
                    v = LT.compare([uniq[reps[a]]], [uniq[reps[b]]], max_passages=1)
                    if v[1] >= LT.MERGE_CONTAINMENT:
                        x, y = fd(reps[a]), fd(reps[b]); par_[x] = y
            cl = defaultdict(list)
            for j in range(len(uniq)): cl[fd(j)].append(j)
            big = max(cl.values(), key=len) if cl else []
            pcache[g] = [uniq[j] for j in big]
            return pcache[g]
        def on_principal(i, g):
            pl = principal(g); fp = fam_pass([fresh[i]])
            return bool(pl and fp) and LT.coherent(LT.compare(fp, pl, max_passages=len(pl)))
        # PER-ROW CONFIRMATION (10 Oct 2026, dry7): each fresh row is tested only against the live
        # groups ITS OWN spans touch, with ITS OWN passages. Family-level testing pooled 128 rows'
        # passages, so any one stray 4-word run confirmed a group for the whole family.
        t_c = time.time(); ntest = 0
        for i, gs in direct.items():
            fp = fam_pass([fresh[i]])
            ok = set()
            for g in gs:
                if not fp or not gpass.get(g):
                    continue
                ntest += 1
                if LT.coherent(LT.compare(fp, gpass[g], max_passages=args.locus_passages)):
                    ok.add(g)
            row_ok[i] = ok
        # DOMINANT GROUP (10 Oct 2026, dry9): a row confirming 2+ live groups is tested against each
        # group's passages ONE BY ONE; its share is the fraction of that group's passages it matches.
        # The group whose locus IS the row's passage matches most of them; a welded group that merely
        # holds one witness of it matches few. The row attaches to the top group only if its share is
        # >= --dominant-min and at least --dominant-ratio times the runner-up; otherwise it stays held
        # (two groups both wholly this passage are a duplicate pair -- a merge question, not ours).
        ndom = nmulti = 0
        shares_of = {}
        if args.dominant_min > 0:
            gsample = {}
            for i, ok in list(row_ok.items()):
                # --attach-prefer applies to what the locus test CONFIRMED, before any share is
                # measured (dry10: 10900007289's passages are partly French, so a Latin row's share
                # of it fell under 0.5 and the rows went to 1200003681, the group Glenn ruled against).
                if prefer and len(ok) > 1:
                    ok = {g for g in ok if prefer.get(g) not in ok}
                    row_ok[i] = ok
                if len(ok) < 2:
                    continue
                nmulti += 1
                fp = fam_pass([fresh[i]])
                sh = {}
                for g in ok:
                    if g not in gsample:
                        gsample[g] = LT.sample(gpass[g], args.dominant_passages)
                    ps = gsample[g]
                    hit = sum(1 for p_ in ps if LT.coherent(LT.compare(fp, [p_], max_passages=args.locus_passages)))
                    sh[g] = hit / max(1, len(ps))
                shares_of[i] = sh
                # Qualifying groups hold this passage as their locus (share >= --dominant-min). Of
                # those, the row takes the LARGEST if it is --dominant-ratio times the next: a
                # singleton holding one more witness of the line is an orphan of the big group, not a
                # rival (dry10: Virgil singletons 10300040276 etc. beside 10900007289). Two large
                # groups of one passage are a duplicate pair -- held, unless --attach-prefer names one.
                # A group QUALIFIES if the row shares text with its PRINCIPAL locus (dry11: a share
                # threshold failed bilingual 10900007289 -- Latin rows matched 15-20% of its passages,
                # all of them on its principal locus -- and handed the rows to 5-row Cicero orphans).
                if args.principal_gate:
                    q = {g for g in ok if on_principal(i, g)}
                else:
                    q = {g for g, v in sh.items() if v >= args.dominant_min}
                q = {g for g in q if prefer.get(g) not in q}
                if not q and not args.principal_gate:
                    top = sorted(sh.items(), key=lambda x: -x[1])
                    if top[0][1] > 0 and top[0][1] >= args.dominant_ratio * top[1][1]:
                        q = {top[0][0]}
                big = sorted(q, key=lambda g: -gsize[g])
                if big and (len(big) == 1 or gsize[big[0]] >= args.dominant_ratio * gsize[big[1]]):
                    row_ok[i] = {big[0]}; ndom += 1
            print(f"  dominant group: {nmulti:,} row(s) confirmed 2+ live groups; {ndom:,} have a dominant one "
                  + (f"(row on the group's principal locus" if args.principal_gate else f"(share >= {args.dominant_min}") + f"; largest qualifying group >= {args.dominant_ratio}x the next, or preferred) and take it")
        # ATTACH AUDIT (10 Oct 2026, Glenn: "so long as you're not merging passages that don't share
        # any text"). Every attachment already passed the locus test on the row's OWN passages; this
        # measures HOW MUCH of the target group it shares (fraction of up to --dominant-passages of the
        # group's passages it matches one by one) and lists the thin ones for reading before --commit.
        if args.audit_share > 0:
            t_au = time.time(); thin = []
            gs_cache = {}
            for i, ok in row_ok.items():
                if len(ok) != 1:
                    continue
                g = next(iter(ok))
                sh = shares_of.get(i, {}).get(g)
                if sh is None:
                    if g not in gs_cache:
                        gs_cache[g] = LT.sample(gpass[g], args.dominant_passages)
                    ps = gs_cache[g]
                    fp = fam_pass([fresh[i]])
                    sh = sum(1 for p_ in ps if LT.coherent(LT.compare(fp, [p_], max_passages=args.locus_passages))) / max(1, len(ps))
                if sh < args.audit_share:
                    thin.append((sh, i, g))
            # PRINCIPAL-LOCUS GATE (10 Oct 2026). group_loci.py on the thin list's groups: the thin rows
            # of 10300001543 (Segnius irritant), 1200000912 (O navis) matched each group's LARGEST locus
            # -- right home, welded elsewhere by bridges; those of 10300004432 (in puppim ferit, beside
            # 'Apparent rari nantes') and 11200218649 (Odes 3.6.46 in a four-locus Voltaire group) matched
            # a minor one -- a stray witness. A thin row attaches only if it coheres with the group's
            # principal locus, clustered exactly as group_loci.py does (4-word shingles over passages of
            # <= --bridge-words, then 0.80 containment between cluster representatives).
            nprin = 0
            if args.principal_gate:
                for k_, (sh, i, g) in enumerate(thin):
                    ok_ = on_principal(i, g)
                    if not ok_:
                        row_ok[i] = set(); nprin += 1
                    thin[k_] = (sh, i, g, ok_)
            else:
                thin = [(sh, i, g, None) for sh, i, g in thin]
            thin.sort(key=lambda x: (x[0], x[1]))
            with open(args.audit_file, "w", encoding="utf-8") as fh:
                fh.write("share\tprincipal\tgroup_id\tgroup_rows\tsource_author\ttarget_author\tsource_passage\ttarget_passage\n")
                for sh, i, g, ok_ in thin:
                    r = fresh[i]
                    cl = lambda t: " ".join(str(t or "").split())[:200]
                    fh.write(f"{sh:.2f}\t{'' if ok_ is None else ('yes' if ok_ else 'NO-new')}\t{g}\t{gsize[g]}\t{r.get('source_author')}\t{r.get('target_author')}\t"
                             f"{cl(r.get('source_passage'))}\t{cl(r.get('target_passage'))}\n")
            print(f"  attach audit: {len(thin):,} attaching row(s) match under {args.audit_share:.0%} of their group's "
                  f"passages -> {args.audit_file} ({time.time() - t_au:.0f}s)"
                  + (f"; {nprin:,} miss their group's principal locus and come in NEW instead" if args.principal_gate else ""))
        for i, ok in row_ok.items():
            confirmed.setdefault(_f(i), set()).update(ok)
        print(f"  locus test: {ntest:,} row x live-group candidate(s) scored ({time.time() - t_c:.0f}s); "
              f"{sum(len(gs) for gs in direct.values()):,} row proposals by span, "
              f"{sum(len(v) for v in row_ok.values()):,} confirmed; families confirming 1 group: "
              f"{sum(1 for v in confirmed.values() if len(v) == 1):,}, 2+: {sum(1 for v in confirmed.values() if len(v) > 1):,}")
        for g in args.show_attach:
            rows = [i for i, gs in direct.items() if g in gs]
            print(f"  test group {g}: proposed for {len(rows)} fresh row(s), confirmed for "
                  f"{sum(1 for i in rows if g in row_ok.get(i, ()))}")
            for i in rows[:15]:
                rec = fresh[i]
                print(f"    row {i} fam {_f(i)} {'OK ' if g in row_ok.get(i, ()) else 'no '}"
                      f"{str(rec.get('source_author'))[:18]} x {str(rec.get('target_author'))[:18]}; "
                      f"other live: {sorted(row_ok.get(i, set()) - {g})[:4]}; "
                      + (f"shares {', '.join(f'{x}:{v:.2f}' for x, v in sorted(shares_of[i].items(), key=lambda t: -t[1])[:4])}; " if i in shares_of else "")
                      + f"{' '.join(str(rec.get('source_passage') or '').split())[:70]!r}")
    root_key, held = {}, []
    for i in range(n0):
        r = _f(i)
        if r in root_key: continue
        gs = confirmed.get(r, set()) if args.attach else set()
        if len(gs) == 1:
            root_key[r] = ("live", next(iter(gs)))
        else:
            root_key[r] = ("new", r)
            if len(gs) > 1: held.append((r, sorted(gs)))
    # A family meeting 2+ live groups is not attached as a whole (that would merge them). Its rows
    # that EACH confirm exactly one live group on their own attach to that group; the rest come in
    # as the family's new group. (10 Oct 2026)
    held_roots = {r for r, _gs in held}
    _row_key = {}
    nsplit = 0
    for i in range(n0):
        r = _f(i)
        k = root_key[r]
        if args.attach and r in held_roots and len(row_ok.get(i, ())) == 1:
            k = ("live", next(iter(row_ok[i]))); nsplit += 1
        _row_key[i] = k
    _span_key = {id(rec): _row_key[i] for i, rec in enumerate(fresh)}
    if args.attach:
        print(f"  held families: {nsplit:,} row(s) confirm exactly one live group on their own and attach to it")
    def locus_of(rec):
        return _span_key[id(rec)]
    _sz = Counter(_span_key.values())
    att = [k for k in _sz if k[0] == "live"]
    print(f"  span loci: {len(_sz):,}; largest {', '.join(str(n) for _g, n in _sz.most_common(8))}"
          f"  (--span-max {SPAN_MAX} bytes)")
    if args.attach:
        print(f"  ATTACHED to an existing live group: {sum(_sz[k] for k in att):,} row(s) into {len(att):,} group(s)")
        print(f"  NEW groups (no live group shares the span): {sum(n for k, n in _sz.items() if k[0] == 'new'):,} row(s)")
        print(f"  HELD -- meets 2+ live groups, comes in as a NEW group, read before any merge: "
              f"{sum(_sz[('new', r)] for r, _gs in held):,} row(s) in {len(held):,} famil(ies)")
        with open(args.attach_held, "w", encoding="utf-8") as fh:
            fh.write("family_root\trows\tlive_groups\n")
            for r, gs in held:
                fh.write(f"{r}\t{_sz[('new', r)]}\t{','.join(map(str, gs))}\n")
        print(f"      -> {args.attach_held}")
        for g in args.show_attach:
            n = _sz.get(("live", g), 0)
            hx = [(r, gs) for r, gs in held if g in gs]
            print(f"  test group {g}: {n:,} restored row(s) would ATTACH"
                  + (f"; also in {len(hx)} held famil(ies) with {', '.join(str(x) for x in hx[0][1][:6])}" if hx else ""))
    for k, n in _sz.most_common(3):
        mem = [r for r in fresh if _span_key[id(r)] == k]
        au = Counter(str(r.get("source_author"))[:24] for r in mem) + Counter(str(r.get("target_author"))[:24] for r in mem)
        ln = sorted(int(r.get("source_end_byte") or 0) - int(r.get("source_start_byte") or 0) for r in mem)
        print(f"    locus of {n} ({'attaches to ' + str(k[1]) if k[0] == 'live' else 'new'}): median source span "
              f"{ln[len(ln)//2]} bytes; authors " + "; ".join(f"{a} x{c}" for a, c in au.most_common(5)))
        print(f"      e.g. {' '.join(str(mem[0].get('source_passage') or '').split())[:120]!r}")
loci = {}
_nnew = 0
for rec in fresh:
    k = locus_of(rec)
    if k not in loci:
        if isinstance(k, tuple) and k and k[0] == "live":
            loci[k] = k[1]             # attached: the live group's own id
        else:
            loci[k] = base + _nnew; _nnew += 1
print(f"  new group ids from {base:,}, {len(loci):,} group(s) "
      f"(--locus-key {args.locus_key})")
if len(loci) > len(fresh) * 0.5:
    print("  ** MORE THAN ONE GROUP PER TWO ROWS. The key is splitting what "
          "should\n  ** be one locus — check --locus-key before committing.")

print(f"\n  {'':<4}{'source':<44}{'target'}")
for rec in fresh[:args.show]:
    print(f"      ({rec.get('source_year')}) "
          f"{str(rec.get('source_author'))[:28]} — "
          f"{str(rec.get('source_title'))[:28]}")
    print(f"      ({rec.get('target_year')}) "
          f"{str(rec.get('target_author'))[:28]} — "
          f"{str(rec.get('target_title'))[:28]}")
    print(f"        {' '.join((rec.get('source_passage') or '').split())[:150]!r}\n")

# WHAT ACTUALLY GETS WRITTEN. The first version listed eleven columns by
# hand and would have inserted rows with no positions, no scores and no
# ngram data — shaped unlike every other row in the corpus, and invisible to
# any instrument reading those fields. Take every column the table has that
# the jsonl supplies, and DERIVE the ones it does not.
CORPORA = ["modern_all_pruned", "modern_pamphlets", "modern_letters",
           "modern_press", "modern_dicos", "modern_all", "gallica_mono"]


def corpus_of(path):
    """The `corpus` column's OWN vocabulary, which is coarse.

    5 Sep: the first version returned sub-corpus directory names —
    'modern_all', 'gallica_mono' — and the dry run showed the column holds
    only 'gallica' and 'modern'. It would have invented a third value in a
    column other instruments filter on. Ask what a column contains before
    writing to it; the guard below now refuses a value the table has never
    seen.
    """
    p = str(path or "").lower()
    return "gallica" if "gallica" in p else "modern"


def derived(rec, col):
    if col == "source_passage_length":
        return len(rec.get("source_passage") or "")
    if col == "target_passage_length":
        return len(rec.get("target_passage") or "")
    if col == "corpus":
        return corpus_of(rec.get("source_filename"))
    return None


supplied = sorted((set(fresh[0].keys()) & cols) - {"rowid", "group_id"})
# the jsonl's own `rowid`, if it has one, is NOT ours — see the note above
# and martial_label_map's: alignment_id is not our rowid, 0 of 470 agreed.
derivable = [c for c in sorted(cols) if c not in supplied
             and c not in ("rowid", "group_id")
             and derived(fresh[0], c) is not None]
still_null = sorted(cols - set(supplied) - set(derivable)
                    - {"rowid", "group_id"})
ins_cols = supplied + derivable + ["group_id"] + (
    [_rowid_col] if _rowid_col else [])

print(f"\n  {args.table} has {len(cols)} column(s)")
print(f"      from the jsonl   {len(supplied)}")
print(f"      derived here     {len(derivable)}"
      f"{'  (' + ', '.join(derivable) + ')' if derivable else ''}")
print(f"      left NULL        {len(still_null)}"
      f"{'  (' + ', '.join(still_null[:10]) + ')' if still_null else ''}")
cur.execute(f"SELECT DISTINCT corpus FROM {args.table} LIMIT 12"
            if "corpus" in cols else "SELECT 1 WHERE FALSE")
vals = [r[0] for r in cur.fetchall()]
would = {corpus_of(r.get("source_filename")) for r in fresh}
if vals:
    print(f"      `corpus` in the table holds: {', '.join(map(str, vals))}")
    print(f"      and this run would write:    {', '.join(sorted(would))}")
    novel = would - set(map(str, vals))
    if novel and not args.allow_new_corpus_value:
        sys.exit(f"""
  REFUSING: this run would write corpus value(s) {sorted(novel)} that
  {args.table} has never held. A new value in a column other instruments
  filter on makes the restored rows invisible to them without any error.
  Fix the derivation, or pass --allow-new-corpus-value deliberately.
""")

# A DRY RUN THAT DOES NOT ATTEMPT THE INSERT IS NOT TESTING THE WRITE.
# 5 Sep: the type error above surfaced only on --commit, after four clean
# dry runs. Both modes now execute the same inserts; the difference is the
# COMMIT at the end. A dry run rolls back, so it exercises every constraint,
# type and trigger the real one will meet.
rows, manifest_lines = 0, []
try:
    for rec in fresh:
        gid = loci[locus_of(rec)]
        vals = []
        for c in ins_cols:
            if c == "group_id":
                v = gid
            elif c == _rowid_col:
                v = _next_rowid
                _next_rowid += 1
            elif c in supplied:
                v = rec.get(c)
            else:
                v = derived(rec, c)
            vals.append(cast(c, v))
        cur.execute(
            f"INSERT INTO {args.table} ({', '.join(ins_cols)}) "
            f"VALUES ({', '.join(['%s'] * len(ins_cols))})", vals)
        manifest_lines.append(
            f"{time.strftime('%Y-%m-%d %H:%M')}\t{gid}\t"
            f"{rec.get('source_filename')}\t{rec.get('target_filename')}\t"
            f"restored from {args.raw}" + (f" by --keys {args.keys}: {args.why}" if KEYS else ""))
        rows += 1
except Exception as e:
    cn.rollback()
    sys.exit(f"\n  INSERT FAILED after {rows:,} row(s); NOTHING was written "
             f"and nothing\n  was recorded in the manifest.\n\n  {e}\n")

if _coerced:
    print(f"\n  values coerced to the column's declared type:")
    for c, k in _coerced.most_common():
        print(f"      {c:<40}{k:>7,}")

if not args.commit:
    cn.rollback()
    print(f"""
  DRY RUN. {rows:,} row(s) were INSERTED AND ROLLED BACK, so every type and
  constraint was exercised and nothing remains. The manifest was not touched.
  Re-run with --commit to keep them: the SEVEN-TABLE TOTAL will rise by
  {rows:,} and that new figure must be recorded the same day.
""")
    cn.close()
    sys.exit(0)

# MANIFEST AFTER THE COMMIT, NEVER DURING. The first version appended inside
# the loop, so the failed commit left a manifest claiming rows that do not
# exist — an undo record that lies is worse than none.
cn.commit()
with open(args.manifest, "a", encoding="utf-8") as mf:
    mf.write("\n".join(manifest_lines) + "\n")
print(f"\n  INSERTED {rows:,} row(s) into {args.table}; manifest "
      f"{args.manifest}")
cur.execute(f"SELECT count(*) FROM {args.table}")
print(f"  {args.table} is now {cur.fetchone()[0]:,}")
print("  RE-RUN the seven-table count and record the new invariant TODAY.")
cn.close()
