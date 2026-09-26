"""Credit ratings from NSE rating filings (Reg 30 `Credit Rating*` announcements): rule-based
extraction of each agency's current rating from the filing PDF text (scanner/kpis.pdf_text).

A filing names the rating as `<agency prefix> <grade>` — `[ICRA]AA-`, `CRISIL A1+`, `CARE BB+`,
`IND AA`, `ACUITE A-`, `BWR AAA`, `IVR BBB-` — usually in the covering letter's table, then again
in the enclosed agency letter, its rating history and its glossary. So only the FIRST rating per
(agency, term) in a filing is kept: in every layout seen (incl. "Current | Previous" tables) that
is the current one. Global agencies (Fitch / S&P / Moody's) state it in prose ("affirmed … at
'BBB-'"). Structured / credit-enhanced paper (`(SO)`, `(CE)`) is not the company's own credit and
is skipped. Every row keeps its exact quote. Precision over recall: a filing that yields nothing
is marked `no_rating` by scripts/extract_ratings.py, not guessed.
"""
from __future__ import annotations

import re

SCAN_CHARS = 20000   # covering letter + the agency letter's first pages; glossaries sit further on

_LT_SCALE = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-",
             "B+", "B", "B-", "C+", "C", "C-", "D"]
_LT = {g: i for i, g in enumerate(_LT_SCALE, 1)}
_LT.update({"CCC+": 17, "CCC": 18, "CCC-": 19, "CC": 19, "RD": 20,                  # S&P / Fitch
            "Aaa": 1, "Aa1": 2, "Aa2": 3, "Aa3": 4, "A1": 5, "A2": 6, "A3": 7,       # Moody's
            "Baa1": 8, "Baa2": 9, "Baa3": 10, "Ba1": 11, "Ba2": 12, "Ba3": 13,
            "B1": 14, "B2": 15, "B3": 16, "Caa1": 17, "Caa2": 18, "Caa3": 19, "Ca": 19})
_ST = {g: i for i, g in enumerate(["A1+", "A1", "A2+", "A2", "A3+", "A3", "A4+", "A4", "D"], 1)}


def notch(rating: str, term: str) -> int | None:
    """1 = best. Long-term AAA..D = 1..20 (global scales mapped onto it); short-term A1+..D = 1..9."""
    return (_ST if term == "short" else _LT).get(rating)


_AGENCY = {"ICRA": "ICRA", "CRISIL": "CRISIL", "CARE": "CARE", "IND": "India Ratings", "LND": "India Ratings",
           "ACUITE": "Acuite", "BWR": "Brickwork", "IVR": "Infomerics"}
# [ICRA]AA- | CRISIL/Crisil AA- | CARE A1+ | IND AA | ACUITE A- | BWR AAA | IVR BBB-  ("lND": an l for
# the I in some PDFs' fonts)
_TOKEN = re.compile(
    r"(?:\[\s*(?P<bpfx>ICRA|CRISIL|CARE)\s*\]\s*|\b(?P<pfx>CRISIL|Crisil|ICRA|CARE|IND|lND|ACUIT[EÉ�]|BWR|IVR)\s+)"
    r"(?:(?P<st>A\s?[1-4l]\s?\+?)(?![\w+])|(?P<lt>AAA|AA|A|BBB|BB|B|C|D)(?P<sign>[+-]?)(?![\w+])"
    r"(?!\s+(?i:one|two|three|four|plus|minus)\b))"         # "Crisil A one plus": a spelled-out duplicate
    r"(?:\s*\(\s*(?P<sfx>CE|SO)\s*\))?")
_FROM = re.compile(r"\bfrom\s*['‘’\"“”]?\s*$", re.I)
_Q = r"['‘’\"]?"
_OUTLOOK = re.compile(rf"\s*{_Q}\s*(?:[/;|,]\s*)?{_Q}\s*\(?\s*(?:Outlook\s*:?\s*|with\s+(?:an?\s+)?)?"
                      r"(Stable|Positive|Negative|Developing)\b", re.I)
