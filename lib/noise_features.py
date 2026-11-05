#!/usr/bin/env python3
"""
noise_features.py
One place that knows how a row becomes a feature vector. Import it; do not
re-derive it.

WHY THIS IS A MODULE
--------------------
`train_noise_classifier.py` builds the vector and `apply_noise_classifier.py`
must build the IDENTICAL vector, in the identical order, or every score is
silently wrong — not an error, a wrong number. On 19 Aug the two were written
separately and the order matched only by luck; a single element inserted in
one and not the other would have produced a model that scores confidently and
means nothing.

This is the same argument that produced `corpus_source.py`, `locus_test.py`
and `protection.py`. A fact that must be remembered in two places is a fact
that will be forgotten in one.

WHAT EACH FEATURE IS, AND WHERE IT CAME FROM
---------------------------------------------
Every one is computed by a module already in the project, so a condemnation
can be explained in terms the rest of the code already uses.

  locus_test      run, setcont, wcont — the coherence verdict's two limbs,
                  separately. MEASURED 19 Aug: these contribute almost
                  NOTHING to detecting boilerplate (importances 0.0008,
                  0.0010, 0.0021), and that is not a defect. Boilerplate is
                  VALIDLY ALIGNED — good run, good containment, exactly like
                  real reuse — because the alignment is correct and only the
                  significance is not. Kept because they cost nothing and
                  they separate the OTHER noise category, bad alignments.

  containment     dist_min, dist_max — windowed distinctness, the OCR signal.

  ngram_df        mindf, meddf, frac_common, n_shared, no_shared_run.
                  meddf is the SECOND strongest feature (0.0351). Note the
                  reversal this represents: on 21 Aug document frequency was
                  rejected for condemnation because Genesis 1:1 sits at
                  df=790. That killed df as a univariate threshold and did
                  not kill it as one feature among twenty-three.

                  no_shared_run is NaN-coded rather than zero-coded, because
                  "the two sides share no 4-word run" is a distinct state and
                  not an extreme number. HistGradientBoosting handles NaN
                  natively as its own branch.

  boilerplate     bp_density is the STRONGEST feature by four times (0.1357).
                  The library reaches 8.3% recall as a RULE and carries a 92%
                  model as a continuous FEATURE. The patterns were never the
                  weak part; the threshold was — requiring a hit plus density
                  >= 6.5 discarded most of what those 315 regexes know.

  shape           lengths, ratio, digit and capital fractions, token
                  diversity, mean token length. upper_frac ranks third
                  (0.0291): chancery styles, titles and headings are
                  capital-heavy.

                  tok_div_min is here as a FEATURE having been rejected as a
                  RULE on 21 Aug for a length bias. As a feature the model
                  conditions it on len_min, which is what the rule could not
                  do.

ORDER IS THE CONTRACT. Append only; never insert, never reorder. A model
pickled against one order and scored against another produces confident
nonsense.
"""

import math

import containment as CT
import locus_test as LT
import boilerplate_patterns as BP

NGRAM = 4

FEATURES = [
    "run", "setcont", "wcont",
    "dist_min", "dist_max",
    "mindf", "meddf", "frac_common", "n_shared", "no_shared_run",
    "bp_hits_s", "bp_hits_t", "bp_matches", "bp_density", "bp_never",
    "bp_garbage", "bp_spared_long",
    "len_min", "len_ratio", "digit_frac", "upper_frac",
    "tok_div_min", "mean_tok_len",
]

# The five the 19 Aug importances put on top, for reporting a verdict.
TOP_FEATURES = ["bp_density", "meddf", "upper_frac", "len_min", "frac_common"]


def grams(folded, n=NGRAM):
    w = folded.split()
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)} \
        if len(w) >= n else set()


def featurise(s, t, df):
    """Feature vector for one alignment row. `df` maps n-gram -> document
    frequency; a MISS means df < the table's floor, which is the strongest
    rarity signal available and is scored as 1, never as unknown.

    Returns None when either side folds away to nothing."""
    fs, ft = CT.fold(s or ""), CT.fold(t or "")
    if not fs or not ft:
        return None

    run, setc, wc, _dead = LT.compare([s], [t])
    ds = CT.windowed_distinctness(fs)
    dt = CT.windowed_distinctness(ft)

    sh = grams(fs) & grams(ft)
    if sh:
        dfs = sorted(df.get(g, 1) for g in sh)
        mindf = float(dfs[0])
        meddf = float(dfs[len(dfs) // 2])
        frac_common = sum(1 for d in dfs if d >= 100) / len(dfs)
    else:
        mindf = meddf = frac_common = math.nan

    ins, int_ = BP.inspect(s), BP.inspect(t)
    ts, tt = fs.split(), ft.split()
    raw = (s or "") + (t or "")

    return [
        float(run), float(setc), float(wc),
        min(ds, dt), max(ds, dt),
        mindf, meddf, frac_common, float(len(sh)), float(not sh),
        float(len(ins["hits"])), float(len(int_["hits"])),
        float(ins["matches"] + int_["matches"]),
        float(max(ins["density"], int_["density"])),
        float(ins["never"] or int_["never"]),
        float(ins["category"] == "OCR garbage"
              or int_["category"] == "OCR garbage"),
        float(ins["spared_long"] or int_["spared_long"]),
        float(min(len(fs), len(ft))),
        min(len(fs), len(ft)) / max(len(fs), len(ft), 1),
        sum(c.isdigit() for c in raw) / max(len(raw), 1),
        sum(c.isupper() for c in raw) / max(len(raw), 1),
        min(len(set(ts)) / max(len(ts), 1), len(set(tt)) / max(len(tt), 1)),
        sum(len(w) for w in ts) / max(len(ts), 1),
    ]


def check(vec):
    """Assert the vector matches the declared contract. Cheap, and it turns a
    silent wrong number into a loud failure."""
    if vec is None:
        return
    if len(vec) != len(FEATURES):
        raise AssertionError(
            f"featurise() returned {len(vec)} values against "
            f"{len(FEATURES)} declared in FEATURES. Order is the contract "
            f"between the trainer and the applier; a mismatch scores "
            f"confidently and means nothing.")


if __name__ == "__main__":
    print(f"{len(FEATURES)} features:")
    for i, f in enumerate(FEATURES):
        print(f"  {i:>2}  {f}")
    print("\nself-test on three registers ...")
    DF = {"de la meme maniere": 4000, "rien n est beau": 4}
    for lbl, a, b in (
            ("boilerplate",
             "Par grace et privilege du Roy donne a Paris le douziesme jour",
             "Par grace & privilege du Roi, donne a Paris le douzieme jour"),
            ("reuse",
             "Rien n'est beau que le vrai, le vrai seul est aimable",
             "et rien n'est beau que le vrai dans la fable"),
            ("rubble", "cc cc cc cc cc C( cc", "CC cc cc cc cc cc")):
        v = featurise(a, b, DF)
        check(v)
        d = dict(zip(FEATURES, v))
        print(f"  {lbl:<12} " + "  ".join(
            f"{k}={'--' if isinstance(d[k], float) and math.isnan(d[k]) else format(d[k], '.2f')}"
            for k in TOP_FEATURES))
    print("\ncontract holds: every vector has "
          f"{len(FEATURES)} elements in the declared order")
