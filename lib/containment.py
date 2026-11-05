#!/usr/bin/env python3
"""
containment.py
Shared module: trigram windowed containment, and the orthographic folding
that early modern Latin needs before any of it means anything.

WHY A MODULE
------------
Windowed containment now exists in three places -- seed_attributions.py,
cluster_orphan_latin.py and this file -- and the project's own rule is that
shared logic lives in a module because scripts do the work at import time
and cannot be imported. The two older copies are unchanged and still
correct; they should be migrated to this module when either is next
touched, rather than being refactored underneath committed results.

WHY CONTAINMENT AND NOT JACCARD
-------------------------------
Quotations differ in LENGTH. One journal prints the whole hexameter, the
next half of it, a third runs two lines together. Jaccard divides by the
union and so punishes that asymmetry: a 44-character verse inside its own
579-character native passage scores 0.08 and is missed at any threshold.
Containment divides by the shorter side and scores the same pair 0.97.

WHY *WINDOWED* CONTAINMENT
--------------------------
Plain set containment records presence and not position, so a 40-trigram
Latin seed is "contained" in any sufficiently long passage by accident.
Run 1 of seed_attributions.py returned ~146,000 hits across 15 seeds on
that basis. Requiring the shared trigrams to fall inside a single window of
len(short) * 1.4 + 12 dropped 146,151 pairs and kept 262, while the count
of true native candidates went UP from 17 to 24. Scatter is penalised;
length never is.

THE FOLDING, AND WHY IT IS THE POINT
------------------------------------
latin_detect.normalise() unescapes entities and collapses whitespace, and
does nothing else. That was sufficient for clustering WITNESSES against
each other, because witnesses printed in the same decades share OCR
conventions. It is not sufficient for matching a witness against the PHI
native text, which is the comparison the orphan-Latin work now needs, and
it is the comparison TextPAIR itself never made:

    juftitiam / iustitiam      long s read as f
    Divos     / diuos          u and v undifferentiated
    coelum    / caelum         ae/oe/e variation
    Aeneis    / ÆNEIS          ligature and case

fold() folds case, accents, ligatures, i/j, u/v and punctuation. Those are
safe: they collapse pairs that are genuinely the same letter in the period
orthography, and no Latin word is distinguished from another by them.

LONG S IS NOT IN THAT SET, BY DEFAULT
-------------------------------------
Mapping f -> s would fold `facit` to `sacit` and `fides` to `sides`, and
manufacture matches between unrelated words. It is available as
fold(s, fs=True) for a targeted pass over material known to be long-s
damaged, and should never be the default. The asymmetry is the usual one
in this project: a missed match leaves work on a queue, a false match
writes a wrong attribution.
"""

import re
import html
import unicodedata
from collections import defaultdict

WINDOW_SLACK = 1.4
WINDOW_PAD = 12

# Distinct trigrams divided by folded length. Below this a passage is
# repetition rather than text -- see is_degenerate().
MIN_DISTINCTNESS = 0.45

# The floor is applied to the BEST WINDOW of this many characters rather than
# to the whole string. See is_degenerate() for the measurement; in short, the
# plain ratio has a length bias that condemned ordinary prose over about a page.
DEGENERACY_WINDOW = 200

# Stamp it, so a report can say which rule produced it. The 18 Aug density
# guard was reverted twice by rsync and nothing in the output said so.
DEGENERACY_RULE = f"windowed-{DEGENERACY_WINDOW} (2026-08-19)"

_PUNCT = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")

# Ligatures and the two letter-pairs the period does not distinguish.
_LIGATURES = {"æ": "ae", "Æ": "ae", "œ": "oe", "Œ": "oe", "ﬁ": "fi", "ﬂ": "fl"}


