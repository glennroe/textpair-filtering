#!/usr/bin/env python3
"""
corpus_source.py
One place that knows what "the corpus" means. Import it; do not re-derive it.

THE PROBLEM THIS EXISTS TO END
------------------------------
`combined_align` has not been the whole corpus since 15 August 2026. Rows are
MOVED to set-aside tables, never deleted, and every table must be read to see
the corpus:

    combined_align                    the working corpus
    combined_align_translations       42,385 rows, set aside 15 Aug
    combined_align_labelled_noise     82,550 rows, set aside 18 Aug

On 18 Aug FIVE separate scripts read `combined_align` alone and each produced a
confident, wrong result:

  map_martial_to_corpus.py    rebuilt martial_label_map with exact-key NON at
                              97 rows instead of 414,861
  sweep_density_floor.py      scored every threshold at 0.0% recall and 100%
                              false positives, because the NON class was gone
  labels_vs_rule.py           same fault, same shape
  report_martial_rows.py      would have reported the confirmed-NON population
                              as vanished
  merge_from_sets.py          printed a NEXT instruction sending the user to
                              the first of these

An earlier instance cost most of a morning: an anti-join that could not see
`combined_align_translations` reported 42,385 preserved rows as deletions and
produced an 8,770-row Horace shortfall whose true value was 629.

The fault was never subtle and it was never noticed, because the knowledge
lived in whoever was writing the query rather than in the code. A fact that
must be remembered in five places is a fact that will be forgotten in one.

WHAT THIS GIVES YOU
-------------------
    import corpus_source as CS

    CS.add_arguments(ap)                      # --table, --setaside, --live-only
    args = ap.parse_args()
    ...
    src = CS.CorpusSource(cur, args)          # resolves, validates, warns
    log(src.describe())
    sql = src.select("group_id, source_passage", alias="c")
    cur.execute(f"SELECT c.group_id FROM {sql} WHERE ...")

`CorpusSource` refuses to build quietly when a known set-aside table exists and
is being excluded. Excluding one is legitimate -- a question about the WORKING
corpus is a real question -- but it must be asked for, with --live-only, and it
is reported in every describe() so the choice appears beside the result.

It also warns about UNREGISTERED tables: any `combined_align_*` that is neither
a known set-aside nor a known derived table. A sixth set-aside created next
month is exactly the thing this module cannot know about, so it says so rather
than silently omitting it.

Self-test -- run it directly to see the current state:

    python3 corpus_source.py
"""

import sys

# Registry. A new set-aside table goes HERE and nowhere else.
KNOWN_SETASIDE = [
    "combined_align_translations",      # 15 Aug: Latin/translation genre pairs
    "combined_align_labelled_noise",    # 18 Aug: human-judged NON rows
    "combined_align_degenerate",        # 21 Aug: OCR rubble on BOTH sides,
                                        # set aside by sweep_degenerate.py
    "combined_align_classified_noise",  # 24 Aug: 162,958 rows the supervised
                                        # noise model condemned and three
                                        # readings adjudicated; setaside_reason
                                        # records the tier so a reversal can be
                                        # scoped to one of them
    "combined_align_editorial_noise",   # 22 Aug: whole groups Glenn read and
                                        # ruled on. Not a population, not a
                                        # score -- a judgement about what the
                                        # group IS, which is why it is also in
                                        # STRUCTURAL below.
    "combined_align_pruned_documents",  # 23 Aug: rows belonging to the 1,329
                                        # documents Glenn removed when he built
                                        # modern_all_pruned. The exclusion was
                                        # applied to every alignment run after
                                        # it and to none before it, so their
                                        # rows survived under the old
                                        # modern_all identity. STRUCTURAL.
]

# Registered BEFORE the table exists, deliberately. `_exists()` skips what is
# absent, so the entry costs nothing until the sweep commits -- and it closes
# the window between writing a set-aside pass and remembering to register its
# table, which is exactly where the 42,385 translation rows were reported as
# deletions for three days.