# "Bank of India (BoI, CARE AA+; Stable / CARE A1+)": another entity's rating named in passing
_THIRD_PARTY = re.compile(r"\([^()]{0,30},[^()]*$")
_PREV_COLUMN = re.compile(r"previous\s+ratings?", re.I)
_WATCH = re.compile(r"watch\s+with\s+(positive|negative|developing)\s+implication|\bRW(P|N|D)I?\b|"
                    r"^\s*/\s*Watch\s+(Positive|Negative|Developing)\b", re.I)
_REMOVED = re.compile(r"removed\s+from\s+(?:the\s+)?rating\s+watch", re.I)
_ACTIONS = [("upgraded", r"upgrad"), ("downgraded", r"downgrad"), ("withdrawn", r"withdra"),
            ("watch", r"placed\s+(?:on|under)\s+(?:the\s+)?rating\s+watch"), ("reaffirmed", r"affirm"),
            ("assigned", r"assign"), ("revised", r"revis")]
_FILING_ACTION = re.compile(r"\bhas\s+(?:\w+\s+){0,3}?(upgraded|downgraded|reaffirmed|affirmed|assigned|withdrawn|"
                            r"revised|placed)\b", re.I)
_WINDOW = 220

# global agencies: "Fitch … affirmed … IDR at BB+ (Outlook: Stable)", "Moody's … upgraded … to Baa3"
# "(a Fitch Group Company)" is India Ratings describing itself, not a Fitch rating
_GLOBAL_AGENCY = re.compile(r"\b(Fitch|FITCH|S&P|Standard (?:&|and) Poor['’]?s|Moody['’]?s|MOODY['’]?S|"
                            r"Japan Credit Rating Agency|CareEdge Global)\b(?!\s+Group)")
_G = r"AAA|AA[+-]?|A[+-]?|BBB[+-]?|BB[+-]?|B[+-]?|CCC[+-]?|Aaa|Aa[1-3]|A[1-3]|Baa[1-3]|Ba[1-3]|B[1-3]|Caa[1-3]"
_MOODYS = re.compile(r"Aaa|Aa[1-3]|A[1-3]|Baa[1-3]|Ba[1-3]|B[1-3]|Caa[1-3]")
_OUTLOOK_WORD = r"(?i:stable|positive|negative|developing)"
# "at 'BBB-'", "to Baa3 with", "ratings (Baa3 stable)", a table cell "BB-/Stable", or quoted "its 'BBB'"
_GLOBAL_GRADE = re.compile(
    rf"(?:\b(?:at|to|of|as)\s+|\(\s*)['‘’\"]?(?P<g>{_G})['’\"]?(?![\w+-])"
    rf"(?=\s*(?:['’\"),.;/(]|with\b|and\b|rating\b|outlook\b|{_OUTLOOK_WORD}\b|$))"
    rf"|\b(?P<g2>{_G})(?=/{_OUTLOOK_WORD}\b)"
    rf"|['‘](?P<g3>{_G})['’]"
    rf"|\bRatings?\s+(?P<g4>{_G})(?![\w+-])")               # a table's rating column: "Credit Rating Baa1"
_GRADE_GROUPS = ("g", "g2", "g3", "g4")
_GLOBAL_FROM = re.compile(rf"\bfrom\s+['‘’\"]?({_G})['’\"]?(?![\w+-])")
_GLOBAL_OUTLOOK_NEXT = re.compile(r"\s*['’\"]?\s*[(/]?\s*(Stable|Positive|Negative|Developing)\b", re.I)
_GLOBAL_OUTLOOK = re.compile(r"Outlook\s*:?\s*(Stable|Positive|Negative|Developing)|"
                             r"(Stable|Positive|Negative|Developing)\s+Outlook", re.I)
GLOBAL_SCAN_CHARS = 5000
# best notch an Indian issuer plausibly holds: India is BBB (S&P) / BBB- (Fitch) / Baa3 (Moody's) /
# A- (JCR), and the strongest corporates sit up to ~3 notches above (Infosys S&P A-, Sun Pharma Baa1)
_SOVEREIGN_CEILING = {"S&P": 7, "Fitch": 7, "Moody's": 7, "CareEdge Global": 7, "JCR": 6}
_PREV_FIRST = re.compile(r"previous\s+ratings?.{0,80}?(?:current|revised|present|new)\s+ratings?", re.I)


