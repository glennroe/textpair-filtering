#!/usr/bin/env python3
"""
boilerplate_patterns.py
Shared vocabulary for classifying an identical-passage cluster as
administrative boilerplate. Imported by both merge_identical_clusters.py
and apply_boilerplate_exclusions.py so the two cannot drift apart: every
cluster the merge script skips is exactly one the deletion script
considers, and vice versa.

The categories continue the ones established by hand across
apply_group_exclusions_gallica2/3/4.py, extended with the formulae that
the identical-passage sweep showed were being missed -- in particular the
tail of the print-privilege formula ("ferme & stable a toujours", "cire
verte sur lacs de soye", "Donne a Versailles ... Signe LOUIS"), which is
far more productive of duplicate groups than the opening clauses that
earlier passes had caught.

WHAT THIS IS AND IS NOT FOR
---------------------------
Matching here means "propose for deletion". It is a coarse instrument
applied to 13,615 clusters, so it is tuned to be CONSERVATIVE: a pattern
is included only if a false positive would be hard to imagine. Anything
not matched falls through to the merge script, which is lossless. The
asymmetry is deliberate -- an unmatched noise cluster merely survives as
a tidier group, whereas a wrongly matched literary cluster is destroyed.

Known deliberate exclusions, learned from the residue review:
  - "droit des gens", "droit naturel", "souveraineté", "citoyen" alone
    are NOT boilerplate markers: they occur throughout the Declaration
    des droits and in Rousseau, Montesquieu and their commentators.
  - "chevalier", "comte", "marquis" match honorific styles but also
    occur in narrative and verse, so they are required to co-occur with
    other administrative vocabulary rather than matching alone.
  - Biblical and liturgical vocabulary is excluded entirely; scripture
    in this corpus is citation, not boilerplate.
"""

import re

# ---------------------------------------------------------------------------
# Pre-normalisation before matching.
#
# The first dry run of merge_identical_clusters.py showed boilerplate leaking
# into the merge set for avoidable reasons, all of them typographic rather
# than semantic:
#   - the corpus uses the typographic apostrophe U+2019 ("l’Ordre Royal"),
#     while the patterns were written with ASCII "'", so nothing matched
#   - OCR renders the ampersand variously as "&", "&amp;", "6c", "8c", "&c",
#     "Se" and "5c", fragmenting every formula containing one
#   - stray commas and spacing inside OCR'd formulae ("Chevalier de ,,l’Ordre")
#     break otherwise fixed phrases
#
# Folding these away before matching lets each pattern be written once, in
# clean modern orthography, instead of enumerating OCR variants.
# ---------------------------------------------------------------------------

# "3c" added 14 Aug 2026: "Ordre Royal 3c Militaire de Saint Louis" survived
# the top5 pass because the ampersand folding knew 6c, 8c and 5c but not 3c.
_AMP = re.compile(r"&amp;|&c\b|\b[3568]c\b|\bSe\b|&")
_APOS = re.compile(r"[’‘´`]")
_QUOTE = re.compile(r"[«»“”]")
_JUNK = re.compile(r"[,;:]{2,}|\s+")


def prepare(passage):
    """Fold typographic and OCR noise so patterns can be written plainly."""
    if not passage:
        return ""
    s = _APOS.sub("'", passage)
    s = _QUOTE.sub(" ", s)
    s = _AMP.sub("&", s)
    s = _JUNK.sub(" ", s)
    return s.strip()


