#!/usr/bin/env python3
"""
latin_detect.py
Scores a passage as Latin or French. Imported by
find_orphan_latin_sources.py and cluster_orphan_latin.py.

WHY THIS IS A MODULE AND NOT A FUNCTION IN THE SCANNER
------------------------------------------------------
cluster_orphan_latin.py originally did

    from find_orphan_latin_sources import latin_score

and find_orphan_latin_sources.py has no `if __name__ == "__main__"` guard,
so the import EXECUTED the whole scanner: it connected to the database,
scored 272,014 groups and printed 400 of them into the clustering script's
output file before the clustering began. The run took twice as long as it
should have and orphan_clusters.txt opened with the wrong report.

Nothing was wrong with the scorer; the fault was in packaging it inside a
script that does work at import time. Shared logic goes in a module.

WHAT THE SCORER DOES
--------------------
Latin in an eighteenth-century French corpus is a gross distinction, and
three signals settle it.

  ACCENTS. French carries e-acute, e-grave, a-grave, c-cedilla constantly;
  Latin, even in period orthography, essentially never does. Treated as a
  veto rather than a vote: >= 2% of characters accented caps the score.

  LATIN MORPHOLOGY. Word endings, MEASURED against both case sets rather
  than assumed. Across the self-test corpus -um scores 11 Latin against 0
  French, -em 4 against 0, and -orum, -arum, -ibus, -tur, -que, -ium, -am,
  -os, -as, -ere likewise. Rejected after measurement: -it (6 Latin, 5
  French -- fait, dit, soit, petit, lit), -es and -ent (French plural and
  verb endings), -ae, -ius, -unt (no signal either way).

  This is the signal that carries short verse, and it is why the first
  draft failed. That draft used function words alone and scored 0.00 on
  'Discite juftitiam moniti, & non temnere Divos' and on 'quo femel est
  imbuta recens; fervabit odorem testa diu' -- two of the three
  native_unaligned verses the pass exists to find. Classical quotations
  are short and made almost entirely of content words, so there is nothing
  for a function-word scorer to weigh.

  FUNCTION WORDS on both sides, with the French weighted double because
  their presence is close to decisive: no Latin passage contains le, la,
  les, du, des. Forms common to both languages -- et, est, non, qui, in,
  a -- are deliberately in NEITHER list, since they carry no information.

Two guards, each added after a real false positive.

  Long-s corruption is admitted as f-variants of the Latin markers (funt,
  fed, ipfe, effe, femper, nifi), because that is the same OCR fault that
  caused the misalignments in the first place.

  A CAPITALISATION cap, added after the first full scan returned a list of
  French departments at a perfect 1.00 -- 'Haute-Garonne Gers Gironde ...
  Ille-et-Vilaine Indre-et-Loire Isere'. It contains no French function
  words at all, so nothing sits on the French side of the ratio, and a few
  place names end in Latin-looking syllables. Gazetteers, indexes and
  subscriber lists all fail that way. Measured:

      departement list      caps 0.86
      Horace, Carmina III.30     0.43
      Aeneid VI.620, OCR'd       0.33
      Virgil, Aeneid IV          0.12
      legal Latin                0.00

  A verse capitalises its first word and its proper names; a list
  capitalises everything.

WHY THIS SCORER IS TRUSTED WHERE TWO EARLIER ONES WERE NOT
----------------------------------------------------------
An IDF floor condemned the Marseillaise and Genesis; word-3-gram template
detection found 'il y a'. Both scored a passage's own words against the
corpus, which is subtle and failed quietly. This asks what language the
text is in, which is coarse. And its failure mode is conservative: a false
positive flags a group for reading and asserts nothing, where a false
positive in boilerplate_patterns.py deleted literature.

Run this file directly for the self-test. A scorer without a test is how
the previous two failures happened.

Usage:
    python3 latin_detect.py            # self-test
    from latin_detect import latin_score, normalise
"""

import re, html, sys

