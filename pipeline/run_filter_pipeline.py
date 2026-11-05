#!/usr/bin/env python3
"""
run_filter_pipeline.py
Unified 4-step filter pipeline for any TextPAIR alignment corpus.

Usage:
    python3 run_filter_pipeline.py <results_dir>

    <results_dir> must contain alignments.jsonl.lz4

Output files written to <results_dir>:
    alignments_clean1.jsonl              after step 1 (phrase/position/short/OCR)
    alignments_clean1_rejected_sample.jsonl
    alignments_clean2.jsonl              after step 2 (group banality)
    alignments_clean2_rejected_sample.jsonl
    alignments_clean3.jsonl              after step 3 (theatre markers)
    alignments_clean3_rejected_sample.jsonl
    alignments_clean4.jsonl              after step 4 (excluded filenames)
    alignments_clean4_rejected_sample.jsonl
    filter_report.txt                    summary across all steps
"""

import sys, os, json, re, random, time, argparse
from collections import Counter

# ── Global resources ──────────────────────────────────────────────────────────
PHRASE_FILE  = "/path/to/alignements/modern_gallica/filter_new_phrases_cleaned.txt"
EXCL_FILE    = "/path/to/alignements/excluded_filenames.json"

# ── Defaults ──────────────────────────────────────────────────────────────────
POS_HIGH       = 90.0
POS_LOW        = 10.0
ALPHA_THRESH   = 0.75
SAMPLE_SIZE    = 100

# ── Theatre regex ─────────────────────────────────────────────────────────────
THEATRE_RE = re.compile(
    r'\b('
    r'fin\s+du\s+\w+\s+acte'
    r'|acte\s+([ivxlcdm]+|\d+|premier|second|\w+i[eè]me)'
    r'|sc[eè]ne\s+([ivxlcdm]+|\d+|premi[eè]re?|derni[eè]re?|\w+i[eè]me)'
    r')',
    re.IGNORECASE
)
# Genuine stage-direction boilerplate is a short, self-contained heading;
# require the match to dominate the passage, not just appear somewhere
# inside much longer, unrelated prose (see step3 for the rationale).
THEATRE_MAX_WORDS = 15

# ─────────────────────────────────────────────────────────────────────────────
def reservoir_add(reservoir, rec, total_rejected):
    if len(reservoir) < SAMPLE_SIZE:
        reservoir.append(rec)
    else:
        j = random.randint(0, total_rejected - 1)
        if j < SAMPLE_SIZE:
            reservoir[j] = rec

def write_sample(path, reservoir):
    with open(path, "w", encoding="utf-8") as f:
        for rec in reservoir:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