CATEGORIES = {
    "legislative (Revolution / Directory)": [
        r"conseil des (cinq[- ]cents|anciens)", r"convention nationale",
        # A bare "\\brésolution\\b" was here and had to go: it matched "dans la
        # résolution de rompre avec lui tout commerce" -- the ordinary sense of
        # resolve, not a Directory legislative act. Under the Directory a
        # résolution is passed by a council, so require that context.
        r"(projet|présente|ladite|la) résolutions?\b[^.]{0,30}(conseil|cinq[- ]cents|anciens)",
        r"résolutions? (du conseil|des cinq[- ]cents|des anciens)",
        r"résolutions? (adoptée|prise|déclarée)",
        r"déclare qu'il y a urgence", r"après avoir (déclaré|décrété) l'urgence",
        r"(déclaré|décrété) l'urgence", r"corps législatif", r"adjudication légale",
        r"nom de la république", r"conseil exécutif provisoire", r"mande et ordonne",
        r"une et indivisible", r"me et indivisible",
        r"garantie de la foi publique", r"assemblée nationale, après avoir",
        r"messidor", r"thermidor", r"fructidor", r"germinal", r"brumaire", r"nivôse",
        r"prairial", r"floréal", r"ventôse", r"vendémiaire", r"pluviôse",
        r"directoire exécutif", r"extrait des registres", r"extrait du registre",
        r"séance (publique|du)", r"imprimée, lue, publiée", r"publiée (6c|8c|&|&amp;) affichée",
        r"loi portant", r"an de la république",
        # Added for combined_align: the decree preamble is the single most
        # productive formula in the revolutionary material, 126 groups and
        # 2,810 rows across "l'Assemblée Nationale, après avoir entendu le
        # rapport de son Comité des Finances / de législation / de salut
        # public". The Declaration's own articles are protected by NEVER,
        # which is checked first.
        r"avoir entendu le rapport", r"entendu le rapport (du|de son|de ses|qui)",
        r"sur le rapport qui lui a été fait", r"rapport de son comité",
        r"comité (des finances|de législation|de salut public|d'instruction)",
    ],
    "print privilege / chancery / notarial": [
        r"faire imprimer", r"d'imprimer ou",
        # `privilèg` measured 21.5% false positive against 65 labelled
        # matches, 18 Aug 2026: a bare stem with no boundary, it caught La
        # Fontaine's Renommée and physiocratic writing on property. The
        # legal sense always names the grantor or the trade.
        r"privil[èe]ges?\b[^.]{0,30}\b(roi|roy|majest[ée]|imprimer|impression|[ée]dition|libraire|imprimeur|ouvrage)\b",
        r"privilege sur ce",
        # `contrefa` measured 35.0% false positive, the worst of any
        # pattern: unanchored at both ends, it caught "L'art de se
        # contrefaire, de revêtir un autre caractère que le sien".
        r"contrefa\w*\b[^.]{0,40}\b(ouvrage|livre|impression|[ée]dition|exemplaires?|imprim)",
        r"lettres patentes", r"sénéchaux", r"huissier",
        r"sergent sur ce requis", r"\b(nous|vous) mandons\b", r"ordonnons",
        # "nos amés" and "cour de parlement" were spelled in modern
        # orthography and so missed the commonest OCR forms -- "A nos amez &
        # féaux Conseillers les Gens tenans nos Cours du Parlement" matched
        # neither. Found by test_boilerplate_patterns.py, not by review.
        r"enjoint sa majesté", r"nos am[eé]z?\b", r"f[ée]aux conseillers",
        r"gens tenans", r"commissaires départis", r"commiflaires",
        # The Alphabet typographique privilege clause, deleted by hand as
        # group 1200046753 but never caught by any pattern. The separator was
        # too strict -- "vendre & debiter par tout le Royaume" leaked through
        # the top5 pass three times because only a comma was allowed.
        r"vendre\s*(,|&|et)?\s*d[eé]biter", r"faire afficher",
        # Further leaks found in the top5 review, each a missing formula
        # rather than a missing category.
        r"en fo[iy] de quoi", r"fo[iy] de quoi nous avons",
        r"apposer le cachet", r"cachet de nos armes",
        # "compter du jour de la publication du present Edit" -- the "à" is
        # not always there.
        r"\bcompter du jour",
        r"requ[ée]rant le procureur", r"faisant droit sur les conclusion",
        r"table de marbre", r"pr[ée]v[ôo]t des marchands", r"[ée]chevins de",
        r"chambre (des|de nos) comptes", r"cours? des ayde",
        r"logement de gens de guerre", r"exemptions? de taille",
        r"prie dieu qu'il vous ait", r"en sa sainte (et|&) digne garde",
        r"servus servorum dei",
        # "grâce mil sept cent cinquante-cinq" -- without the "l'an de".
        r"gr[âa]ce mil (six|sept|huit) cen",
        r"intendans", r"greffier", r"forme (&|et) teneur", r"forme teneur",
        r"plein & entier effet", r"sortira son plein", r"trouble ny empêchement",
        r"amende applicable", r"exemplaires contrefaits", r"livres d'amende",
        r"dépens, dommages", r"ferme &? ?(stable|fiable|ftable)", r"cire verte",
        r"lacs de so[iy]e", r"lacs de fo[iy]e", r"grand sceau", r"scellé",
        r"à versailles le", r"sign[ée] louis", r"de n[oô]tre regne", r"de notre règne",
        r"bon papier", r"beaux caractères", r"foy soit adjoustée",
        r"tel est n[oô]tre plaisir", r"en témoin dequoy", r"nous avons fait mettre",
        r"avons fait apposer", r"presentes lettres verront", r"présentes lettres verront",
        r"\bregistres\b", r"cours? d[eu] parlement",
        # "arrêt"/"arresté" is kept bare, because narrowing it to explicit
        # phrases ("arrêt de la cour", "suivant l'arrêt") released 378
        # clusters of genuine chancery text -- "l'exécution du présent
        # arrêté", "faire joüir ledit Exposant" and the like. The single
        # verse it wrongly caught, "par arrêt du Ciel, il faut que l'homme
        # meure", is instead handled by NEVER, which is checked first. That
        # is the right division of labour: broad patterns for a formulaic
        # register, an explicit exception list for the quotations that
        # borrow its vocabulary.
        # THE SINGLE LARGEST SOURCE OF FALSE POSITIVES: 552 labelled
        # matches, 73 of them wrong. `arr[êe]s?t[ée]?s?` conflates the
        # legal noun *arrêt* with the participle *arrêté*, "arrested", and
        # so condemns Declaration des droits ARTICLE 7 -- "Nul homme ne
        # peut être accusé, arrêté ni détenu" -- in four groups.
        #
        # A narrowing was tried once and reverted for releasing 378 genuine
        # chancery clusters; that was done blind. The noun stays
        # unconditional, so those clusters are still caught. Only the
        # participle -- which is where the damage is -- needs context, and
        # the Directory's administrative *arrêtés* keep theirs.
        r"\barr[êe]s?ts?\b",
        r"\barr[êe]t[ée]s?\b[^.]{0,30}\b(directoire|conseil|comit[ée]|consuls|convention|municipalit[ée]|pr[ée]fet|pris? par)\b",
        r"qualité (et|&|se) condition qu", r"de l'imprimer",
        r"faire jo[uü]ir", r"ledit exposant", r"chancelier le manuscrit",
        r"avons fait mettre", r"scel à ce", r"seel à ce", r"nôtre scel", r"notre scel",
        r"enjoint aux subst", r"pour y être l[uû]", r"publié, registre",
        r"registre, gardé, observé", r"desdites parties", r"desdits ouvrages",
        r"exemplaires desdit", r"de la daté d'icelles", r"de la date d'icelles",
        r"donné à (marly|fontainebleau|s\. germain|saint-germain|compiègne|paris)",
        r"donne'? à (marly|fontainebleau|s\. germain|saint-germain)",
        r"et de n(otre|ôtre|ostre) r[ée]gne", r"conclusions du procureur général",
        r"a ces cau?ses", r"lettres de privilege", r"lettres sur ce nécessaires",
        # --- added 16 Aug 2026 from the top-300 noise review -------------
        # The counter-seal. 'notre scel' and 'grand sceau' were here; the
        # counter-seal was not, and the OCR spaces the hyphen: the witness
        # reads 'ci-attaché fous le contre - scel de notre Chancellerie'.
        r"contre\s*-?\s*scel",
        # 'Chancellerie' is anchored, because the bare word appears in
        # ordinary historical prose about the chancery as an institution.
        r"de n(otre|ôtre|ostre) chancellerie",
        # The closing formula of every royal letter, and unmistakable.
        r"car tel est n(otre|ôtre|ostre) (bon )?plaisir",
        r"lettres à ce contraires",
        # The address and the sanction of letters patent.
        # 'A tous' as often as 'à tous': the preposition loses its accent in
        # period printing and in the OCR alike.
        r"[àa] tous (ceux )?(pr[eé]sens|qui ces pr[eé]sentes)",
        r"sinon (&|et) à faute de ce faire",
        r"foi de quoi nous (lui )?avons d[eé]livr[eé]",
        r"pour y [êe]tre ex[eé]cut[eé]",
        # Division of a fine among Crown, hospital and informer -- a fixed
        # tripartite formula, not a statement about anyone's charity.
        r"un tiers à nous",
        r"l'h[oô]tel[- ]dieu de paris",
        # The sovereign courts by name.
        # Loose whitespace around the comma: the witness reads
        # 'Cour des Comptes , Aides & Finances de Rouen'.
        r"cour des comptes\s*,?\s*(aides?|aydes)",
        # Anchored on the pair, not on 'prevost', because the OCR drops
        # characters between them: 'prevot f des marchands & eschevins'.
        r"marchands (&|et) [eé]?schevins",
        r"la cour faisant droit",
        r"requi[st]itoire du procureur g[eé]n[eé]ral",
        r"les gens du roi (sont|font) entr[eé]s",
        r"toutes les chambres assembl[eé]es",
        r"mis (&|et) met les parties hors de cour",
        # The drop capital is lost in scanning -- 'UR la Requête présentée'.
        r"s?ur la requ[êe]te pr[eé]sent[eé]e au roi",
        r"communauté des imprimeurs", r"bibliothèque publique",
        r"substituts? du procureur", r"exploits requis",
        r"extrait des registres", r"arrest de la cour",
        r"met l'appellation au néant", r"lecture à lui faite de sa dépo",
        r"contenir vérité", r"rien trouvé qui puisse en empêcher",
        r"délivré (ce|le) présent certificat", r"conseil d'etat du roi",
        r"chancelier ce manuscrit", r"publication des présentes",
        r"fassiez jouir", r"fassent consigner", r"ayans cause",
        r"changement de titres", r"fausses marques", r"suivant la feuille imprimée",
        r"feuille imprimée", r"pour modele", r"pour modèle",
        r"conformément à la feuille", r"nonobstant oppositions",
        r"sans préjudice", r"sans preiudice", r"certifier la cour",
        # Was a bare "expert", unanchored, which matched "expertia" in
        # Horace, Ars Poetica 341 ("centuriae seniorum agitant expertia
        # frugis") and so condemned group 1200000893 -- 213 rows, and one of
        # the native anchor groups other witnesses had been merged INTO all
        # session. Anchored, and restricted to the French noun.
        r"\bexperts?\b", r"parties conviendront", r"peine de nullité",
    ],
    "royal / noble / academic styles": [
        r"par la grâce de dieu",
        # `roi de france` measured 15.0% false positive: a designation,
        # not a claim -- Glenn's ruling on "les rois de la première et
        # seconde race" applies exactly. It caught Rousseau on the abbé de
        # Saint-Pierre and Louis XVI's testament. The chancery use is the
        # full titulature, which the compound forms below already model.
        r"ro[iy] de france (&|et) de navarre",
        r"empereur des romains", r"grand duc de lithuanie", r"prince du sang",
        r"chevalier des ordres", r"chevalier de l'ordre royal",
        # Hyphen allowed: the corpus prints both "Ordre Royal & Militaire"
        # and "l'Ordre-Royal & Militaire de St Louis".
        r"ordre[- ]royal & militaire",
        # "Chevalier de l'Ordre Militaire de St. Louis" -- abbreviated.
        r"militaire de s(ain)?t\.?[- ]louis",
        # RETAINED after the boiler10 review, 14 Aug 2026, having been
        # briefly removed on my mistaken objection.
        #
        # I argued that "les rois de la premiere et seconde race" should be
        # spared because Vauban, Le Vayer de Boutigny, Pierre Rival and La
        # Curne de Sainte-Palaye all use it while arguing the same question
        # -- the origins of French law, fiefs and nobility, the
        # Boulainvilliers/Dubos controversy. Glenn's ruling: that is a fact
        # about the AUTHORS, not about the alignment. What the match
        # actually contains is the dynastic designation and nothing else,
        # and two texts sharing a fixed label for the Merovingians and
        # Carolingians are not quoting one another. The argument lives in
        # the surrounding sentences, which is exactly what the matched span
        # does not include.
        #
        # The general test this settles: ask what the MATCHED SPAN carries,
        # not what the works containing it are about. A shared designation
        # is an honorific; a shared claim is reuse.
        r"de la premi[èe]re (&|et) (de la )?seconde race",
        r"lieutenant général de ses armées", r"conseiller du roy",
        r"conseil d'etat & privé", r"académie royale des", r"académie des sciences",
        r"société royale des sciences", r"doyen de la faculté",
        r"par la permission divine", r"duc d'orléans", r"sa majesté",
        # Added for modern_all_align. Its bulk is journals and the Mercure
        # galant, which print diplomatic titulature constantly: the
        # Grande-Bretagne style alone accounts for 64 groups and 1,922 rows.
        r"roi de la grande[- ]bretagne", r"reine de la grande[- ]bretagne",
        r"roi et reine de la grande", r"de france,? et d'irlande",
        r"de france (&|et) d'irlande", r"roi tr[èe]s[- ]chr[ée]tien",
        r"roy tr[èe]s[- ]chr[ée]tien",
    ],
    # ---------------------------------------------------------------------
    # The four registers below were derived from combined_align by
    # discover_boilerplate_registers.py, on the same evidence-first basis as
    # the gallica categories above. gallica is dictionaries, encyclopaedias
    # and legal texts; modern is journals, the Mercure galant, the Journal
    # des savants and academy proceedings, whose formulaic register the
    # gallica patterns saw almost nothing of.
    #
    # NOT included, deliberately: the "generic prose" population -- "à peu
    # près le même effet", "présenter sous un seul point de vue". Two
    # automatic measures were tried against it and both failed, each
    # condemning Boileau, the Marseillaise and Genesis, because a line
    # becomes quotable precisely by being built from ordinary words. That
    # population needs reading, not patterns. See the project summary.
    # ---------------------------------------------------------------------
    "court styles / approbation": [
        r"premier gentilhomme de la chambre", r"gentilhomme de la chambre",
        r"petit[- ]?fils de france", r"pair de france", r"premier pair de france",
        r"grand [ée]cuyer", r"maréchal de france", r"mar[ée]chal de france",
        # The approbation formula, printed in every privileged book:
        # "lû par ordre de Monseigneur le Chancelier un manuscrit qui a
        # pour titre ...". 163 groups, and none of it is anyone's prose.
        r"par ordre de monseigneur", r"monseigneur le chancelier",
        r"monseigneur le garde des sceaux", r"monseigneur le vice[- ]chancelier",
        r"tr[èe]s[- ]humble (&|et) tr[èe]s obéissant", r"de votre grandeur",
        r"commandeur de l'ordre", r"gouverneur (et|&) lieutenant général",
        # --- added 16 Aug 2026 from the top-300 noise review -------------
        # The censor's verdict, which every privileged book carries.
        r"rien (trouv[eé]|qui)\s.{0,24}emp[êe]cher l'impression",
        r"n'ai rien trouv[eé] qui",
        # The moral warrant an approbation asserts. Anchored on BOTH halves,
        # because the vice/virtue antithesis on its own is ordinary moral
        # prose and belongs to Racine as readily as to a censor -- and this
        # category has reached into scripture three times already.
        r"horreur (pour|du|de) le?\s?vice.{0,60}amour (pour|de) la vertu",
        r"amour (pour|de) la vertu.{0,60}horreur (pour|du|de) le?\s?vice",
        # Offices and household charges.
        r"capitaine de (la premi[èe]re compagnie|cent hommes)",
        r"gardes du corps", r"princes du sang",
        r"grands officiers de la couronne",
        r"chevalier de l'ordre du roi",
        # 'de Ces armées' -- the OCR reads C for long s.
        r"lieutenant g[eé]n[eé]ral de [cs]es arm[eé]es",
        # This read 'doyen|doct(eur|-régent) de la faculté de médecine', where
        # the alternation binds at the TOP level: a bare 'doyen' anywhere in
        # any passage would have condemned it. Exactly the unanchored-pattern
        # fault that caught 'expert' in Ars Poetica 341 and cost a native
        # Horace group of 213 rows. Split and anchored.
        r"(doyen|doct(eur|-?r[eé]gent)) de la facult[eé]",
        r"r[eé]gent de la facult[eé] de m[eé]decine",
        # 'Académie' is truncated in the witness: 'Royale des Inscriptions
        # & Belles-Lettres de Paris'.
        r"royale des inscriptions",
    ],
    "necrological / biographical notice": [
        # Deliberately narrow. The first draft used bare "né à" and "mort
        # à", which caught Malherbe's Consolation twice, plus Voltaire,
        # Rousseau and two Horace passages -- "mort à" is ubiquitous in
        # verse. These require the actual apparatus of a dictionary notice:
        # a place AND a year, or an explicit age, or the Encyclopédie's
        # "mort dans la même ville".
        r"n[ée]e? à [^,;.]{2,30}\s+en\s+\d{3,4}",
        r"mort(e)?\s+dans\s+la\s+m[êe]me\s+ville",
        # The gap allows for OCR junk between the number and "ans":
        # "âgé de 51 ) ans", "âgé de 57. ans" both occur.
        r"[âa]g[ée]e?\s+de\s+\d+[^a-zà-ÿ]{0,4}ans",
        # "mourut en" alone matched "elle mourut en donnant le jour à un gros
        # Garçon" in Gueullette's Contes mogols -- narrative, not a notice.
        # A dictionary notice always dates the death.
        r"mourut\s+(en|le)\s+\d",
        r"mourut\s+à\s+[^,;.]{2,25}\s+(en|le)\s+\d",
        r"n[ée]e?\s+en\s+\d{3,4}[^.]{0,20}mort",
        r"d[ée]c[ée]d[ée]e?\s+(en|à|le)\s",
    ],
    # ---------------------------------------------------------------------
    # Journal editorial commonplace -- added 14 Aug 2026, and worth its own
    # note because of how it was arrived at.
    #
    # This is the "generic prose" population that TWO automatic measures
    # failed on. A word-level IDF floor condemned Boileau's most-quoted line,
    # the Marseillaise and Genesis, because a line becomes quotable precisely
    # by being built from ordinary words. Word-3-gram template detection then
    # returned "il y a", "n est pas", "ce qu il" -- the commonest sequences
    # in French -- and was confounded by passage length. Both failed the same
    # way: they scored properties of the passage's own vocabulary.
    #
    # The top5 review settled it by judgement instead. Fifteen of the fifty-
    # three groups Glenn flagged NOISE were one frame, roughly 2,000 rows:
    #
    #   "produiroit a peu pres le mesme effet"   "fait a peu pres le mesme effet"
    #   "font a peu pres de la meme nature"      "arriver a peu pres dans le meme tems"
    #   "concues a peu-pres dans les memes termes"  "tient a peu pres le meme langage"
    #   "porte a peu pres le meme jugement"      "parle a peu pres dans les memes termes"
    #
    # Once adjudicated, the frame is an ordinary explicit pattern, no
    # different from "tel est nostre plaisir". The judgement was the hard
    # part; the regex is trivial. That is the lesson worth keeping: where an
    # automatic measure fails twice, the answer may be to ask the reviewer
    # once rather than to invent a third measure.
    #
    # Both halves of the frame are required within a short window, because
    # "a peu pres" alone is ordinary French and appears in argument as well
    # as in filler.
    # ---------------------------------------------------------------------
    # NOTE ON EARLY-MODERN ORTHOGRAPHY. The first draft of these patterns
    # wrote "m[êe]mes?" and "peut[- ]?[êe]tre", and missed "le MESME effet"
    # and "peut-ESTRE bien aise" -- the seventeenth-century s that the
    # circumflex later replaced. Anything in this module matching a common
    # French word needs the s-form: m[êe]s?mes?, [êe]s?tre, and so on.
    "journal editorial commonplace": [
        # The two halves must sit in the SAME clause and close together. A
        # first draft allowed 45 characters of anything between them, and
        # its own test case caught it: "a peu pres tout ce qu'il avance est
        # contestable, et le meme auteur se contredit ailleurs" is ordinary
        # argument, not filler. 22 characters, no sentence boundary.
        r"[àa][- ]peu[- ]?pr[èe]s[^.;]{0,22}\bm[êe]s?mes?\b",
        r"\bm[êe]s?mes?\b[^.;]{0,22}[àa][- ]peu[- ]?pr[èe]s",
        r"[àa] peu de choses pr[èe]s",
        # "point de vue" is ordinary; the presentational frame is not.
        # OCR renders "sous" as "fous" throughout this corpus.
        # \W{0,3} between the qualifier and "point": the corpus prints
        # 'fous un certain "point de vue' with a stray ASCII quote, which
        # prepare() does not fold (it handles the typographic quotes only).
        r"[sf]ous (un |le |ce )?(seul|certain|m[êe]s?me|autre|nouveau)\s*\W{0,3}\s*point de vue",
        r"point de vue [sf]ous lequel",
        r"rapprocher,? [sf]ous un m[êe]s?me",
        # The reviewer's polite hedge, four groups in the top 100.
        # "peut - estre" with spaces around the hyphen occurs; so does
        # "bien-aise" hyphenated.
        r"(sera|fera)\s+peut\s*[- ]?\s*[êe]s?tre\s+(pas\s+)?(bien\s*[- ]?\s*)?(aise|f[âa]ch[ée])",
        r"(ne\s+)?(sera|fera)\s+pas\s+hors\s+de\s+propos",
        # "Voila, a peu pres, ce que l'on peut dire" -- the summing-up frame,
        # which carries no "meme" and so escaped the pair patterns above.
        r"voil[àa],? [àa][- ]peu[- ]?pr[èe]s",
        # "sera bien aise de trouver ici" -- the hedge without "peut-etre".
        r"(sera|fera),? (bien )?aise de (trouver|voir|s[çc]avoir|apprendre)",
        # Periodical coverage statements.
        # NARROWED 14 Aug 2026, boiler10 review. The previous form,
        #     r"pendant les (trois |quinze |premiers? )?(mois|jours) d",
        # allowed 'jours' and required nothing after the 'd', so it condemned
        # group 1200005074 -- Ecclesiastes 12:1 in La Sainte Bible,
        # "Souviens-toi de ton Créateur PENDANT LES JOURS DE ta jeunesse".
        # Same failure as the Boileau, Marseillaise and Genesis cases: a
        # pattern written for one register reaching into scripture.
        # What was actually intended is the journal date-range formula, which
        # always enumerates named months, so the month name is now required.
        # The character class after the 'd' is deliberately loose: this text
        # is OCR, and the elision appears as d', d’, d" and bare d across the
        # boiler10 listing alone. The month name that follows is what makes
        # the pattern safe, so the elision does not need to be.
        r"pendant les (trois |quinze |premiers? )?mois d[eu'’\"\.]{0,2}\s*"
        r"(janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[ûu]s?t|"
        r"septembre|octobre|novembre|d[ée]cembre)",
    ],
    "chronological / dating formula": [
        r"avant\s+(la\s+naissance\s+de\s+)?j[ée]sus[- ]?christ",
        r"avant\s+j\.?\s?c\b", r"[èe]re\s+chr[ée]tienne",
        r"de\s+l'[èe]re\s+(chrétienne|vulgaire)",
        r"l'an\s+de\s+(gr[âa]ce|rome)",
        r"depuis\s+la\s+création\s+du\s+monde",
    ],

    "edition statements / bibliographic citation": [
        r"nouvelle édition", r"seconde édition", r"revûë, corrigée", r"revue, corrigée",
        r"considérablement augmentée", r"dictionnaire raisonné des sciences",
        r"collection choisie", r"ornés de figures", r"collection académique",
        r"composée des mémoires", r"nouvelle collection de toutes les relations",
    ],
    "bookseller / printer imprints": [
        r"\brue (s\.|saint|neuve|s\b|pavée|plâtrière|plātrière)",
        # "chez" is ordinary French ("chez les Romains", "chez M. Fouquet"),
        # so it only counts as an imprint when it sits next to a trade word,
        # a place of publication, or a street.
        r"à paris, chez", r"a paris, chez", r"\bchez\b[^.]{0,40}\b(libraire|imprimeur|veuve)",
        r"\bchez\b[^.]{0,30}\brue\b", r"\bchez\b[^.]{0,30}\bquai\b",
        # "au coin d" alone matched "au coin de son feu". An imprint address
        # names a street.
        r"au coin de la rue", r"au coin des rues", r"au coin du quai",
        # A bare "\\blibraire\\s*[,.]" matched "M. Becket, Libraire, dit à M.
        # Rousseau" -- a bookseller as a character in narrative rather than in
        # an imprint. The imprint forms below all anchor him to a place.
        # A bare "\\blibraire\\s*[,.]" matched "M. Becket, Libraire, dit a M.
        # Rousseau" -- a bookseller as a character in narrative. But the first
        # replacement required "rue" immediately after and took the category
        # from 5,037 groups to 111: an imprint names an address in many ways
        # ("Libraire, quai des Augustins", "Libraires, au Palais", "Libraire,
        # vis-a-vis le College"). So: anchor to an ADDRESS WORD within a short
        # window, rather than to one word in one position.
        r"libraires?\b[^.]{0,25}\b(rue|quai|place|pont|palais|coll[èe]ge|"
        r"cloître|march[ée]|faubourg|vis-[àa]-vis|au coin|pr[èe]s d)",
        r"libraires?,? (à|a) paris", r"imprimeur (du|de la|ordinaire)",
        r"libraire[- ]imprimeur", r"libraires? associ[ée]s",
        r"chez les libraires",
        # "se trouve chez" alone is ordinary French -- "cette qualité se
        # trouve chez tous les hommes" -- and caught a passage on Homer and
        # another on the acids of Javel. An imprint says where the book is to
        # be had, so require a trade word or an address after it.
        r"se trouve[^.]{0,20}chez[^.]{0,40}\b(libraire|imprimeur|rue|quai|palais)",
        r"\bquai (des|de|d')", r"quai des augustins", r"\bhôtel de\b.*\brue\b",
    ],
    "measurement / tabular / index fragments": [
        r"degrés? \d", r"degrez", r"\d+ degrés", r"pouces \d+ lignes",
        # "3. pouces de haut" -- the period defeated a bare "\d+ pouces".
        r"\d+\s*\.?\s*pouces", r"\d+\s*\.?\s*toises", r"\btoises\b",
        r"livres tournois", r"thermomètre", r"baromètre",
        r"\bp\. \d+.*\bp\. \d+", r"^\W*[\d\s.,;:%°]+\W*$",
        r"florins de hollande", r"\d+ minutes de longitude", r"de longitude",
        r"de latitude", r"sols la livre", r"le cent pesant",
    ],
}