# STRUCTURAL removals: set aside by a RULING about what the pair IS, not by a
# classifier's verdict about how it looks. Nothing learned later can overturn
# them, so a probe asking "what did our filtering wrongly remove" must not
# read them -- their rows are not mistakes, they are decisions.
#
# Pass rescannable_only=True to omit these. It is NOT --live-only: the
# classifier's own output stays in, because that is precisely what a rescan
# is entitled to reconsider.
#
# Glenn, 21 Aug 2026: "the translation exclusions never need to be rescanned,
# only the classified noise."
STRUCTURAL = {
    "combined_align_translations":
        "14 Aug 2026 ruling: translation matched against translation is 'too "
        "easy and noisy' -- several editions are the same translation "
        "reprinted, so the match is a reprint rather than a reuse. Removed "
        "for what the PAIR IS, whatever language it is in, so no rescan can "
        "change the verdict. See setaside_translation_pairs.py and "
        "recovery-scope-representative-blindness-only.",
    "combined_align_editorial_noise":
        "22 Aug 2026: whole groups read and ruled noise -- a Fenelon title "
        "page circulating through catalogues, the Nicene Creed reproducing "
        "itself across 48 documents, the Treaty of The Hague, a bibliographic "
        "entry. The ruling is about what the GROUP is, not about how a row "
        "scores, so a rescan cannot overturn it any more than it can overturn "
        "the translations ruling. setaside_groups.py writes it and records the "
        "reason per group. NOTE: the same reading KEPT Article 14 of the "
        "Declaration and Title I of the 1791 Constitution, on the rule that "
        "the office reproducing itself goes while scripture in an argument "
        "stays -- so membership here is a judgement about circulation, never "
        "about the text's importance.",
    "combined_align_pruned_documents":
        "23 Aug 2026: the documents Glenn excluded when he built "
        "modern_all_pruned from modern_all -- tariff schedules, the "
        "Dictionaire de marine, ordonnances, the Code des prises, coutumes, "
        "guild statutes, almanachs de marchands, the Encyclopedie oeconomique, "
        "treatises on coinage. The pruning governed every later run; these "
        "rows survived only because the modern_all self-alignment and the "
        "dicos and letters runs predate it. Glenn, 23 Aug: 'I pruned them out "
        "on purpose... just for data coherence.' A ruling about what belongs "
        "in the corpus at all, so no rescan can reconsider it -- the same "
        "class as the translations and editorial rulings above. NOTE: the set "
        "is not uniform (Le Nouveau Testament 1534, the Book of Common Prayer "
        "sit in it), which is why setaside_pruned_documents.py reports what it "
        "is about to move BY WORK and not merely by count.",
}
# combined_align_labelled_noise is NOT here. Those rows were set aside on
# human judgement of the ROW, which is a verdict about that passage and can
# in principle be revisited, so a rescan may legitimately read them.

# Tables that sit alongside the corpus and are NOT part of it. Listed so the
# unregistered-table warning does not fire on them every run.
#
# Two different reasons to be here, both meaning "do not union this":
#   derived     rebuilt from the corpus by rebuild_derived_tables.py; unioning
#               one would double-count every row it summarises
#   adjacent    a different kind of object entirely
NOT_CORPUS_SUFFIXES = [
    "_groups",                # derived: one representative row per group
    "_ordered",               # derived: the corpus in display order
    "_groups_provenance",     # adjacent: scholarly attribution overrides
    "_reference_passages",    # adjacent: Phase 4 canonical readings from
                              # public-domain editions. NOT alignment rows --
                              # a reference passage is a printed text we may
                              # display beside a group, not a witness in it.
                              # Empty as of 18 Aug 2026.
]

# Kept as an alias so nothing breaks if an older import used the former name.
DERIVED_SUFFIXES = NOT_CORPUS_SUFFIXES