def _action(text: str) -> str | None:
    """The first rating verb after the grade (a later one belongs to the next table row); an
    outlook "revised" counts only when no other verb is there."""
    hits = [(m.start(), name) for name, pat in _ACTIONS if (m := re.search(pat, text, re.I))]
    firm = [h for h in hits if h[1] != "revised"]
    return min(firm or hits)[1] if hits else None


def _third_party(before: str) -> bool:
    """The grade sits inside an unclosed "(<entity>, …" aside; closed inner groups such as
    "(CE)" are dropped first so they can't end the aside."""
    prev = None
    while prev != before:
        prev, before = before, re.sub(r"\([^()]*\)", "", before)
    return bool(_THIRD_PARTY.search(before))


def _resolve(row: dict, filing_action: str | None) -> dict:
    """A watch with no other verb is the action, else the covering letter's verb; a known
    previous rating decides up / down."""
    if row["action"] is None:
        row["action"] = filing_action or ("watch" if row["watch"] else None)
    old, new = notch(row["prev_rating"] or "", row["term"]), row["notch"]
    if old and new and old != new:
        row["action"] = "upgraded" if new < old else "downgraded"
    elif old and old == new and row["action"] in ("upgraded", "downgraded"):
        row["action"] = "reaffirmed"   # same grade: the "upgrade" was the outlook's
    return row


def _tokens(t: str) -> list[dict]:
    """Every agency-prefixed grade, minus structured / guaranteed paper and third parties'."""
    toks, ce_end = [], -100
    for m in _TOKEN.finditer(t):
        if m["sfx"]:
            ce_end = m.end()
            continue
        # the other leg of a guaranteed rating ("CARE AAA (CE); Stable / CARE A1+")
        if m.start() - ce_end < 30 and re.search(r"/\s*$", t[ce_end:m.start()]):
            continue
        if _third_party(t[max(0, m.start() - 120):m.start()]):
            continue
        pfx = (m["bpfx"] or m["pfx"]).upper().replace("É", "E").replace("�", "E")
        term = "short" if m["st"] else "long"
        # "Al+": an l for the 1 in some PDFs' fonts
        grade = re.sub(r"\s", "", m["st"]).upper().replace("L", "1") if m["st"] else m["lt"].upper() + m["sign"]
        if notch(grade, term) is None:
            continue
        toks.append({"m": m, "agency": _AGENCY[pfx], "term": term, "rating": grade,
                     "prev": bool(_FROM.search(t[max(0, m.start() - 25):m.start()])), "col_prev": None})
    return toks


def _pair_previous_column(t: str, current: list[dict]) -> list[dict]:
    """In a "Current | Previous rating" table the grade right after the current one (same agency
    and term) is its previous rating — or before it, when the header puts Previous first; a
    repeat of the same grade is the spelled-out echo."""
    header = t[:current[0]["m"].start()] if current else ""
    if not _PREV_COLUMN.search(header):
        return current
    prev_first = bool(_PREV_FIRST.search(header))
    out, i = [], 0
    while i < len(current):
        k, j = current[i], i + 1
        while (j < len(current) and (current[j]["agency"], current[j]["term"]) == (k["agency"], k["term"])
               and current[j]["m"].start() - k["m"].end() < 200):
            if current[j]["rating"] != k["rating"]:
                if prev_first:
                    current[j]["col_prev"], k = k["rating"], current[j]
                else:
                    k["col_prev"] = current[j]["rating"]
                j += 1
                break
            j += 1
        out.append(k)
        i = j
    return out


def _domestic(t: str, filing_action: str | None) -> list[dict]:
    toks = _tokens(t)
    current = _pair_previous_column(t, [k for k in toks if not k["prev"]])
    out, seen = [], set()
    for i, k in enumerate(current):
        m = k["m"]
        nxt = current[i + 1]["m"].start() if i + 1 < len(current) else len(t)
        end = min(nxt, m.end() + _WINDOW)
        window = t[m.end():end]
        key = (k["agency"], k["term"])
        if key in seen:
            continue
        seen.add(key)
        ol = _OUTLOOK.match(t, m.end())
        prev = k["col_prev"] or next((p["rating"] for p in toks if p["prev"] and m.end() <= p["m"].start() < end
                                      and p["agency"] == k["agency"] and p["term"] == k["term"]), None)
        w = _WATCH.search(window)
        watch = None
        if w and not _REMOVED.search(window[:w.start() + 40]):
            code = {"P": "positive", "N": "negative", "D": "developing"}
            watch = (w[1] or w[3] or code[w[2].upper()]).lower()
        out.append(_resolve({
            "agency": k["agency"], "scale": "domestic", "term": k["term"], "rating": k["rating"],
            "notch": notch(k["rating"], k["term"]), "outlook": ol[1].title() if ol and k["term"] == "long" else None,
            "watch": watch, "action": _action(window), "prev_rating": prev,
            "quote": t[m.start():end].strip()[:300]}, filing_action))
    # a defaulted issuer has no live short-term rating: an A1 beside a long-term D is history
    defaulted = {r["agency"] for r in out if r["term"] == "long" and r["rating"] == "D"}
    return [r for r in out if not (r["term"] == "short" and r["agency"] in defaulted and r["rating"] != "D")]