# One compiled regex per category, plus a combined one.
COMPILED = {name: re.compile("|".join(pats), re.I) for name, pats in CATEGORIES.items()}
ANY = re.compile("|".join(p for pats in CATEGORIES.values() for p in pats), re.I)

# Passages that are pure OCR wreckage: a short token repeated, or nothing
# but punctuation and digits. Treated as its own category.
GARBAGE = re.compile(r"^(?:\W*(\w{1,3})\W+)(?:\1\W+){3,}|^[\W\d\s]+$")


# Passages that must never be classified as boilerplate, whatever else they
# match. These are canonical texts that happen to contain administrative
# vocabulary -- the Declaration speaks of "la loi" and "le citoyen", the
# civic oath of "la nation, à la loi et au roi", and Racine's Athalie of
# kings. Checked before the category patterns.
NEVER = re.compile("|".join([
    r"naissent et demeurent libres",
    r"distinctions sociales",
    r"utilité commune",
    r"libre communication des pensées",
    r"expression de la volonté générale",
    # Declaration Article 11's second half contains "imprimer", which sits
    # next door to the privilege vocabulary; named explicitly so widening
    # that category later cannot reach it.
    r"écrire, imprimer librement",
    r"imprimer librement",
    r"abus de cette liberté",
    r"souveraineté réside",
    r"nul corps, nul individu",
    # Declaration Article 7. Found classified as chancery boilerplate by
    # the bare "arrêt" pattern, which matches "arrêté" -- exactly the risk
    # accepted when that pattern was restored. The article is a canonical
    # text that happens to use the vocabulary of arrest.
    r"accusé, arrêté",
    r"ni détenu que dans les cas",
    r"peut être accusé",
    r"arrêté ni détenu",
    r"droits naturels et imprescriptibles",
    r"allons enfans de la patrie",
    r"qu'un sang impur",
    r"formez vos bataillons",
    r"ça ira",
    r"met un fr[ae]in à la fureur des flots",
    r"mèt un frain",
    r"l'oeil n'a point vu",
    r"oeil n'a point vu",
    r"lierez en la terre",
    r"lieras en terre",
    r"delierez en la",
    r"clefs du royaume",
    r"peindre la parole",
    r"ames bien nées",
    r"bonne renommée",
    r"charité bien ordonnée",
    # Verse and burlesque caught by the chancery patterns in review of
    # boilerplate_review.txt. Scarron's is the instructive case: it is a
    # parody OF the royal style, so it necessarily reproduces the formula
    # it mocks and no amount of pattern-tuning would separate the two.
    r"scarron par la grâce de dieu",
    r"n'ayant ni feu ni lieu",
    r"arrêt du ciel",
    r"il faut que l'homme meure",
    r"vertu du vieux caton",
    r"de falerne",
    r"dieu des vers",
    r"poëtes stériles",
    r"s'éleve un temple obscur",

    # -------------------------------------------------------------------
    # Added 13 Aug 2026, before the modern registers below were written.
    # Every entry here is a passage that the FIRST draft of one of those
    # registers actually caught in discover_boilerplate_registers.py.
    # -------------------------------------------------------------------

    # Malherbe, Consolation à M. du Périer -- caught TWICE (600001655,
    # 300006690) by a bare "mort à" in the necrological register. This is
    # the reference text the reviewer supplied by hand, and the one group
    # in the corpus recorded as native_damaged. It is exactly the passage
    # a necrological pattern must never touch, since a consolation poem is
    # *about* a death and shares all its vocabulary.
    r"mort a des rigueurs",
    r"nulle autre pareilles",
    r"on a beau la prier",
    r"la cruelle qu'elle est",
    r"se bouche les oreilles",
    r"barri[èe]res du louvre",
    r"le chaume le couvre",
    r"sujet à ses loi",

    # Ossian by way of Prévost (900133199), caught by royal titulature.
    r"fille du ciel",
    r"silence de ta face",

    # The largest hot=0 groups from find_template_families.py -- verified
    # canonical, and short enough that a future widening could reach them.
    r"rien n'est beau que le vrai",
    r"le vrai seul est aimable",
    r"forçons point notre talent",
    r"ferions rien avec grâce",
    r"arbre de la science du bien",
    r"nul n'aura d'esprit hors nous",
    r"perdre impunément de l'encre",

    # Verse caught by the first draft of the necrological register.
    r"nouveau labeur à tes armes",
    r"plus ces cheveux",
    r"beauté qui me rendit",
]), re.I)