def add_arguments(ap, table_default="combined_align"):
    """Add the standard corpus arguments to an argparse parser."""
    ap.add_argument("--table", default=table_default,
                    help="the working corpus table")
    ap.add_argument("--setaside", nargs="*", default=None,
                    help="set-aside tables to include. Defaults to every "
                         "registered one that exists. Rows there were moved, "
                         "not deleted.")
    ap.add_argument("--live-only", action="store_true",
                    help="read the WORKING corpus only, excluding set-aside "
                         "rows. A deliberate choice, not a default: it answers "
                         "'what is live' rather than 'what exists'.")
    return ap


class CorpusSource:
    """Resolves what to read, and says so."""

    def __init__(self, cur, args=None, table=None, setaside=None,
                 live_only=False, warn=None, rescannable_only=False):
        self.cur = cur
        self.warn = warn or (lambda m: print(m, file=sys.stderr, flush=True))
        self.table = table or getattr(args, "table", "combined_align")
        if args is not None:
            if setaside is None:
                setaside = getattr(args, "setaside", None)
            live_only = live_only or getattr(args, "live_only", False)
            rescannable_only = rescannable_only or getattr(
                args, "rescannable_only", False)
        self.live_only = live_only
        self.rescannable_only = rescannable_only

        wanted = [] if live_only else (
            KNOWN_SETASIDE if setaside is None else list(setaside))
        wanted = [t for t in wanted if t]
        # A structural removal is a ruling, not a mistake, so a rescan reads
        # past it deliberately rather than being refused for omitting it.
        self.structural_skipped = []
        if rescannable_only:
            self.structural_skipped = [t for t in wanted if t in STRUCTURAL]
            wanted = [t for t in wanted if t not in STRUCTURAL]

        if not self._exists(self.table):
            raise SystemExit(f"corpus_source: {self.table} does not exist.")
        self.tables = [self.table]
        self.missing = []
        for t in wanted:
            if self._exists(t):
                self.tables.append(t)
            else:
                self.missing.append(t)

        # The guard. Excluding a set-aside table that exists and holds rows is
        # the exact fault this module was written for, so it is never silent.
        self.excluded = []
        for t in KNOWN_SETASIDE:
            if t in self.tables or not self._exists(t):
                continue
            if t in self.structural_skipped:
                continue        # omitted on purpose, and reported in describe()
            n = self._count(t)
            if n:
                self.excluded.append((t, n))
        if self.excluded:
            held = sum(n for _t, n in self.excluded)
            msg = ("corpus_source: EXCLUDING " +
                   ", ".join(f"{t} ({n:,} rows)" for t, n in self.excluded) +
                   f" — {held:,} row(s) held there are NOT being read.")
            if live_only:
                self.warn(msg + " (--live-only was given)")
            else:
                raise SystemExit(
                    msg + "\n\nThose rows were MOVED, not deleted. Reading "
                    "without them is how five scripts produced confident "
                    "wrong answers on 18 Aug. If you mean to read only the "
                    "working corpus, pass --live-only and say so in the "
                    "output.")

        self._unregistered()

    def _exists(self, t):
        self.cur.execute("SELECT to_regclass(%s)", (t,))
        return self.cur.fetchone()[0] is not None

    def _count(self, t):
        self.cur.execute(f"SELECT COUNT(*) FROM {t}")
        return self.cur.fetchone()[0]

    def _unregistered(self):
        """A set-aside table created after this module was written is the one
        thing it cannot know about. Look for candidates and say so."""
        self.cur.execute("""
            SELECT tablename FROM pg_tables
             WHERE schemaname NOT IN ('pg_catalog','information_schema')
               AND tablename LIKE %s""", (self.table + "\\_%",))
        found = [r[0] for r in self.cur.fetchall()]
        unknown = [t for t in found
                   if t not in KNOWN_SETASIDE
                   and not any(t == self.table + s for s in NOT_CORPUS_SUFFIXES)
                   and not t.startswith(self.table + "_groups")]
        if unknown:
            self.warn(
                "corpus_source: unregistered table(s) alongside the corpus: "
                + ", ".join(unknown) +
                ". If any holds set-aside rows, add it to KNOWN_SETASIDE in "
                "corpus_source.py — it is NOT being read.")
        self.unregistered = unknown

    def select(self, cols, alias=None, where=None):
        """A parenthesised UNION ALL over every table being read.

        `cols` must name the same columns in the same order for every table,
        which is why it is a single string rather than per-table.
        """
        w = f" WHERE {where}" if where else ""
        body = " UNION ALL ".join(
            f"SELECT {cols} FROM {t}{w}" for t in self.tables)
        return f"({body})" + (f" {alias}" if alias else "")

    def counts(self):
        return {t: self._count(t) for t in self.tables}

    def total_rows(self):
        return sum(self.counts().values())

    def describe(self):
        bits = [f"corpus = {' + '.join(self.tables)}"]
        if self.live_only:
            bits.append("WORKING CORPUS ONLY (--live-only): set-aside rows "
                        "excluded")
        if self.structural_skipped:
            bits.append("STRUCTURAL removals skipped deliberately (" +
                        ", ".join(self.structural_skipped) +
                        ") — set aside by ruling, not by classifier, so not "
                        "rescannable")
        if self.missing:
            bits.append("not present: " + ", ".join(self.missing))
        if self.unregistered:
            bits.append("UNREGISTERED and unread: " +
                        ", ".join(self.unregistered))
        return "; ".join(bits)


