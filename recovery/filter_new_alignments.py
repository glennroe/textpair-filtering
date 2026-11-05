#!/usr/bin/env python3
"""
agent/filter_new_alignments.py -- READ-ONLY on the database (it only loads ngram_df).
Apply the corpus's later noise gates to a NEW alignment file, so new alignments
(e.g. Dacier's Iliade tomes 2-3 against modern_all_pruned / gallica_mono) arrive
filtered to the same standard combined_align was brought to in Aug-Sep 2026.

RUN run_filter_pipeline.py ON THE RESULTS DIRECTORY FIRST (steps 1-4: phrases,
banality, theatre, excluded filenames); this script takes its output,
alignments_clean6.jsonl (the pipeline now has six steps, through clean6), and adds the three gates that were run later as DB sweeps:

  DEGENERATE   both sides OCR rubble        containment.is_degenerate (windowed, 19 Aug fix)
  BOILERPLATE  both sides boilerplate       boilerplate_patterns.classify (density floor 6.5, 21 Aug)
  CLASSIFIER   p(noise) >= model threshold  noise_model.pkl over noise_features.featurise
               spared: Latin on either side (latin_detect >= 0.70), the literary
               corpora of SPARE_CORPUS_PATHS -- exactly apply_noise_classifier.py's guards.
  ONE-SIDE     boilerplate or degenerate on one side only: KEPT, flagged for reading.

Writes into the results directory:
  alignments_gated.jsonl           kept rows
  alignments_gated_rejected.jsonl  rejected rows, each with "_reason" and "_p_noise"
  gated_review.txt                 counts, and samples of every reason for reading
(names chosen so as never to collide with the pipeline's own alignments_cleanN files)
Usage (from cleaned/):
  python3 agent/filter_new_alignments.py <results_dir> [--in alignments_clean6.jsonl]
"""
import argparse, configparser, json, os, pickle, random, sys, time
import numpy as np, psycopg2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boilerplate_patterns as BP, containment as CT, noise_features as NF, latin_detect as LD

ap = argparse.ArgumentParser()
ap.add_argument("results_dir")
ap.add_argument("--in", dest="inp", default="alignments_clean6.jsonl")
ap.add_argument("--model", default="noise_model.pkl")
ap.add_argument("--latin-threshold", type=float, default=0.70)
ap.add_argument("--sample", type=int, default=25)
ap.add_argument("--long", type=int, default=10000, help="passages longer than this are kept unscored")
a = ap.parse_args()
LONG = a.long
SPARE = ("frantext18", "theatre18", "cphil", "modern_letters")
log = lambda m: print(time.strftime("%H:%M:%S"), m, flush=True)

M = pickle.load(open(a.model, "rb")); THR = M["threshold"]
if list(M["features"]) != list(NF.FEATURES): sys.exit("model / noise_features order mismatch: retrain")
cfg = configparser.ConfigParser(); cfg.read("/etc/text-pair/global_settings.ini")
conn = psycopg2.connect(user=cfg["DATABASE"]["database_user"], password=cfg["DATABASE"]["database_password"],
                        database=cfg["DATABASE"]["database_name"]); conn.set_session(readonly=True)
log("loading ngram_df ..."); DF = {}
sc = conn.cursor(name="df"); sc.itersize = 500000; sc.execute("SELECT ngram, df FROM ngram_df")
while True:
    b = sc.fetchmany(500000)
    if not b: break
    DF.update(b)
log(f"  {len(DF):,} n-grams; classifier threshold {THR:.4f}")

path = os.path.join(a.results_dir, a.inp)
keep = open(os.path.join(a.results_dir, "alignments_gated.jsonl"), "w", encoding="utf-8")
rej = open(os.path.join(a.results_dir, "alignments_gated_rejected.jsonl"), "w", encoding="utf-8")
stats, samples = {}, {}
def note(k, r):
    stats[k] = stats.get(k, 0) + 1
    s = samples.setdefault(k, [])
    if len(s) < a.sample: s.append(r)
    elif random.random() < a.sample / stats[k]: s[random.randrange(a.sample)] = r
n = 0
for line in open(path, encoding="utf-8"):
    r = json.loads(line); n += 1
    s, t = r.get("source_passage") or "", r.get("target_passage") or ""
    r["_len"] = max(len(s), len(t))
    reason = None
    if max(len(s), len(t)) > LONG:
        # boilerplate_patterns declines these outright as document-level reuse (NEVER_CLASSIFY_ABOVE),
        # and the classifier's containment features are quadratic in length: keep, flag, do not score.
        note(f"kept, long (> {LONG:,} chars): not classified (read)", r)
        keep.write(json.dumps(r, ensure_ascii=False) + "\n"); note("KEPT", r)
        if n % 50 == 0: log(f"  {n:,} rows")
        continue
    dg = [CT.is_degenerate(CT.fold(x)) for x in (s, t)]
    bp = [BP.classify(x) for x in (s, t)]
    if all(dg): reason = "DEGENERATE"
    elif all(bp): reason = "BOILERPLATE"
    else:
        v = NF.featurise(s, t, DF)
        p = float(M["model"].predict_proba(np.array([v], dtype=np.float32))[0, 1]) if v is not None else 0.0
        r["_p_noise"] = round(p, 4)
        if p >= THR:
            paths = str(r.get("source_filename", "")) + str(r.get("target_filename", ""))
            if any(q in paths for q in SPARE): note("spared: literary corpus", r)
            elif max(LD.latin_score(s)[0], LD.latin_score(t)[0]) >= a.latin_threshold: note("spared: Latin", r)
            else: reason = "CLASSIFIER"
    if reason:
        r["_reason"] = reason; rej.write(json.dumps(r, ensure_ascii=False) + "\n"); note(reason, r)
    else:
        if any(dg) or any(bp): note("kept, one side degenerate/boilerplate (read)", r)
        keep.write(json.dumps(r, ensure_ascii=False) + "\n"); note("KEPT", r)
    if n % 50 == 0: log(f"  {n:,} rows")
keep.close(); rej.close(); conn.close()
with open(os.path.join(a.results_dir, "gated_review.txt"), "w", encoding="utf-8") as fh:
    fh.write(f"{path}: {n:,} rows in\n")
    for k, v in sorted(stats.items(), key=lambda x: -x[1]): fh.write(f"  {k:<48} {v:>9,}  ({100*v/max(n,1):.1f}%)\n")
    for k, rs in samples.items():
        if k == "KEPT": continue
        fh.write(f"\n{'='*78}\n{k}  ({stats[k]:,}; {len(rs)} sampled)\n{'='*78}\n")
        for r in rs:
            fh.write(f"\n p={r.get('_p_noise','-')}  {r.get('source_filename','').split('/')[-1]} -> {r.get('target_filename','').split('/')[-1]}\n")
            fh.write(f"   S: {' '.join(str(r.get('source_passage','')).split())[:300]}\n")
            fh.write(f"   T: {' '.join(str(r.get('target_passage','')).split())[:300]}\n")
log(f"done: {n:,} in; " + ", ".join(f"{k} {v:,}" for k, v in stats.items()))