# ---------------------------------------------------------------------------
# Length guard.
#
# source_passage in this corpus is not always quotation-length. Group
# 1500112697 -- Gueullette, Les Sultanes de Guzarate -- carries a passage of
# 20,450 characters: a table of contents followed by two entire Contes
# mogols. It was condemned as a necrological notice because somewhere in
# those twenty thousand characters a woman "mourut en donnant le jour".
#
# That is not a pattern problem, it is a scale problem. Every formula in
# this module is between roughly 40 and 300 characters, and the longest
# genuine boilerplate seen in any review is under 500. Above a few thousand
# characters, a single pattern hit carries almost no information: a long
# enough text contains everything.
#
# So above MAX_CLASSIFY_LEN, classification requires corroboration -- at
# least MIN_HITS_LONG distinct categories must match, not one. That keeps
# the genuinely long privilege texts (which hit chancery patterns many times
# over) while sparing a novel that mentions a death once.
MAX_CLASSIFY_LEN = 2000

# MIN_HITS_LONG required N distinct CATEGORIES before classifying a long
# passage. That was wrong in kind, not merely mistuned, and Morand's memoir
# on the mineral waters of Saint-Amand (900069778, 29,536 chars) showed why.
# It hit three categories and was duly condemned:
#
#     necrological   "une fille agee de 20 ans" -- a patient in a case history
#     commonplace    "rassemble sous un meme point de vue" -- ordinary prose
#     measurement    "14 degres", "5 toises", "thermometre" -- he is a
#                    physician MEASURING things
#
# Requiring N categories assumes the categories are independent evidence.
# They are not. A long scientific text hits measurement because it measures,
# necrological because case histories give ages, and the commonplace frame
# because it is prose. Length buys accidental hits at no cost.
#
# Density is the honest test. Boilerplate is boilerplate throughout: a
# privilege act matches a dozen patterns in three thousand characters. A
# treatise matches a handful in thirty thousand.
#
#     Morand, memoir on mineral waters     6 matches / 29,536 chars = 0.20
#     Maupertuis, Lettre sur la comete     3 / 43,614              = 0.07
#     d'Holbach, Politique naturelle       1 / 129,904             = 0.01
#     a genuine long privilege act        ~15 / 3,207              = 4.7
#
# Matches are counted per PATTERN, not per category, so a text saturated in
# chancery formula scores high even though it occupies one category.
MIN_HITS_LONG = 3          # retained for callers that pass it explicitly
MIN_DENSITY_LONG = 1.0     # RETIRED, 21 Aug 2026 -- kept only for the history
                            # and for any caller passing it explicitly. See
                            # the fix note at the floor selection in inspect().