def fold(s, fs=False):
    """Case, accents, ligatures, i/j, u/v, punctuation. Optionally f -> s.

    The result is for MATCHING only and is not readable text; never store
    it, never display it, never write it back to the database."""
    if not s:
        return ""
    # HTML entities are IN the corpus text, undecoded. '&amp;' is the common
    # one and in eighteenth-century French most passages carry an ampersand,
    # so folding it as literal characters contributes '&am', 'amp', 'mp;',
    # ' &a' and 'p; ' to nearly everything and inflates containment across the
    # board. Measured 17 Aug: two false Montesquieu candidates fell from 0.64
    # and 0.62 to 0.58 and 0.55 once decoded, i.e. from above a 0.60 threshold
    # to below it. latin_detect.normalise() has always unescaped; fold() never
    # did, and fold() is what every native search uses.
    if "&" in s:
        s = html.unescape(s)
    for k, v in _LIGATURES.items():
        s = s.replace(k, v)
    # Strip diacritics: early modern printing is inconsistent about them and
    # OCR more so. NFD then drop the combining marks.
    s = "".join(c for c in unicodedata.normalize("NFD", s)
                if not unicodedata.combining(c))
    s = s.lower()
    s = s.replace("ſ", "s")          # the actual long-s character, unambiguous
    s = s.replace("j", "i").replace("v", "u")
    if fs:
        s = s.replace("f", "s")      # see the docstring; off by default
    s = _PUNCT.sub(" ", s)
    return _WS.sub(" ", s).strip()


def trigrams(s):
    if len(s) < 3:
        return frozenset()
    return frozenset(s[i:i + 3] for i in range(len(s) - 2))


def distinctness(folded, tris=None):
    """Distinct trigrams over folded length. Normal text runs 0.65-0.97."""
    if not folded:
        return 0.0
    t = tris if tris is not None else trigrams(folded)
    return len(t) / len(folded)