if __name__ == "__main__":
    import configparser, psycopg2
    cfg = configparser.ConfigParser()
    cfg.read("/etc/text-pair/global_settings.ini")
    conn = psycopg2.connect(user=cfg["DATABASE"]["database_user"],
                            password=cfg["DATABASE"]["database_password"],
                            database=cfg["DATABASE"]["database_name"])
    cur = conn.cursor()
    print("=" * 78)
    print("CORPUS SOURCE — what 'the corpus' currently means")
    print("=" * 78)
    src = CorpusSource(cur)
    print(f"\n  {src.describe()}\n")
    total = 0
    for t, n in src.counts().items():
        print(f"      {t:<34} {n:>12,}")
        total += n
    print(f"      {'TOTAL':<34} {total:>12,}")
    print(f"""
  Any script reading only {src.table} sees
  {src.counts()[src.table]:,} of these — the rest were moved, not deleted.

  Example of the SQL this produces:

      {src.select('group_id, source_passage', alias='c')[:300]}
""")
    cur.close(); conn.close()


# ---------------------------------------------------------------------------
# next_free_group_id -- added 27 Sep 2026.
# Three tools took new ids from max(group_id)+1 over the LIVE table alone.
# Once the highest-numbered groups had been set aside, that re-issued ids
# still carried by set-aside rows: detach_rows_to_group.py gave the Crito
# rows 11200308633, which Henault's 18 rows in combined_align_editorial_noise
# already held. An id is taken wherever it appears -- the working table,
# every registered set-aside table, and the provenance tables (a tombstone
# claim on a retired id would otherwise be inherited by a stranger).
# ---------------------------------------------------------------------------
ID_HOLDERS_EXTRA = ["combined_align_groups_provenance",
                    "combined_align_groups_provenance_withdrawn"]

def next_free_group_id(cur, table="combined_align"):
    tabs = [table] + [t for t in KNOWN_SETASIDE if t != table] + ID_HOLDERS_EXTRA
    mx = 0
    for t in tabs:
        cur.execute("SELECT to_regclass(%s)", (t,))
        if cur.fetchone()[0] is None:
            continue
        cur.execute(f"SELECT COALESCE(MAX(group_id), 0) FROM {t}")
        mx = max(mx, cur.fetchone()[0] or 0)
    return mx + 1