# UNIFIED across all lengths as of 21 Aug 2026 -- see the fix note below
# MIN_DENSITY_LONG. Originally applied at every length below
# MAX_CLASSIFY_LEN only, with MIN_DENSITY_LONG taking over above it.
# Glenn, 18 Aug 2026: "the smaller the passage the easier it is to
# condemn." Fitted to 158 adjudicated rows -- median density 16.4 when
# the condemnation was sound against 3.3 when it was wrong, while the
# raw match COUNT is 1 in both cases -- then validated against 37,412
# independently labelled reuses.
#
# SET AT 6.5, NOT THE 12.0 THE FIT SUGGESTED, because two kinds of
# evidence disagree and the disagreement is worth recording rather than
# resolving silently.
#
#   Martial's labels prefer 10.0 or above, where the measured false-
#   positive rate is exactly zero. At 6.0 it is 6 rows in 3,879
#   condemnations -- 0.15% -- for 4.7% of confirmed noise reached.
#
#   test_boilerplate_patterns.py fails at 7.0 and above, on La Curne de
#   Sainte-Palaye's "de la première & de la seconde Race" -- 152
#   characters, one match, density 6.58 -- which Glenn ruled explicitly in
#   round 10 IS to be condemned: "a shared designation is an honorific; a
#   shared claim is reuse."
#
# The harness wins, because the floor is no longer load-bearing. It was
# adopted to stop single-match condemnations of canonical text, and the
# case that motivated it -- Declaration Article 7 -- now scores ZERO
# pattern matches once `arrêt` is narrowed. The regex fixes do that work
# precisely; the density floor did it bluntly, and bluntness costs the
# dynastic designations the harness exists to protect.
#
# RE-MEASURE AFTER THIS LANDS. Every false-positive figure above was
# measured BEFORE the four narrowings, so the curve moves. If 6.5 proves
# expensive on the new measurement, the better fix is not a higher floor
# but exempting DESIGNATION patterns -- where one match is conclusive by
# construction, as with OCR garbage -- rather than lowering precision
# everywhere to accommodate them.
MIN_DENSITY = 6.5