def _fits(t: str, m: re.Match, agency: str) -> bool:
    """A grade on this agency's own scale, within the sovereign ceiling, and not the opening of an
    aside about another issuer ("Organon & Co. (Ba3, ratings under review)")."""
    name = next(k for k in _GRADE_GROUPS if m[k])
    grade, s, e = m[name], m.start(name), m.end(name)
    n = notch(grade, "long")
    if n is None or n < _SOVEREIGN_CEILING[agency] or bool(_MOODYS.fullmatch(grade)) != (agency == "Moody's"):
        return False
    return not (re.search(r"\(\s*['‘]?$", t[max(0, s - 3):s]) and re.match(r"['’]?\s*,", t[e:]))


def _global(t: str, filing_action: str | None) -> list[dict]:
    """Global-scale ratings, from the covering letter only (the enclosed press releases name
    other issuers' ratings), and never above India's own rating — an Indian issuer's foreign-
    currency rating can't out-rate the sovereign, so a better grade is a misread."""
    out, seen = [], set()
    for a in _GLOBAL_AGENCY.finditer(t[:GLOBAL_SCAN_CHARS]):
        name = a[1].lower()
        agency = ("Fitch" if name == "fitch" else "Moody's" if name.startswith("moody") else
                  "JCR" if name.startswith("japan") else "CareEdge Global" if name.startswith("careedge") else "S&P")
        if agency in seen:
            continue
        g = next((m for m in _GLOBAL_GRADE.finditer(t, a.end(), a.end() + 400) if _fits(t, m, agency)), None)
        if not g:
            continue
        grade = next(g[k] for k in _GRADE_GROUPS if g[k])
        seen.add(agency)
        before, after = t[a.start():g.start()], t[g.end():g.end() + 150]
        ol = _GLOBAL_OUTLOOK_NEXT.match(after) or _GLOBAL_OUTLOOK.search(after)
        # "from 'Baa3' to 'Baa2'" or "to 'A-' with Stable Outlook from 'BBB+'"
        prev = _GLOBAL_FROM.search(before[-60:]) or _GLOBAL_FROM.search(after[:100])
        start = max(a.start(), g.start() - 120)
        out.append(_resolve({
            "agency": agency, "scale": "global", "term": "long", "rating": grade, "notch": notch(grade, "long"),
            "outlook": next(x for x in ol.groups() if x).title() if ol else None, "watch": None,
            "action": _action(before + after), "prev_rating": prev[1] if prev else None,
            "quote": t[start:g.end() + 40].strip()[:300]}, filing_action))
    return out


def parse_ratings(text: str) -> list[dict]:
    """Filing text -> one row per (agency, term): the current rating, outlook, watch, action and
    (when the filing says "from X") the previous rating, each with its exact quote."""
    t = " ".join((text or "").split())[:SCAN_CHARS]
    fa = _FILING_ACTION.search(t[:4000])
    filing_action = _action(fa[1]) if fa else None
    if filing_action is None and fa and fa[1].lower() == "placed":
        filing_action = "watch"
    return _domestic(t, filing_action) + _global(t, filing_action)


def rating_rows(filing: dict, extracted: list[dict]) -> list[dict]:
    """Extractor output -> `credit_ratings` rows carrying the source filing's identity."""
    return [{"seq_id": filing["seq_id"], "symbol": filing["symbol"], "disclosed_at": filing["disclosed_at"],
             **r, "method": "rule_v1"} for r in extracted]
