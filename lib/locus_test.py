#!/usr/bin/env python3
"""
locus_test.py
One place that knows what "these two documents share a locus" means.

WHY THIS IS A MODULE
--------------------
check_merged_coherence.py asks it of merged canonicals and
group_conflation_rate.py asks it of arbitrary groups, and the answer has to be
the SAME answer or the comparison between them is meaningless -- the entire
point of the base-rate measurement is that merged and unmerged groups are
judged identically. Two copies of the verdict is how the native_status
vocabulary came to disagree with itself.

THE VERDICT, AND WHY IT TAKES EITHER TEST
------------------------------------------
Two documents inside one group cohere when some passage of one shares either

    a RUN of MIN_RUN consecutive words with some passage of the other, or
    MERGE_CONTAINMENT set containment against it

Each test is blind where the other sees.

  THE RUN alone condemns OCR. Gazette_litteraire_de_l_Europe_1766_15_610
  scores 0.93 containment against a 1770 witness of the same passage and
  shares no run of four words, because OCR corrupts about one word in four.
  Sixty-five of 196 failing pairs looked like that on 19 Aug.

  CONTAINMENT alone condemns unequal spans. Two witnesses clipping different
  lengths of one native share six consecutive words and score 0.35. Thirty-one
  pairs on the same run.

Glenn's rule, 19 Aug: "we can only merge passages into groups if all the
passages share at least some information, i.e., there is some textual overlap
- even just a few words, but something". Either test is evidence of that
overlap; only a pair failing BOTH is evidence of a fusion.

WHAT IT CANNOT DO
-----------------
It asks whether two passages share material. It cannot say where the locus
ENDS, so a native long enough to cover two verses passes every pair that
touches it. That needs a reference edition.
"""

from containment import score_pair, fold, trigrams, is_degenerate

MIN_RUN = 4
MERGE_CONTAINMENT = 0.80
MAX_PASSAGES = 40

# LONGEST RUN IS CAPPED. The verdict only asks whether a run reaches MIN_RUN;
# the exact length is reporting sugar. Escalating one word at a time rebuilds
# two shingle sets per step, so an unbounded search on a 46-word match did 43
# rebuilds -- per passage PAIR. Stopping at 12 keeps the number informative
# and bounds the cost.
MAX_RUN_REPORTED = 12

_CACHE = {}


def keyed(t, min_run=MIN_RUN):
    """(folded, trigrams, word list, shingle set, degenerate) for a passage.

    THE DEGENERACY FLAG IS CACHED HERE, and that is the whole point. Since
    19 Aug is_degenerate has been WINDOWED -- it slices the string every 100
    characters and builds trigrams for each window -- which is right but no
    longer cheap. Calling it inside the pair loop re-derived it once per
    comparison instead of once per passage, and on 20 Aug that stalled
    campaign_find_natives.py for over an hour at 80 of 98 seeds.

    A passage's degeneracy is a property of the passage. It is computed once.
    """
    k = (t, min_run)
    v = _CACHE.get(k)
    if v is None:
        f = fold(t)
        tr = trigrams(f)
        w = f.split()
        sh = ({" ".join(w[i:i + min_run]) for i in range(len(w) - min_run + 1)}
              if len(w) >= min_run else frozenset())
        v = _CACHE[k] = (f, tr, w, sh, is_degenerate(f, tr))
    return v


def longest_run(wa, wb, min_run=MIN_RUN):
    """Longest run of consecutive words common to two word lists.

    Escalates the shingle width from min_run upward and stops at the first
    width with no intersection. Only called on a pair already known to share
    min_run words, so the loop almost always runs a handful of times."""
    n, best = min_run, 0
    top = min(len(wa), len(wb), MAX_RUN_REPORTED)
    while n <= top:
        sa = {" ".join(wa[i:i + n]) for i in range(len(wa) - n + 1)}
        sb = {" ".join(wb[i:i + n]) for i in range(len(wb) - n + 1)}
        if not (sa & sb):
            break
        best = n
        n += 1
    return best


def sample(xs, max_passages=MAX_PASSAGES):
    """Longest passages first. A long passage carries more of the locus, and
    arbitrary database order is not a sample."""
    return sorted(xs, key=len, reverse=True)[:max_passages]


def compare(xs, ys, min_run=MIN_RUN, merge_containment=MERGE_CONTAINMENT,
            max_passages=MAX_PASSAGES):
    """Best evidence of shared material between two documents' passages.

    Returns (longest_run, best_setcont, best_wcont, degenerate_only).

    setcont is computed exactly by score_pair in every branch and is safe to
    report. wcont is a LOWER BOUND wherever the min_cont prefilter fired --
    containment.py: "callers must not report it as a score" -- so it is
    carried separately and is meaningful only when positive."""
    run = 0
    sc_best = wc_best = 0.0
    live = False
    # KEY EVERY PASSAGE ONCE, drop the degenerate ones once, then loop. The
    # inner loop must contain no work that depends on one side alone.
    A = [k for k in (keyed(x, min_run) for x in sample(xs, max_passages))
         if not k[4]]
    B = [k for k in (keyed(y, min_run) for y in sample(ys, max_passages))
         if not k[4]]
    if not A or not B:
        return 0, 0.0, 0.0, True
    live = True
    for xf, xt, xw, xsh, _ in A:
        for yf, yt, yw, ysh, _ in B:
            if xsh & ysh and run < MAX_RUN_REPORTED:
                r = longest_run(xw, yw, min_run)
                if r > run:
                    run = r
            try:
                w, sc, _jac, _d = score_pair(
                    xf, yf, tris_a=xt, tris_b=yt,
                    min_cont=merge_containment, skip_degenerate=False)
            except Exception:
                continue
            if sc > sc_best:
                sc_best = sc
            if w > wc_best:
                wc_best = w
    return run, sc_best, wc_best, (not live)


def coherent(v, min_run=MIN_RUN, merge_containment=MERGE_CONTAINMENT):
    """EITHER test suffices. Requiring both would condemn every OCR'd witness
    in the corpus; requiring only the run does exactly that."""
    run, sc, _wc, _dead = v
    return run >= min_run or sc >= merge_containment


def matrix(docs, keys, **kw):
    """Every pair of the named documents, scored."""
    m = {}
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            m[(a, b)] = compare(docs[a], docs[b], **kw)
    return m


def verdict(m, min_run=MIN_RUN, merge_containment=MERGE_CONTAINMENT):
    """(bad pairs, total pairs). Empty bad list means the group is one locus
    as far as this test can tell."""
    bad = [k for k, v in m.items()
           if not coherent(v, min_run, merge_containment)]
    return bad, len(m)