# Below this a passage is too short for density to say anything: one match
# in 25 characters is 40 per 1,000 and clears any floor -- correctly, since
# such a span IS the formula. Said out loud rather than left to fall out of
# the arithmetic.
DENSITY_FLOOR_LEN = 25

# Above this, the classifier DECLINES rather than judging. Not a threshold
# to be tuned -- a statement about what this module is for.
#
# Every pattern here describes a formula of roughly 40 to 500 characters: a
# privilege clause, a court style, a decree preamble. The longest genuine
# boilerplate act seen in any review is about 3,000. Asking whether a
# 29,354-character text "is boilerplate" is a category error: parts of it
# might be, the whole never is.
#
# A passage this long is not a quotation either. Nobody quotes a chapter.
# It means two DOCUMENTS share a chunk of text -- Du Halde's Formosa chapter
# reappearing in Prevost's Histoire generale des voyages, the Encyclopedie
# absorbing the Art du tailleur, Raynal carried into Mentelle's school
# reader. That is document-level reuse, a different phenomenon from a
# witness citing a line of Horace, and it wants its own treatment rather
# than a verdict from an instrument built for quotations.
#
# Every serious false positive of 13-14 Aug 2026 was a long passage:
#   1200000893  Horace, Ars Poetica       579 chars   "expert" in "expertia"
#   1500112697  Gueullette, Contes mogols  20,450     "mourut en donnant le jour"
#   1500133533  Maupertuis, la comete      43,614     "avant Jesus-Christ", "degres"
#   900069778   Morand, eaux minerales     29,536     "agee de 20 ans" + measurement
#   11200243420 d'Holbach, Politique nat. 129,904     one chancery pattern
#   1500118525  Du Halde, la Chine         29,354     "privilege" -- of Formosan
#                                                     islanders, granted for
#                                                     excellence at the chase
NEVER_CLASSIFY_ABOVE = 10000