MIN_LEN = 25          # below this, no judgement is attempted
CAPS_MAX = 0.60       # proper-noun / gazetteer guard
ACCENT_MAX = 0.02     # accent rate above which a passage is French

_ACCENTS = set("éèêëàâäçôöûüùîïÉÈÊÀÂÇÔÛÙÎ")
_WORD = re.compile(r"[a-zA-ZÀ-ÿ]+")

LATIN = {
    "atque", "autem", "enim", "tamen", "quidem", "ipse", "ipsa", "ipsum",
    "esse", "sunt", "erat", "erit", "nec", "neque", "quae", "quam", "quod",
    "quid", "cum", "ex", "ad", "per", "sed", "ut", "aut", "nam", "iam",
    "jam", "nisi", "sine", "super", "inter", "ante", "etiam", "igitur",
    "ergo", "vero", "quoque", "omnia", "omnes", "omnis", "magis", "semper",
    "nihil", "hoc", "haec", "hunc", "hanc", "illa", "ille", "illud", "eius",
    "ejus", "suis", "suum", "nostra", "nostri", "tibi", "mihi", "sibi",
    "res", "rerum", "causas", "animo", "modo", "tantum", "satis",
    "funt", "fed", "ipfe", "effe", "femper", "nifi", "fine", "fatis",
    "fuper", "fuis", "fibi", "fic", "fecundum",
}
FRENCH = {
    "le", "la", "les", "de", "des", "du", "en", "ne", "pas", "un", "une",
    "dans", "pour", "que", "plus", "sur", "cette", "leur", "leurs", "aux",
    "avec", "sont", "tout", "tous", "toute", "mais", "ainsi", "comme",
    "sans", "sous", "ils", "elle", "elles", "nous", "vous", "très", "où",
    "déjà", "celui", "ceux", "cela", "ce", "se", "sa", "ses", "son", "au",
    "par", "il", "on", "je", "lui", "être", "avoir", "fait", "faire",
    "bien", "peu", "point", "encore", "toujours", "jamais", "même",
    "aussi", "donc", "car", "quand",
}
LATIN_ENDINGS = ("orum", "arum", "ibus", "tur", "que", "ium",
                 "um", "us", "am", "em", "os", "as", "ere", "is")


def normalise(s):
    if s is None:
        return ""
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def latin_score(passage):
    """Return (score, detail). 1.0 is unambiguous Latin, 0.0 French."""
    s = normalise(passage)
    if len(s) < MIN_LEN:
        return 0.0, {"reason": "too short"}
    words = [w.lower() for w in _WORD.findall(s)]
    if len(words) < 4:
        return 0.0, {"reason": "too few words"}

    acc = sum(1 for ch in s if ch in _ACCENTS)
    acc_rate = acc / len(s)
    lat_w = sum(1 for w in words if w in LATIN)
    fre_w = sum(1 for w in words if w in FRENCH)
    lat_e = sum(1 for w in words
                if len(w) > 3 and w.endswith(LATIN_ENDINGS) and w not in FRENCH)

    lat = lat_w + lat_e
    fre = 2 * fre_w
    score = 0.0 if lat == 0 else lat / (lat + fre)

    if acc_rate >= ACCENT_MAX:
        score = min(score, 0.15)
    caps = sum(1 for w in _WORD.findall(s) if w[:1].isupper()) / len(words)
    if caps >= CAPS_MAX:
        score = min(score, 0.15)

    return score, {"words": len(words), "latin_words": lat_w,
                   "latin_endings": lat_e, "french_words": fre_w,
                   "accents": acc, "acc_rate": round(acc_rate, 4),
                   "caps": round(caps, 2)}


