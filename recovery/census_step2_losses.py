#!/usr/bin/env python3
"""
agent/census_step2_losses.py -- READ-ONLY. How much did run_filter_pipeline.py STEP 2 (group banality) remove, run by
run, and how much of it is still absent from every table today?

Step 2 drops every record whose RUN-LEVEL group (the jsonl's own group_id) holds >= 30 records in clean1, entire and
before any other judgement. Group size measures how much a passage was quoted, so the cap removes the most-reused
passages first (trace_phrase_through_filter.py, 5 Sep). On 6 Oct the La Motte / Limojon trace showed six good verse
alignments lost exactly this way and held in no table. This measures the class.

Per run directory (default: every run that fed the corpus):
  A. clean1 groups, the groups step 2 removed (>= --cap), the records they held, by group-size band
  B. whether those records are in ANY of the seven tables today (natural key, full path), against a CALIBRATION:
     the same lookup on a sample of clean-final survivors, which should be found almost always. A low calibration
     means the run's paths differ from the corpus's and B is not trustworthy for that run.
  C. --sample removed groups at random, with size, the commonest document pair and the passage, for reading:
     canonical reuse, or formula?
Usage (from cleaned/):
  nohup python3 agent/census_step2_losses.py > agent/census_step2.out 2>&1 &
  nohup python3 agent/census_step2_losses.py --run /path/to/alignements/modern_all_align/output/results > ... &
"""
import argparse, configparser, json, os, random, sys, time
from collections import Counter, defaultdict
import psycopg2
from psycopg2.extras import execute_values
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import corpus_source as CS

RUNS = ["/path/to/alignements/modern_all_align/output/results", "/path/to/alignements/modern_letters/output/results",
        "/path/to/alignements/modern_dicos/output/results", "/path/to/alignements/modern_pamphlets/output/results",
        "/path/to/alignements/modern_press/output/results", "/path/to/alignements/modern_gallica/output/results",
        "/path/to/alignements/gallica/output/results"]
ap = argparse.ArgumentParser()
ap.add_argument("--run", action="append", default=[])
ap.add_argument("--cap", type=int, default=30)
ap.add_argument("--gallica", action="store_true", help="also census the two pre-pipeline Gallica runs (cap 20)")
ap.add_argument("--sample", type=int, default=25)
ap.add_argument("--calib", type=int, default=5000)
ap.add_argument("--seed", type=int, default=6)
a = ap.parse_args()
random.seed(a.seed)
T0 = time.time()
def log(m): print(f"[{int(time.time()-T0):>5}s] {m}", file=sys.stderr, flush=True)

cfg = configparser.ConfigParser(); cfg.read("/etc/text-pair/global_settings.ini"); D = cfg["DATABASE"]
cn = psycopg2.connect(user=D["database_user"], password=D["database_password"], database=D["database_name"])
cur = cn.cursor(); cur.execute("SET statement_timeout = 0")
tabs = []
for t in ["combined_align"] + CS.KNOWN_SETASIDE:
    cur.execute("SELECT to_regclass(%s)", (t,))
    if cur.fetchone()[0]: tabs.append(t)

def nk(rec):
    try: return (rec.get("source_filename"), int(rec.get("source_start_byte")), rec.get("target_filename"), int(rec.get("target_start_byte")))
    except (TypeError, ValueError): return None

def found(keys):
    """how many of these natural keys sit in any of the seven tables"""
    keys = [k for k in keys if k]
    if not keys: return 0
    cur.execute("CREATE TEMP TABLE _k (sf text, sb bigint, tf text, tb bigint)")
    execute_values(cur, "INSERT INTO _k VALUES %s", keys, page_size=5000)
    cur.execute("CREATE INDEX ON _k (sf, sb)")
    cur.execute("ANALYZE _k")
    hit = set()
    for t in tabs:
        cur.execute(f"""SELECT k.sf, k.sb, k.tf, k.tb FROM _k k JOIN {t} c
                          ON c.source_filename = k.sf AND c.source_start_byte = k.sb
                         AND c.target_filename = k.tf AND c.target_start_byte = k.tb""")
        hit.update(cur.fetchall())
    cur.execute("DROP TABLE _k")
    return len(hit)

# 10 Oct 2026: the two Gallica runs were filtered BEFORE run_filter_pipeline.py existed, by
# filter_banality.py (modern_gallica: alignments_clean.jsonl -> clean2) and
# filter_banality_gallica.py (gallica: clean2 -> clean3), both with a cap of 20, not 30.
# A run may be given as DIR::BEFORE::CAP::FINAL to read such a layout.
GALLICA = ["/path/to/alignements/modern_gallica/output::alignments_clean.jsonl::20::alignments_clean4.jsonl",
           "/path/to/alignements/gallica/output::alignments_clean2.jsonl::20::alignments_clean5.jsonl"]