# Every individual pattern, kept flat so density can be measured per pattern
# rather than per category.
_FLAT = [(name, re.compile(p, re.I)) for name, pats in CATEGORIES.items() for p in pats]


def inspect(passage, max_len=MAX_CLASSIFY_LEN, min_hits_long=MIN_HITS_LONG,
            min_density=MIN_DENSITY_LONG, min_density_short=MIN_DENSITY):
    """Full account of the classification decision, for callers that need to
    do something other than delete.

    Returns a dict:
        length        len(prepare(passage))
        never         True if NEVER matched (canonical, protected)
        hits          list of category names whose patterns matched
        category      the category to act on, or None
        spared_long   True if a match was OVERRULED by the length guard
        extended      True if the passage is document-level reuse rather
                      than a quotation (over NEVER_CLASSIFY_ABOVE chars),
                      in which case the classifier declined outright

    spared_long is the interesting one. Those passages DID match a pattern
    and are not being deleted only because they are too long for one hit to
    mean anything. They are not "clean" -- they are unadjudicated, and they
    deserve their own review rather than being folded back into the great
    mass of unmatched groups where nobody will ever look at them again.
    """
    out = dict(length=0, never=False, hits=[], category=None, spared_long=False,
               extended=False, matches=0, density=0.0, spared_sparse=False)
    if not passage:
        return out
    s = prepare(passage)
    out["length"] = len(s)
    if NEVER.search(s):
        out["never"] = True
        return out

    hits = [name for name, rx in COMPILED.items() if rx.search(s)]
    out["hits"] = hits
    if not hits:
        if GARBAGE.search(s):
            out["category"] = "OCR garbage"
        return out

    if len(s) > NEVER_CLASSIFY_ABOVE:
        # Document-level reuse, not a quotation. The classifier declines.
        out["spared_long"] = True
        out["extended"] = True
        return out

    # Density at EVERY length. Previously computed only above max_len, so a
    # 60-character coordinate string and a 300-character narrative containing
    # one coordinate were condemned on identical evidence.
    n = sum(1 for _, rx in _FLAT if rx.search(s))
    density = n * 1000.0 / len(s)
    out["matches"] = n
    out["density"] = round(density, 3)

    # FIX, 21 Aug 2026 (docket item, sweep_density_floor.py): the floor is
    # now ONE VALUE AT EVERY LENGTH, not a step at MAX_CLASSIFY_LEN. The
    # shipped rule was 6.5 below 2,000 characters and 1.0 above it, so the
    # same density was condemned at 2,001 chars and spared at 1,999 --
    # non-monotonic in length, and nobody chose it, two thresholds meeting
    # badly. `sweep_density_floor.py` scored the unified floor against the
    # two-step one over the 120,542-row labelled set: 3,637 condemned (2
    # OUI, 0.05% FP, 4.4% recall) against the shipped rule's 3,640 (2 OUI,
    # 0.05% FP, 4.4% recall) -- a difference of 3 rows, all previously
    # condemned only by the laxer long-passage floor. See density_sweep.txt
    # for the full curve. MIN_DENSITY_LONG is retired; the argument that
    # motivated it (Morand's memoir at density 0.20, a genuine privilege
    # act at 4.7) is subsumed by density being the honest test at every
    # length, not just below 2,000 characters.
    floor = min_density_short
    if len(s) >= DENSITY_FLOOR_LEN and density < floor:
        out["spared_long"] = len(s) > max_len
        out["spared_sparse"] = True
        return out

    # Preserve the original precedence: first category in CATEGORIES order.
    for name in COMPILED:
        if name in hits:
            out["category"] = name
            break
    return out


def classify(passage, max_len=MAX_CLASSIFY_LEN, min_hits_long=MIN_HITS_LONG,
             min_density=MIN_DENSITY_LONG, min_density_short=MIN_DENSITY):
    """Return a category name, 'OCR garbage', or None if not boilerplate.

    Matching runs against prepare(passage) so that typographic apostrophes
    and OCR ampersand variants do not defeat the patterns.

    A passage must clear min_density_short matches per 1,000 characters,
    ONE FLOOR AT EVERY LENGTH as of 21 Aug 2026 (see the fix note at the
    floor selection in inspect()); min_hits_long and max_len are retained
    for callers that still pass them explicitly but no longer change the
    verdict. Passages over NEVER_CLASSIFY_ABOVE characters are declined
    outright as document-level reuse rather than a quotation. Callers that
    want to SEE the evidence, rather than merely get a verdict, should use
    inspect().
    """
    return inspect(passage, max_len, min_hits_long, min_density,
                   min_density_short)["category"]


def is_boilerplate(passage):
    return classify(passage) is not None