def windowed_distinctness(folded, window=DEGENERACY_WINDOW, tris=None):
    """Best distinctness over any window of `window` characters.

    Repetition is a LOCAL property: a declension table or an OCR stutter is
    dense in every window, so its best window is as poor as its whole. Genuine
    prose has at least one dense stretch however long it runs. Taking the
    maximum therefore keeps the diagnostic and drops the length bias.
    """
    if len(folded) <= window:
        return distinctness(folded, tris)
    step = max(window // 2, 1)
    best = 0.0
    for i in range(0, len(folded) - window + 1, step):
        d = distinctness(folded[i:i + window])
        if d > best:
            best = d
    tail = distinctness(folded[-window:])      # the loop can miss the end
    return max(best, tail)


def is_degenerate(folded, tris=None, floor=MIN_DISTINCTNESS,
                  window=DEGENERACY_WINDOW):
    """True for a passage that is repetition rather than text.

    THE LENGTH BIAS, FOUND 19 AUG 2026, AND WHY THIS IS NOW WINDOWED
    ----------------------------------------------------------------
    Until 19 Aug this divided distinct trigrams by the length of the WHOLE
    string. Distinct trigrams saturate -- French has a bounded trigram
    inventory -- while length does not, so the ratio falls with length for
    reasons that have nothing to do with repetition. Measured on corpus prose:

           100 chars  0.93        1600 chars  0.36  <-- condemned
           400 chars  0.68        2500 chars  0.24  <-- condemned
          1200 chars  0.46        3000 chars  0.20  <-- condemned

    Ordinary prose crosses the 0.45 floor at roughly 1,300 characters, so every
    passage longer than about a page was called repetition. With
    skip_degenerate=True that returns a zero score, and the zero is
    indistinguishable from 'these passages share nothing'.

    IT COST A WHOLE RESULT. group_conflation_rate.py scored 3,019 bridging
    rows, one passage against one passage, and reported that 3,018 of them --
    100% -- shared nothing with their own alignment partner. The first example
    it printed was:

        ait remis generalement tout ce qui estoit du par les particuliers
        ait remis generalement tout cequi etoit du par les particuliers

    scored at 0.00. Two identical long passages score 1.00 with the gate off
    and 0.00 with it on; that is the whole of the finding.

    THE ERROR IS ONE-SIDED. This gate can only destroy a match, never invent
    one, so nothing merged on its evidence is in doubt. What is in doubt is
    every decision NOT to act: candidates not found, components held, document
    pairs called disjoint.

    WHAT IT STILL CATCHES. Both cases the rule was built from, described
    below, are dense in every window and stay flagged, and 3,000 characters of
    genuine repetition still scores 0.05. Only the length artefact is gone:
    3,000 characters of real prose recovers from 0.38 to 0.91.

    Set containment is blind to repetition: it compares SETS, so a 94-
    character string built from six repeated words carries the trigram set of
    a very short one and is 'contained' in almost anything. Two real cases
    from the corpus, both of which outranked the true native on 17 Aug:

        'Mien, du Mien, au Mien, le Mien, du Mien, la de la a la la Mienne.'
            -- Restaut's grammar, a declension table.  94 chars, 29 trigrams.
        'Mets De Mets a De Mets a De Mets a De Mets a De Mets a De. Mets a'
            -- OCR stutter.                            82 chars, 15 trigrams.

    Their distinctness is 0.31 and 0.18. Every genuine passage tested --
    French verse, French prose, Latin verse, the Vulgate -- ran 0.66 to 0.97,
    so the floor separates the class cleanly and is not a near thing.

    This does NOT catch a short scrap of ordinary function words, which is a
    different failure with the same symptom: 'mots, moins, mieux, plus mal,
    moins mal' scores 0.66 and is indistinguishable by shape from a real
    quotation. Nothing computed from the passage alone will separate that --
    only the RARITY of the shared trigrams would, which means corpus
    frequencies. The practical guard there is the threshold: French verse is
    copied exactly and true natives score 0.84-1.00, while those scraps top
    out around 0.76.
    """
    return windowed_distinctness(folded, window, tris) < floor


def windowed_containment(short, long_, short_tris):
    """Largest number of distinct short-trigrams inside any one window of
    long_, over len(short_tris).

    Identical in behaviour to the implementations in seed_attributions.py
    and cluster_orphan_latin.py; kept bit-for-bit so results stay
    comparable across the three."""
    if not short_tris:
        return 0.0
    window = int(len(short) * WINDOW_SLACK) + WINDOW_PAD
    pos = [(i, long_[i:i + 3]) for i in range(len(long_) - 2)
           if long_[i:i + 3] in short_tris]
    if not pos:
        return 0.0
    counts = defaultdict(int)
    distinct = best = lo = 0
    for hi in range(len(pos)):
        p, t = pos[hi]
        counts[t] += 1
        if counts[t] == 1:
            distinct += 1
        while pos[lo][0] < p - window:
            t0 = pos[lo][1]
            counts[t0] -= 1
            if counts[t0] == 0:
                distinct -= 1
            lo += 1
        if distinct > best:
            best = distinct
    return best / len(short_tris)


def score_pair(a, b, tris_a=None, tris_b=None, min_cont=None,
               skip_degenerate=False):
    """Symmetric score for two folded strings.

    skip_degenerate is OPT-IN and defaults False. It returns a zero score for
    a pair where either side is repetition rather than text (is_degenerate).
    It is off by default deliberately: score_pair underlies results already
    committed, and silently changing what it returns would refactor the
    project underneath them. New callers should pass True; older ones should
    be switched only when they are next re-run in full.

    Returns (wcont, setcont, jaccard, direction) where direction is
    'CAND<SEED' when b is the longer side and 'SEED<CAND' when a is.
    The denominator is always the SHORTER side -- Glenn's question, 15 Aug:
    scoring one direction only finds a native beneath a quotation but is
    blind to a shorter excerpt of a seed.

    min_cont is a PREFILTER and not a threshold: windowed containment counts
    a subset of the trigrams plain set containment counts, so it can never
    exceed it. A set score below min_cont is therefore a proof that the
    windowed score is below it too, and the windowed pass -- which is linear
    in the length of the longer string -- can be skipped outright. Without
    it, 2,230 overrides against 18,788 native passages is several billion
    character operations; with it, almost every pair dies on a set
    intersection. The returned wcont is 0.0 in that case, which is a lower
    bound and not a measurement; callers must not report it as a score.
    """
    ta = tris_a if tris_a is not None else trigrams(a)
    tb = tris_b if tris_b is not None else trigrams(b)
    if not ta or not tb:
        return 0.0, 0.0, 0.0, "CAND<SEED"
    if skip_degenerate and (is_degenerate(a, ta) or is_degenerate(b, tb)):
        return 0.0, 0.0, 0.0, "CAND<SEED" if len(a) <= len(b) else "SEED<CAND"
    inter = len(ta & tb)
    union = len(ta | tb)
    setcont = inter / min(len(ta), len(tb))
    jac = inter / union if union else 0.0
    if min_cont is not None and setcont < min_cont:
        return 0.0, setcont, jac, "CAND<SEED" if len(a) <= len(b) else "SEED<CAND"
    if len(a) <= len(b):
        wc = windowed_containment(a, b, ta)
        direction = "CAND<SEED"
    else:
        wc = windowed_containment(b, a, tb)
        direction = "SEED<CAND"
    return wc, setcont, jac, direction