if a.gallica: a.run = (a.run or []) + GALLICA
BANDS = [(20, 29), (30, 49), (50, 99), (100, 499), (500, 10**9)]
def is_phi(f): return "modern_phi" in os.path.basename(str(f or ""))
for spec in (a.run or RUNS):
    parts = spec.split("::")
    run = parts[0]
    c1 = os.path.join(run, parts[1] if len(parts) > 1 else "alignments_clean1.jsonl")
    cap = int(parts[2]) if len(parts) > 2 else a.cap
    print(f"\n{'=' * 100}\nRUN {run}   (before-banality file {os.path.basename(c1)}, cap {cap})")
    if not os.path.exists(c1):
        print(f"  no {os.path.basename(c1)} -- skipped (for a pre-pipeline run give DIR::BEFORE::CAP::FINAL, or --gallica)"); continue
    if len(parts) > 3:
        final = os.path.join(run, parts[3]); final = final if os.path.exists(final) else None
    else:
        final = next((os.path.join(run, f"alignments_clean{i}.jsonl") for i in (6, 5, 4, 3, 2)
                      if os.path.exists(os.path.join(run, f"alignments_clean{i}.jsonl"))), None)
    log(f"{run}: pass 1, counting clean1 groups")
    gcount = Counter()
    with open(c1, "rb") as fh:
        for line in fh:
            try: gcount[json.loads(line).get("group_id", 0)] += 1
            except Exception: continue
    removed = {g for g, n in gcount.items() if n >= cap}
    log(f"  {len(gcount):,} groups, {len(removed):,} removed; pass 2, collecting their records")
    keys, recs_by_g, phikeys = [], defaultdict(list), []
    pick = set(random.sample(sorted(removed), min(a.sample, len(removed)))) if removed else set()
    with open(c1, "rb") as fh:
        for line in fh:
            try: rec = json.loads(line)
            except Exception: continue
            g = rec.get("group_id", 0)
            if g in removed:
                keys.append(nk(rec))
                if is_phi(rec.get("source_filename")) or is_phi(rec.get("target_filename")):
                    phikeys.append(nk(rec))
                if g in pick: recs_by_g[g].append(rec)
    nrem = len(keys)
    print(f"  A. clean1: {sum(gcount.values()):,} records in {len(gcount):,} groups")
    print(f"     step 2 removed {len(removed):,} group(s) holding {nrem:,} record(s) "
          f"({100 * nrem / max(1, sum(gcount.values())):.1f}% of clean1)")
    for lo, hi in BANDS:
        gs = [g for g in removed if lo <= gcount[g] <= hi]
        print(f"       groups of {lo:>3}-{hi if hi < 10**9 else '':<4} {len(gs):>8,} group(s) {sum(gcount[g] for g in gs):>10,} record(s)")
    log("  presence of the removed records in the seven tables")
    f_rem = found(keys)
    print(f"  B. removed records found in a table today: {f_rem:,} of {nrem:,}  -> ABSENT: {nrem - f_rem:,}")
    f_phi = found(phikeys)
    print(f"     of them with a PHI text on one side: {len(phikeys):,}; found {f_phi:,}  -> ABSENT: {len(phikeys) - f_phi:,}")
    if final:
        sample = []
        with open(final, "rb") as fh:
            for i, line in enumerate(fh):
                if len(sample) < a.calib: sample.append(line)
                else:
                    j = random.randint(0, i)
                    if j < a.calib: sample[j] = line
        ck = [nk(json.loads(l)) for l in sample]
        f_c = found(ck)
        print(f"     calibration: {f_c:,} of {len(ck):,} survivors of {os.path.basename(final)} found "
              f"({100 * f_c / max(1, len(ck)):.1f}%) -- set-aside rows count as found")
    print(f"  C. {len(pick)} removed group(s) at random, for reading:")
    for g in sorted(pick, key=lambda x: -gcount[x]):
        rs = recs_by_g[g]
        pair = Counter((r.get("source_author"), r.get("source_title"), r.get("target_title")) for r in rs).most_common(1)[0]
        docs = len({r.get("source_filename") for r in rs} | {r.get("target_filename") for r in rs})
        p = " ".join((rs[0].get("source_passage") or "").split())
        print(f"\n   group {g}: {gcount[g]} records, {docs} documents; commonest pair x{pair[1]}: "
              f"{str(pair[0][0])[:28]} | {str(pair[0][1])[:40]} -> {str(pair[0][2])[:40]}")
        print(f"      {p[:260]}")
print("\nRead-only. Nothing written.")