def safe_float(val, default=50.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default

def alpha_ratio(text):
    non_space = text.replace(" ", "")
    if not non_space:
        return 0.0
    return len(re.findall(r"[a-zA-ZÀ-ÿ]", non_space)) / len(non_space)

# ─────────────────────────────────────────────────────────────────────────────
def step1(base, min_words=5, no_position=False):
    import lz4.frame, ahocorasick

    INPUT  = os.path.join(base, "alignments.jsonl.lz4")
    OUTPUT = os.path.join(base, "alignments_clean1.jsonl")
    SAMPLE = os.path.join(base, "alignments_clean1_rejected_sample.jsonl")

    print("Step 1 — phrase blocklist / position / short / OCR", flush=True)

    # Build automaton
    A = ahocorasick.Automaton()
    n = 0
    with open(PHRASE_FILE, encoding="utf-8") as fh:
        for line in fh:
            phrase = line.strip().lower()
            if phrase:
                A.add_word(phrase, phrase)
                n += 1
    A.make_automaton()
    print(f"  Blocklist: {n:,} phrases", flush=True)

    counts = {"total": 0, "kept": 0, "phrase": 0, "position": 0, "short": 0, "ocr": 0}
    reservoir = []
    rejected = 0
    t0 = time.time()

    with lz4.frame.open(INPUT, "rb") as fin, open(OUTPUT, "wb") as fout:
        for raw in fin:
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except Exception:
                continue

            counts["total"] += 1
            if counts["total"] % 100_000 == 0:
                print(f"  {counts['total']:,} processed | kept {counts['kept']:,} "
                      f"| {time.time()-t0:.0f}s", flush=True)

            sp = rec.get("source_passage") or ""
            tp = rec.get("target_passage") or ""
            reject = None

            # 1. Phrase blocklist
            if next(A.iter((sp + " " + tp).lower()), None) is not None:
                reject = "phrase"; counts["phrase"] += 1

            # 2. Position paratext (exempt long passages; skippable for short-doc corpora)
            if not reject and not no_position:
                se = safe_float(rec.get("source_end_position"))
                te = safe_float(rec.get("target_end_position"))
                ss = safe_float(rec.get("source_start_position"))
                ts = safe_float(rec.get("target_start_position"))
                if (se > POS_HIGH and te > POS_HIGH) or (ss < POS_LOW and ts < POS_LOW):
                    if len(sp.split()) < 100 and len(tp.split()) < 100:
                        reject = "position"; counts["position"] += 1

            # 3. Too short
            if not reject and len(sp.split()) < min_words:
                reject = "short"; counts["short"] += 1

            # 4. OCR noise
            if not reject and min(alpha_ratio(sp), alpha_ratio(tp)) < ALPHA_THRESH:
                reject = "ocr"; counts["ocr"] += 1

            if not reject:
                fout.write(raw + b"\n")
                counts["kept"] += 1
            else:
                rejected += 1
                rec["_reject_reason"] = reject
                reservoir_add(reservoir, rec, rejected)

    write_sample(SAMPLE, reservoir)
    elapsed = time.time() - t0
    total = counts["total"]
    pct = lambda n: f"{n/total*100:.1f}%" if total else "—"

    print(f"  Done in {elapsed:.1f}s.", flush=True)
    print(f"  Total: {total:,} | Kept: {counts['kept']:,} ({pct(counts['kept'])})", flush=True)
    print(f"  Rejected: phrase {counts['phrase']:,} | position {counts['position']:,} "
          f"| short {counts['short']:,} (min={min_words}) | ocr {counts['ocr']:,}", flush=True)

    return counts

# ─────────────────────────────────────────────────────────────────────────────
def step2(base, max_group_size=30):
    INPUT  = os.path.join(base, "alignments_clean1.jsonl")
    OUTPUT = os.path.join(base, "alignments_clean2.jsonl")
    SAMPLE = os.path.join(base, "alignments_clean2_rejected_sample.jsonl")

    print("Step 2 — group banality (max group size {})".format(max_group_size), flush=True)

    # Pass 1: count groups
    group_counts = Counter()
    with open(INPUT, "rb") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            group_counts[rec.get("group_id", 0)] += 1
            if n % 100_000 == 0:
                print(f"  Pass 1: {n:,} records...", flush=True)

    keep_groups = {gid for gid, cnt in group_counts.items() if cnt < max_group_size}
    print(f"  {len(group_counts):,} groups; keeping {len(keep_groups):,}, "
          f"removing {len(group_counts)-len(keep_groups):,}", flush=True)

    # Pass 2: filter
    kept = removed = 0
    reservoir = []
    with open(INPUT, "rb") as fh, open(OUTPUT, "wb") as fout:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("group_id", 0) in keep_groups:
                fout.write(line + b"\n")
                kept += 1
            else:
                removed += 1
                reservoir_add(reservoir, rec, removed)

    write_sample(SAMPLE, reservoir)
    print(f"  Kept: {kept:,} | Removed: {removed:,}", flush=True)
    return {"kept": kept, "removed": removed}

# ─────────────────────────────────────────────────────────────────────────────
def step3(base):
    INPUT  = os.path.join(base, "alignments_clean2.jsonl")
    OUTPUT = os.path.join(base, "alignments_clean3.jsonl")
    SAMPLE = os.path.join(base, "alignments_clean3_rejected_sample.jsonl")

    print("Step 3 — theatre markers", flush=True)

    kept = removed = 0
    reservoir = []
    with open(INPUT, "rb") as fin, open(OUTPUT, "wb") as fout:
        for n, line in enumerate(fin, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            sp = rec.get("source_passage") or ""
            tp = rec.get("target_passage") or ""
            # "acte" and "scene" are ordinary French words (legal "acte" =
            # deed/decree, "scene" = setting) far more often than they're
            # stage directions. Genuine stage-direction boilerplate is
            # short -- essentially just the heading itself ("ACTE PREMIER.
            # SCENE PREMIERE. Le Theatre represente") -- while false
            # positives are "acte"/"scene" appearing once inside much
            # longer, unrelated prose. Require the match to dominate a
            # short passage rather than merely appear somewhere in it.
            sp_hit = THEATRE_RE.search(sp) and word_count(sp) <= THEATRE_MAX_WORDS
            tp_hit = THEATRE_RE.search(tp) and word_count(tp) <= THEATRE_MAX_WORDS
            if sp_hit or tp_hit:
                removed += 1
                reservoir_add(reservoir, rec, removed)
            else:
                fout.write(line + b"\n")
                kept += 1
            if n % 100_000 == 0:
                print(f"  {n:,} processed | kept {kept:,} removed {removed:,}", flush=True)

    write_sample(SAMPLE, reservoir)
    print(f"  Kept: {kept:,} | Removed: {removed:,}", flush=True)
    return {"kept": kept, "removed": removed}

# ─────────────────────────────────────────────────────────────────────────────
def step4(base):
    INPUT  = os.path.join(base, "alignments_clean3.jsonl")
    OUTPUT = os.path.join(base, "alignments_clean4.jsonl")
    SAMPLE = os.path.join(base, "alignments_clean4_rejected_sample.jsonl")

    print("Step 4 — excluded filenames", flush=True)

    with open(EXCL_FILE) as f:
        excluded = set(json.load(f))
    print(f"  {len(excluded):,} excluded filenames", flush=True)

    kept = removed = 0
    reservoir = []
    with open(INPUT, "rb") as fh, open(OUTPUT, "wb") as fout:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("target_filename", "") in excluded:
                removed += 1
                reservoir_add(reservoir, rec, removed)
            else:
                fout.write(line + b"\n")
                kept += 1
            if n % 100_000 == 0:
                print(f"  {n:,} processed | kept {kept:,} removed {removed:,}", flush=True)

    write_sample(SAMPLE, reservoir)
    print(f"  Kept: {kept:,} | Removed: {removed:,}", flush=True)
    return {"kept": kept, "removed": removed}

# ── Title-reproduction / citation-clutter helpers ─────────────────────────────
import difflib


# Restricted to known bibliographic/reference abbreviations rather than any
# short word. The original pattern (any 1-8 letter word + "." + number)
# systematically misfires on numbered scripture verses -- e.g. Vulgate
# Psalm text like "...solemnitatis tuae. 6. Posuerunt..." matches the same
# shape as a real citation ("p. 6.") even though it's just verse numbering,
# not bibliographic apparatus. Genuine citation clutter (e.g. "Recherches
# de la Fr. l. VIII. c. 1. p. 754. Fauchet, p. 84.") still matches fine
# since real abbreviations like "p.", "c.", "l." are in the list below.
CITATION_ABBR = (
    r"p|pp|pag|pages?|ch|chap|chapitre|l|liv|livre|t|tom|tome|vol|volume|"
    r"art|n|no|nos|éd|ed|edit|edition|fol|f|c|cf|v|vs|vv|ann|sect|sec|s"
)
CITATION_RE = re.compile(
    r'\b(?:' + CITATION_ABBR + r')\.\s*\d{1,3}[,.:]\s*\d{0,3}\b',
    re.IGNORECASE
)

def normalize_tokens(text):
    return re.findall(r"[a-zà-ÿ']+", text.lower())

def title_overlap_ratio(passage, title):
    """Ratio of passage tokens that overlap with title tokens (containment)."""
    if not passage or not title:
        return 0.0
    p_tokens = normalize_tokens(passage)
    t_tokens = set(normalize_tokens(title))
    if not p_tokens or not t_tokens:
        return 0.0
    overlap = sum(1 for tok in p_tokens if tok in t_tokens)
    return overlap / len(p_tokens)

def is_title_echo(passage, title, min_title_tokens=3, threshold=0.7):
    t_tokens = normalize_tokens(title or "")
    if len(t_tokens) < min_title_tokens:
        return False
    # direct fuzzy match (handles reordering/OCR noise)
    ratio = difflib.SequenceMatcher(None, passage.lower(), title.lower()).ratio()
    if ratio >= threshold:
        return True
    # token containment (passage is mostly made of title's own words)
    return title_overlap_ratio(passage, title) >= threshold

def is_citation_clutter(text, min_hits=4):
    return len(CITATION_RE.findall(text)) >= min_hits

# ── Content-density helpers (step 6) ──────────────────────────────────────────
FUNC_WORDS = set("""
le la les l un une des du de d à au aux et ou mais donc car ni or que qui quoi
dont où ce cet cette ces se sa son ses leur leurs notre nos votre vos mon ma mes
ton ta tes il elle ils elles nous vous je tu on ne pas plus point jamais rien
est sont fut furent été être avoir a ont avait avaient sera seront serait
seraient dans pour sur avec sans sous entre chez par comme si tout tous toute
toutes même mêmes aussi bien fort très peu trop moins encore déjà alors ainsi
puis enfin selon lors dès depuis pendant après avant contre vers hors outre
qu n s c j m t y en quant peut
""".split())

# Latin function words — many Gallica/letters/dicos corpora contain substantial
# Latin passages (Vulgate, classical citations, legal formulas). Without these,
# every Latin passage scores near-zero on French function-word density and gets
# wrongly flagged as a low-content fragment regardless of whether it's genuine
# prose or noise.
LATIN_FUNC_WORDS = set("""
et in ad cum qui quae quod quia quoniam sunt est non ut sed aut vel nec si
per de ex e a ab atque ac enim autem sicut tamquam quam quo qua cur unde ubi
dum etiam tamen sive seu nam quidem ita hoc haec hic huius hunc hanc his
ille illa illud eius eum eam eos eas his ipse ipsa ipsum se sui sibi suum
suam suos suas nos vos ego tu mihi tibi nobis vobis me te qui quibus quorum
quarum cui cuius nunc tunc iam vero igitur ergo inter super sub post ante
propter usque quoque neque nisi ubi cunctis omnia omnibus rebus res
""".split())

FUNC_WORDS = FUNC_WORDS | LATIN_FUNC_WORDS

TITLECASE_RE = re.compile(r"^[A-ZÀ-ß][a-zà-ÿ'’]*\.?$|^[A-ZÀ-ß]{2,}\.?$")

def func_word_ratio(text):
    tokens = normalize_tokens(text)
    if not tokens:
        return 0.0
    hits = sum(1 for t in tokens if t.strip("'") in FUNC_WORDS)
    return hits / len(tokens)

def proper_noun_ratio(text):
    """Fraction of whitespace-split tokens (excluding the first) that look
    like capitalized names/title-case words — catches name lists, office
    lists, and bare titles.

    Case is only a meaningful signal when the passage has genuine upper/
    lower contrast. Classical mottos, epigraphs, and inscriptions are
    often typeset entirely in capitals (e.g. an all-caps rendering of a
    Horace ode or the Thermopylae epitaph) -- in that case EVERY token
    matches the title-case pattern regardless of content, which would
    otherwise make genuine quotations look identical to a name list. When
    the passage is overwhelmingly uppercase, treat the case signal as
    uninformative and return 0 rather than a false-positive ~1.0.
    """
    letters = [c for c in text if c.isalpha()]
    if letters and sum(1 for c in letters if c.isupper()) / len(letters) > 0.9:
        return 0.0
    raw_tokens = [t.strip(",;:()") for t in text.split()]
    raw_tokens = [t for t in raw_tokens if t]
    if len(raw_tokens) < 2:
        return 0.0
    rest = raw_tokens[1:]  # skip first token (sentence-initial capital is normal)
    if not rest:
        return 0.0
    hits = sum(1 for t in rest if TITLECASE_RE.match(t))
    return hits / len(rest)

def word_count(text):
    return len(normalize_tokens(text))

FRENCH_DIACRITICS_RE = re.compile(r"[éèêëàâçœîïôöûüù]")

def is_probably_latin(text):
    """Latin has no articles, so it's structurally more content-word-dense
    than French and will never clear a French-calibrated function-word
    threshold. Detect Latin via its own function words, and the near-total
    absence of French-specific diacritics as a corroborating signal."""
    tokens = normalize_tokens(text)
    if not tokens:
        return False
    latin_hits = sum(1 for t in tokens if t in LATIN_FUNC_WORDS)
    latin_ratio = latin_hits / len(tokens)
    french_diacritic_hits = len(FRENCH_DIACRITICS_RE.findall(text))
    return latin_ratio >= 0.12 and french_diacritic_hits == 0

DATE_TIME_RE = re.compile(
    r'\b('
    r'\d{1,4}\s*(ans?|si[eè]cles?)\s+(avant|apr[eè]s)'
    r'|avant\s+j[ée]sus.?christ|apr[eè]s\s+j[ée]sus.?christ|avant\s+j\.?-?c\.?'
    r'|l\'?an\s+de\s+gr[âa]ce'
    r'|\b\d{1,2}\s*heures?\b|\bmidi\b|\bminuit\b|\bdemie?\b(?!-)'
    r'|\b(janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre)\s+\d{1,4}\b'
    r')',
    re.IGNORECASE
)

def is_low_content(text, max_words=14, fr_thresh=0.40, pr_thresh=0.45):
    """Combined function-word-density / proper-noun-density check.
    Catches fragments, name lists, office lists, and bare title echoes
    that are too short to carry real intertextual content.

    Requires BOTH low function-word density AND high proper-noun density
    (not either alone). Low function-word density on its own is a normal
    property of compressed verse, maxims, and classical citations (Latin
    or French) -- not a sign of low content. What actually marks genuine
    noise (name lists, office lists, signature blocks) is the combination
    of sparse connective tissue *and* being dominated by bare proper nouns/
    titles. Spot-checking against the Gallica letters corpus showed the
    old OR logic discarding recognizable Horace, Cicero, and Voltaire
    citations alongside genuine noise; switching to AND preserved every
    correct catch (all scored high on proper-noun ratio) while sparing the
    false positives (which scored near-zero on proper nouns).
    """
    wc = word_count(text)
    if wc == 0 or wc > max_words:
        return False
    if is_probably_latin(text):
        # Latin has no articles, so it's inherently more content-word-dense
        # than French; only flag genuinely word-salad-short Latin fragments.
        return func_word_ratio(text) < 0.10 and wc <= 5
    fr = func_word_ratio(text)
    pr = proper_noun_ratio(text)
    return (fr < fr_thresh) and (pr > pr_thresh)

def is_date_time_reference(text, max_words=15):
    tokens = normalize_tokens(text)
    if not tokens or len(tokens) > max_words:
        return False
    return bool(DATE_TIME_RE.search(text))

# ─────────────────────────────────────────────────────────────────────────────
def step6(base):
    INPUT  = os.path.join(base, "alignments_clean5.jsonl")
    OUTPUT = os.path.join(base, "alignments_clean6.jsonl")
    SAMPLE = os.path.join(base, "alignments_clean6_rejected_sample.jsonl")

    print("Step 6 — content density (fragments / name-lists / date-time)", flush=True)

    counts = {"kept": 0, "fragment": 0, "namelist": 0, "datetime": 0}
    reservoir = []
    removed = 0
    with open(INPUT, "rb") as fh, open(OUTPUT, "wb") as fout:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue

            sp = rec.get("source_passage") or ""
            tp = rec.get("target_passage") or ""
            reject = None

            if is_low_content(sp) or is_low_content(tp):
                reject = "fragment"; counts["fragment"] += 1
            elif is_date_time_reference(sp) or is_date_time_reference(tp):
                reject = "datetime"; counts["datetime"] += 1

            if not reject:
                fout.write(line + b"\n")
                counts["kept"] += 1
            else:
                removed += 1
                rec["_reject_reason"] = reject
                reservoir_add(reservoir, rec, removed)

            if n % 100_000 == 0:
                print(f"  {n:,} processed | kept {counts['kept']:,} removed {removed:,}", flush=True)

    write_sample(SAMPLE, reservoir)
    print(f"  Kept: {counts['kept']:,} | Fragment/namelist: {counts['fragment']:,} | "
          f"Date/time: {counts['datetime']:,}", flush=True)
    return {"kept": counts["kept"], "removed": removed, **counts}

# ─────────────────────────────────────────────────────────────────────────────
def step5(base):
    INPUT  = os.path.join(base, "alignments_clean4.jsonl")
    OUTPUT = os.path.join(base, "alignments_clean5.jsonl")
    SAMPLE = os.path.join(base, "alignments_clean5_rejected_sample.jsonl")

    print("Step 5 — title echo / citation clutter", flush=True)

    counts = {"kept": 0, "title": 0, "citation": 0}
    reservoir = []
    removed = 0
    with open(INPUT, "rb") as fh, open(OUTPUT, "wb") as fout:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue

            sp = rec.get("source_passage") or ""
            tp = rec.get("target_passage") or ""
            s_title = rec.get("source_title") or ""
            t_title = rec.get("target_title") or ""
            reject = None

            if is_title_echo(sp, s_title) or is_title_echo(tp, t_title):
                reject = "title"; counts["title"] += 1
            elif is_citation_clutter(sp) or is_citation_clutter(tp):
                reject = "citation"; counts["citation"] += 1

            if not reject:
                fout.write(line + b"\n")
                counts["kept"] += 1
            else:
                removed += 1
                rec["_reject_reason"] = reject
                reservoir_add(reservoir, rec, removed)

            if n % 100_000 == 0:
                print(f"  {n:,} processed | kept {counts['kept']:,} removed {removed:,}", flush=True)

    write_sample(SAMPLE, reservoir)
    print(f"  Kept: {counts['kept']:,} | Title echo: {counts['title']:,} | "
          f"Citation clutter: {counts['citation']:,}", flush=True)
    return {"kept": counts["kept"], "removed": removed,
            "title": counts["title"], "citation": counts["citation"]}

# ─────────────────────────────────────────────────────────────────────────────
def count_lines(path):
    n = 0
    with open(path, "rb") as f:
        for _ in f:
            n += 1
    return n


def main():
    parser = argparse.ArgumentParser(description="TextPAIR 4-step filter pipeline")
    parser.add_argument("results_dir", help="Directory containing alignments.jsonl.lz4")
    parser.add_argument("--min-words",      type=int,   default=5,  help="Minimum passage word count (default 5)")
    parser.add_argument("--max-group-size", type=int,   default=30, help="Max group size before banality filter (default 30)")
    parser.add_argument("--no-theatre",     action="store_true",    help="Skip step 3 theatre marker filter")
    parser.add_argument("--no-position",    action="store_true",    help="Skip position paratext filter (useful for short-document corpora like letters)")
    parser.add_argument("--no-filenames",   action="store_true",    help="Skip step 4 excluded-filenames filter (useful for non-Gallica corpora, where the list never matches)")
    parser.add_argument("--no-title-citation", action="store_true", help="Skip step 5 title-echo / citation-clutter filter")
    parser.add_argument("--no-content-density", action="store_true", help="Skip step 6 content-density filter (fragments/name-lists/date-time)")
    parser.add_argument("--start-step", type=int, default=1, choices=range(1, 7),
                         help="Resume from this step (1-6). Assumes the output of step (start-step - 1) "
                              "already exists in results_dir (e.g. --start-step 5 requires alignments_clean4.jsonl).")
    args = parser.parse_args()

    base = args.results_dir.rstrip("/")
    if not os.path.isdir(base):
        print(f"Error: {base} is not a directory")
        sys.exit(1)

    if args.start_step <= 1:
        input_file = os.path.join(base, "alignments.jsonl.lz4")
        if not os.path.exists(input_file):
            print(f"Error: {input_file} not found")
            sys.exit(1)
    else:
        prev_file = os.path.join(base, f"alignments_clean{args.start_step - 1}.jsonl")
        if not os.path.exists(prev_file):
            print(f"Error: --start-step {args.start_step} requires {prev_file}, which was not found")
            sys.exit(1)

    print(f"\n{'='*60}")
    print(f"Filter pipeline: {base}")
    flags = f"  --min-words {args.min_words}  --max-group-size {args.max_group_size}"
    if args.no_theatre:  flags += "  --no-theatre"
    if args.no_position: flags += "  --no-position"
    if args.no_filenames: flags += "  --no-filenames"
    if args.no_title_citation: flags += "  --no-title-citation"
    if args.no_content_density: flags += "  --no-content-density"
    if args.start_step > 1: flags += f"  --start-step {args.start_step}"
    print(flags)
    print(f"{'='*60}\n")

    t_total = time.time()

    if args.start_step <= 1:
        r1 = step1(base, args.min_words, args.no_position); print()
    else:
        print(f"Step 1 — SKIPPED (resuming from step {args.start_step})", flush=True)
        r1 = None

    if args.start_step <= 2:
        r2 = step2(base, args.max_group_size); print()
    else:
        print(f"Step 2 — SKIPPED (resuming from step {args.start_step})", flush=True)
        r2 = None

    if args.start_step <= 3:
        if args.no_theatre:
            print("Step 3 — theatre markers: SKIPPED", flush=True)
            # Copy clean2 → clean3 so step 4 has its expected input
            import shutil
            prev_kept = r2["kept"] if r2 else count_lines(os.path.join(base, "alignments_clean2.jsonl"))
            shutil.copy(
                os.path.join(base, "alignments_clean2.jsonl"),
                os.path.join(base, "alignments_clean3.jsonl")
            )
            r3 = {"kept": prev_kept, "removed": 0}
        else:
            r3 = step3(base)
        print()
    else:
        print(f"Step 3 — SKIPPED (resuming from step {args.start_step})", flush=True)
        r3 = None

    if args.start_step <= 4:
        if args.no_filenames:
            print("Step 4 — excluded filenames: SKIPPED", flush=True)
            import shutil
            prev_kept = r3["kept"] if r3 else count_lines(os.path.join(base, "alignments_clean3.jsonl"))
            shutil.copy(
                os.path.join(base, "alignments_clean3.jsonl"),
                os.path.join(base, "alignments_clean4.jsonl")
            )
            r4 = {"kept": prev_kept, "removed": 0}
        else:
            r4 = step4(base)
        print()
    else:
        print(f"Step 4 — SKIPPED (resuming from step {args.start_step})", flush=True)
        r4 = None

    if args.start_step <= 5:
        if args.no_title_citation:
            print("Step 5 — title echo / citation clutter: SKIPPED", flush=True)
            import shutil
            prev_kept = r4["kept"] if r4 else count_lines(os.path.join(base, "alignments_clean4.jsonl"))
            shutil.copy(
                os.path.join(base, "alignments_clean4.jsonl"),
                os.path.join(base, "alignments_clean5.jsonl")
            )
            r5 = {"kept": prev_kept, "removed": 0, "title": 0, "citation": 0}
        else:
            r5 = step5(base)
        print()
    else:
        print(f"Step 5 — SKIPPED (resuming from step {args.start_step})", flush=True)
        r5 = None

    if args.no_content_density:
        print("Step 6 — content density: SKIPPED", flush=True)
        import shutil
        prev_kept = r5["kept"] if r5 else count_lines(os.path.join(base, "alignments_clean5.jsonl"))
        shutil.copy(
            os.path.join(base, "alignments_clean5.jsonl"),
            os.path.join(base, "alignments_clean6.jsonl")
        )
        r6 = {"kept": prev_kept, "removed": 0, "fragment": 0, "namelist": 0, "datetime": 0}
    else:
        r6 = step6(base)
    print()

    elapsed = time.time() - t_total

    if r1 is not None:
        # Full run from step 1 -- same detailed report as before.
        total_in  = r1["total"]
        total_out = r6["kept"]
        report_lines = [
            f"Filter pipeline report: {base}",
            "=" * 60,
            f"Input:  {total_in:>10,}",
            f"Output: {total_out:>10,}  ({total_out/total_in*100:.1f}% kept)" if total_in else "",
            "",
            f"Step 1 — phrase/position/short/OCR:",
            f"  Phrase blocklist:   {r1['phrase']:>10,}  ({r1['phrase']/total_in*100:.1f}%)" if total_in else "",
            f"  Position paratext:  {r1['position']:>10,}  ({r1['position']/total_in*100:.1f}%)" if total_in else "",
            f"  Too short:          {r1['short']:>10,}",
            f"  OCR noise:          {r1['ocr']:>10,}",
            f"Step 2 — group banality (>={args.max_group_size}): {r2['removed']:>10,} removed",
            f"Step 3 — theatre markers:               {r3['removed']:>10,} removed",
            f"Step 4 — excluded filenames:            {r4['removed']:>10,} removed",
            f"Step 5 — title echo:                    {r5['title']:>10,} removed",
            f"Step 5 — citation clutter:               {r5['citation']:>10,} removed",
            f"Step 6 — fragment/name-list/title echo: {r6['fragment']:>10,} removed",
            f"Step 6 — date/time reference:           {r6['datetime']:>10,} removed",
            "",
            f"Total runtime: {elapsed:.1f}s",
        ]
    else:
        # Resumed run -- only report on the steps actually executed this time.
        # Earlier-step counts (if wanted) live in this dir's prior filter_report*.txt.
        resumed_input = count_lines(os.path.join(base, f"alignments_clean{args.start_step - 1}.jsonl"))
        report_lines = [
            f"Filter pipeline report (RESUMED from step {args.start_step}): {base}",
            "=" * 60,
            f"Note: steps 1-{args.start_step - 1} were not run this pass -- see any prior "
            f"filter_report*.txt in this directory for those counts.",
            f"Input to step {args.start_step}:  {resumed_input:>10,}",
            f"Final output (alignments_clean6.jsonl): {r6['kept']:>10,}",
            "",
        ]
        if r5 is not None:
            report_lines += [
                f"Step 5 — title echo:                    {r5['title']:>10,} removed",
                f"Step 5 — citation clutter:               {r5['citation']:>10,} removed",
            ]
        report_lines += [
            f"Step 6 — fragment/name-list/title echo: {r6['fragment']:>10,} removed",
            f"Step 6 — date/time reference:           {r6['datetime']:>10,} removed",
            "",
            f"Total runtime: {elapsed:.1f}s",
        ]

    report = "\n".join(report_lines)
    print(report)

    report_suffix = f"_resumed_step{args.start_step}" if r1 is None else ""
    report_path = os.path.join(base, f"filter_report{report_suffix}.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report + "\n")
    print(f"\nReport saved to {report_path}", flush=True)

if __name__ == "__main__":
    main()