# ---------------------------------------------------------------------------
# Self-test. Every passage is real, from the review files or this project's
# own history.
# ---------------------------------------------------------------------------
LATIN_CASES = [
    ("Virgil, Georgics II.490", "Felix qui potuit rerum cognoscere causas, Atque metus omnes et inexorabile fatum Subjecit pedibus"),
    ("Virgil, Aeneid III.56-57", "fas omne abrumpit: Polydorum obtruncat, et auro ui potitur. quid non mortalia pectora cogis, auri sacra fames"),
    ("Horace, Ars Poetica 343", "Omne tulit punctum qui miscuit utile dulci lectorem delectando pariterque monendo"),
    ("Horace, Sermones I.4.43", "Ingenium cui sit, cui mens divinior atque os Magna sonaturum, des nominis hujus honorem"),
    ("Virgil, Aeneid VI.620, OCR'd", "Discite juftitiam moniti, & non temnere Divos"),
    ("Horace, Epistulae I.2.69, OCR'd", "quo femel est imbuta recens; fervabit odorem testa diu"),
    ("Virgil, Georgics II.458, OCR'd", "fortunatos nimium, fua si bona norint, Agricolas"),
    ("Pliny, Latin", "Italia octoni boves ad singulos vomeres anhelent"),
    ("Lucretius", "esse vias in mente parent, Qua possint eadem rerum simulacra venire"),
    ("Tacitus, legal", "velut regula juris est, ufuras ufurarum non deberi, futti tantum deberi"),
    ("Horace, Carmina I.1.7", "Hunc si mobilium turba Quiritium Certat tergeminis tollere honoribus"),
    ("Horace, Carmina III.30", "qua pauper aquae Daunus agrestium Regnavit Populorum"),
]
FRENCH_CASES = [
    ("department list -- gazetteer", "Haute-Garonne Gers Gironde. . ( Bordeaux. (Sainte-Foy. Herault. $ Montpellier. Beziers. Ille-et-Vilaine Indre-et-Loire Isere. ( Grenoble, (Vienne. Jura v Landes Loir-et-Cher Haute-Loire Loire-Inferie"),
    ("Boileau", "Rien n'est beau que le vrai. Le vrai seul est aimable"),
    ("Boileau, Art poétique", "Enfin Malherbe vint, et le premier en France, fit sentir dans les vers une juste cadence"),
    ("Homer, French translation", "reconnoît bien ici les mœurs anciennes. Iphitus va chercher les mules et les juments de son père"),
    ("journal commonplace", "Voilà, à peu près, ce que l'on peut dire sur ce sujet"),
    ("chancery", "Fait à Versailles le vingtième jour du mois de juin mil sept cent"),
    ("Ecclesiastes 12:1, French", "Créateur pendant les jours de votre jeunesse, avant que le temps de l'affliction soit arrivé"),
    ("dynasties", "doit rapporter ce qui se lit dans nos hiftoriens de la première et de la seconde Race"),
    ("Montaigne-ish prose", "Tout me confirma bien-tôt dans la résolution de rompre avec lui tout commerce"),
    ("Tite-Live, French trans., archaic", "fix mille hommes de pied, huit cens de cheual"),
    ("Plutarch, French translation", "des vieillards et des femmes descendit jusqu'aux bords de la riviere en tendant les mains"),
]


def selftest(threshold=0.70, out=sys.stdout):
    p = lambda *a: print(*a, file=out)
    p("=" * 78)
    p(f"latin_detect SELF-TEST -- threshold {threshold}")
    p("=" * 78)
    bad = 0
    for label, cases, want_latin in (("MUST SCORE LATIN", LATIN_CASES, True),
                                     ("MUST SCORE FRENCH", FRENCH_CASES, False)):
        p(f"\n{label}")
        for name, passage in cases:
            sc, d = latin_score(passage)
            ok = (sc >= threshold) if want_latin else (sc < threshold)
            bad += not ok
            p(f"  {'ok  ' if ok else 'FAIL'} {sc:.2f}  {name}")
            if not ok:
                p(f"        {d}")
                p(f"        {passage[:100]!r}")
    p("\n" + "=" * 78)
    p("PASSED" if not bad else f"FAILED: {bad} case(s)")
    return bad == 0


if __name__ == "__main__":
    sys.exit(0 if selftest() else 1)
