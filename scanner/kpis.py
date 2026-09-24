"""Rule-based KPI extraction from filing text (F3). Chosen by the F2 sample analysis
(docs/FILINGS_KPI_ANALYSIS.md): only metrics that are (a) not in structured financials and
(b) stated formulaically enough for deterministic rules — order book, order-win value,
current capacity utilisation — plus guidance captured as quotes (not normalised).

Every result carries the exact `quote` it came from (a substring of the text) so each number
is checkable. Precision over recall: ambiguous phrasings return nothing.
"""
from __future__ import annotations

import re
from datetime import date

_MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july",
                                         "august", "september", "october", "november", "december"], 1)}
_MON = r"(january|february|march|april|may|june|july|august|september|october|november|december)"
_CUR = r"(₹|Rs\.?|INR|US\$|USD|\$)?"
_UNIT = r"(lakh crores?|crores?|cr\.?|mn|million|bn|billion|lakhs?)"
# amount + unit, NOT followed by a physical unit (an ethanol "order book" in crore litres)
# optional range ("US$1.3–1.4 billion"): value = the lower bound, currency carried across
MONEY = re.compile(_CUR + r"\s*([\d,]+(?:\.\d+)?)\+?(?:\s*(?:–|-|to)\s*[\d,]+(?:\.\d+)?)?\s*" + _UNIT +
                   r"(?![a-z])(?!\s*(?:liters?|litres?|tonnes?|mt\b|kl\b|units?|kg))", re.I)
_BOOK = r"order ?(?:book|backlog)\b"   # \b: 'order bookings' is inflow, not the book
# anything in between that means the number belongs to another metric (or a new slide bullet)
_FOREIGN = re.compile(r"inflow|target|pipeline|revenue|secured|received|booked|worth|grew|grown|growth|"
                      r"increase|added|addition|guidance|new orders?|contract|used to|\bleft\b|declared|"
                      r"performance|led by|segment|division|vertical|•|;|\|", re.I)
_FUTURE = re.compile(r"\bwill\b|expect|target|\baim|plan|going to|guidance|would like|should|"
                     r"\bby (fy|q\d|quarter|the end)|next (year|\d)", re.I)


def to_crore(value: float, unit: str) -> float | None:
    u = (unit or "").lower().strip(". ")
    if "usd" in u or "$" in u:
        return None
    if u.startswith("lakh cr"):
        return float(value) * 100000
    if u.startswith(("crore", "cr")):
        return float(value)
    if u.startswith("lakh"):
        return round(value / 100, 4)
    if u in ("mn", "million"):
        return round(value / 10, 4)
    if u in ("bn", "billion"):
        return round(value * 100, 4)
    return None


def _num(s: str) -> float:
    v = float(s.replace(",", ""))
    return int(v) if v.is_integer() else v


def _canon(unit: str) -> str:
    u = unit.lower().rstrip(".")
    if u.startswith("lakh cr"):
        return "lakh crore"
    if u.startswith(("crore", "cr")):
        return "crore"
    if u.startswith("lakh"):
        return "lakh"
    return "mn" if u in ("mn", "million") else "bn"


def _unit(m: re.Match) -> str:
    """Canonical unit (crore | lakh | mn | bn, or 'USD mn' / 'USD bn' for dollar amounts)."""
    cur, unit = (m.group(1) or ""), _canon(m.group(3))
    return f"USD {unit}" if cur.upper() in ("US$", "USD", "$") else unit


def _row(kpi: str, value, unit, quote: str, as_of=None) -> dict:
    return {"kpi": kpi, "value": value, "unit": unit,
            "value_cr": to_crore(value, unit) if value is not None and unit else None,
            "as_of": as_of, "quote": quote}


def _as_of(s: str) -> str | None:
    m = re.search(r"as (?:on|of|at)\s+(\d{1,2})\s?(?:st|nd|rd|th)?\s+" + _MON + r",?\s+(\d{4})", s, re.I)
    if m:
        return date(int(m[3]), _MONTHS[m[2].lower()], int(m[1])).isoformat()
    m = re.search(r"as (?:on|of|at)\s+" + _MON + r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", s, re.I)
    if m:
        return date(int(m[3]), _MONTHS[m[1].lower()], int(m[2])).isoformat()
    return None


def _dedupe(rows: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in rows:
        k = (r["kpi"], r["value"], r["unit"])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def order_book(text: str) -> list[dict]:
    """Order-book LEVEL statements. Forward: 'order book ... stands at ₹X crore' (the first
    amount within 70 chars, nothing foreign in between); reverse (slides): '₹X Cr [Total|...]
    Order Book'. Growth statements, headings over other metrics, and non-rupee/physical units
    return nothing."""
    out = []
    for m in re.finditer(_BOOK, text, re.I):
        tail = text[m.end(): m.end() + 70]
        mm = MONEY.search(tail)
        if not mm or _FOREIGN.search(tail[: mm.start()]):
            continue
        quote = text[m.start(): m.end() + mm.end()]
        ctx = text[max(0, m.start() - 60): m.end() + mm.end()]
        out.append(_row("order_book", _num(mm.group(2)), _unit(mm), quote, _as_of(ctx)))
    for mm in MONEY.finditer(text):
        after = text[mm.end(): mm.end() + 40]
        rb = re.match(r"\s*(?:[A-Za-z]+\s+){0,2}?" + _BOOK, after, re.I)
        if not rb or _FOREIGN.search(after[: rb.end()]):
            continue
        quote = text[mm.start(): mm.end() + rb.end()]
        out.append(_row("order_book", _num(mm.group(2)), _unit(mm), quote,
                        _as_of(text[mm.start(): mm.end() + 120])))
    return _dedupe(out)


def order_win_value(text: str) -> list[dict]:
    """Value of an order announced in a Reg 30 order-win filing: the first amount after the
    'consideration or size of the order' cell (or 'worth/valued at/contract price of').
    Band-only disclosures ('Mega Order') return nothing."""
    pats = [r"(?:consideration|size) of (?:the )?order", r"(?:worth|valued at|value of|contract price of|"
            r"totall?ing|aggregating)\s"]
    for p in pats:
        for m in re.finditer(p, text, re.I):
            window = text[m.end(): m.end() + 200 if "order" in p else m.end() + 40]
            mm = MONEY.search(window)
            if mm:
                return [_row("order_win_value", _num(mm.group(2)), _unit(mm),
                             text[m.start(): m.end() + mm.end()])]
    return []


def capacity_utilisation(text: str) -> list[dict]:
    """CURRENT capacity utilisation %. 'utilization stood at 65%' / '~76% Capacity Utilisation';
    anything with future/target language nearby ('will reach', 'expect') returns nothing."""
    out = []
    fwd = re.compile(r"capacity utili[sz]ation[^.%]{0,40}?\b(stood|stands|is|was|at|of|remained|reached)"
                     r"\b[^.%\d]{0,30}(\d{1,3}(?:\.\d+)?)\s?%", re.I)
    rev = re.compile(r"~?(\d{1,3}(?:\.\d+)?)\s?%\s*(?:of (?:that|the|our) )?capacity utili[sz]ation", re.I)
    for m in fwd.finditer(text):
        pre = text[max(0, m.start() - 60): m.start()] + m.group(0)
        v = float(m.group(2))
        if not _FUTURE.search(pre) and 0 < v <= 100:
            out.append(_row("capacity_utilisation", _num(m.group(2)), "%", m.group(0)))
    for m in rev.finditer(text):
        pre = text[max(0, m.start() - 80): m.start()]
        v = float(m.group(1))
        if not _FUTURE.search(pre) and 0 < v <= 100:
            out.append(_row("capacity_utilisation", _num(m.group(1)), "%", m.group(0)))
    return _dedupe(out)


def guidance_quotes(text: str, limit: int = 8) -> list[dict]:
    """Management guidance as QUOTES (not normalised — guidance spans revenue, volume, capex,
    cost, stores...): sentences mentioning guidance / 'we expect|target|aim' AND a number."""
    out = []
    for s in re.split(r"(?<=[.!?])\s+", text):
        s = s.strip()
        if 20 <= len(s) <= 300 and re.search(r"guidance|\bwe (expect|target|aim)", s, re.I) \
                and re.search(r"\d+(?:\.\d+)?\s?%|₹|\bRs\.?\s?\d|crore|\bINR\s?\d", s, re.I):
            out.append(_row("guidance", None, None, s))
        if len(out) >= limit:
            break
    return out


# --- financials sector pack (lenders): ratio KPIs, "<label> ... X%" -------------------------
FIN_LABELS = {
    "gnpa": r"\bGNPA\b(?: ratio)?|\bgross npa(?: ratio)?|gross non[- ]performing assets?|gross stage ?(?:3|iii)\b",
    "nnpa": r"\bNNPA\b(?: ratio)?|\bnet npa(?: ratio)?|net non[- ]performing assets?|net stage ?(?:3|iii)\b",
    "nim": r"\bNIMs?\b|net interest margins?",
    "credit_cost": r"\bcredit costs?\b",
    "pcr": r"\bPCR\b|provision(?:ing)? coverage(?: ratio)?",
    "crar": r"\bCRAR\b|capital adequacy(?: ratio)?|(?-i:\bCAR\b)",   # 'car loans' is not CAR
    "casa": r"\bCASA\b(?: ratio)?",
    "roa": r"\bROA\b|return on (?:average )?assets",
}
_FIN_MAX = {"gnpa": 40, "nnpa": 10, "nim": 25, "credit_cost": 20, "pcr": 100, "crar": 100,
            "casa": 100, "roa": 10}
_FIN_MIN = {"crar": 8, "pcr": 25}   # below any regulatory floor / plausible coverage = misread
# The ONLY words allowed between a label and its %: connectors, time words, directions. Anything
# else ("Deposits", "grew", "corridor", "PAT", slide labels) means the number isn't this ratio.
_FIN_CONNECT = set("""ratio ratios stood stands standing stand is was were are at of to remained remains
improved improving declined fell dropped moderated increased increasing has have had been already come
down further strong healthy comfortable now about around approx approximately the quarter for ended as
on in domestic global annualized annualised basis points bps year-on-year yoy sequentially q-on-q qoq
by which a an broadly stable also company total our overall stage assets reported which level levels
end excluding including one-offs one-off consolidated standalone""".split())
_FIN_TOKEN_OK = re.compile(r"^(\d+(?:\.\d+)?(?:st|nd|rd|th)?|q[1-4]|fy\d{2,4}|h[12]|" + _MON[1:-1] + r")$", re.I)


_FIN_LABEL_END = re.compile("(?:" + "|".join(FIN_LABELS.values()) +
                            r")(?:[\W\d]+|\b(?:at|is|of|was|stood|stands|to|ratio)\b)*$", re.I)


def _value_first_tile(text: str, start: int) -> bool:
    """True if a % sits right BEFORE the label and is NOT itself the value of a preceding lender
    label — i.e. a value-then-label KPI tile ('3.46% Gross NPA 12.38% 30+ DPD'), where reading
    forward would take the next tile's number."""
    before = text[max(0, start - 14): start]
    pm = re.search(r"\d{1,3}(?:\.\d+)?\s?%[\s*|]*$", before)
    if not pm:
        return False
    prev = text[max(0, start - 14 - 45): max(0, start - 14) + pm.start()]
    return not _FIN_LABEL_END.search(prev)


def _clean_connector(between: str) -> bool:
    for tok in re.findall(r"[A-Za-z0-9.\-]+", between):
        tok = tok.strip(".").lower()
        if tok and tok not in _FIN_CONNECT and not _FIN_TOKEN_OK.match(tok):
            return False
    if re.search(r"\d{1,3},\d{2,3}", between):   # an amount (35,787) — the % belongs to it
        return False
    return not re.search(r"[.;|<>+]\s", between + " ")   # a sentence break / bound / sign
# a label between the metric and its number means the number belongs to that other label
_ANY_FIN = re.compile("|".join(FIN_LABELS.values()) + r"|\bRoE\b|\bCET ?-?1\b|\btier ?[12]\b|\bLCR\b|"
                      r"yields?\b|cost of (?:funds|borrowing)", re.I)
_PCT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s?%")


def fin_ratios(text: str) -> list[dict]:
    """Lender ratios (GNPA, NNPA, NIM, credit cost, PCR, CRAR, CASA, RoA): the first % within
    55 chars of the label, one per KPI per filing. Rejected: another metric's label or a '%'
    header in between, multi-quarter table rows (3+ percentages in a row), guidance language,
    'A and B were X% and Y%' (handled as an explicit pair), out-of-range values."""
    out: dict[str, dict] = {}
    pair = re.search(r"(\bGNPA\b|gross npa)\s+and\s+(\bNNPA\b|net npa)\s+(?:were|are|stood|was)?\s*(?:at\s+)?"
                     r"(\d{1,2}(?:\.\d+)?)\s?%\s+and\s+(\d{1,2}(?:\.\d+)?)\s?%", text, re.I)
    if pair:
        out["gnpa"] = _row("gnpa", _num(pair.group(3)), "%", pair.group(0))
        out["nnpa"] = _row("nnpa", _num(pair.group(4)), "%", pair.group(0))
    for kpi, pat in FIN_LABELS.items():
        if kpi in out:
            continue
        for m in re.finditer(pat, text, re.I):
            gap = text[m.end(): m.end() + 55]
            p = _PCT.search(gap)
            if not p:
                continue
            between = gap[: p.start()]
            after = text[m.end() + p.end(): m.end() + p.end() + 40]
            if (_ANY_FIN.search(between) or "%" in between or not _clean_connector(between)
                    or _value_first_tile(text, m.start())
                    or len(_PCT.findall(text[m.end() + p.start(): m.end() + p.start() + 30])) >= 3
                    or re.match(r"\s+and\s+\d", after)
                    or _FUTURE.search(text[max(0, m.start() - 60): m.start()] + between)):
                continue
            v = float(p.group(1))
            if _FIN_MIN.get(kpi, 0) <= v <= _FIN_MAX[kpi] and v > 0:
                out[kpi] = _row(kpi, _num(p.group(1)), "%", text[m.start(): m.end() + p.end()])
                break
    return list(out.values())


METHOD = "rule_v1"


def pdf_text(data: bytes, max_pages: int = 80) -> tuple[str | None, int]:
    """(text of the first `max_pages` pages, total page count) via PyMuPDF; (None, 0) if the
    bytes aren't a PDF. Born-digital filings have clean text layers (F2: 198/200 docs)."""
    import fitz
    if not data or not data.startswith(b"%PDF"):
        return None, 0
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:  # corrupt / encrypted PDF
        return None, 0
    return "\n".join(doc[i].get_text() for i in range(min(max_pages, doc.page_count))), doc.page_count


def kpi_rows(filing: dict, extracted: list[dict]) -> list[dict]:
    """Extractor output -> `company_kpis` rows carrying the source filing's identity."""
    return [{"seq_id": filing["seq_id"], "symbol": filing["symbol"],
             "disclosed_at": filing["disclosed_at"], **r, "method": METHOD} for r in extracted]


def headline(rows: list[dict], kind: str, dated_only_in_transcripts: bool = True) -> list[dict]:
    """One value per filing for a level KPI: the first statement carrying an 'as on <date>';
    else — outside call transcripts — the first statement. Transcripts are Q&A: analysts'
    guesses and project-level remainders float around, so for the order book only a dated
    status line counts (capacity utilisation's own tense guard is enough — it's never dated)."""
    dated = [r for r in rows if r["as_of"]]
    if dated:
        return dated[:1]
    return [] if kind == "transcript" and dated_only_in_transcripts else rows[:1]


def doc_kind(category: str, subject: str | None) -> str:
    if category in ("Bagging/Receiving of orders/contracts", "Awarding of order(s)/contract(s)"):
        return "order"
    if category.startswith("Analysts") and "transcript" in (subject or "").lower():
        return "transcript"
    return "presentation" if category == "Investor Presentation" else "press"


def extract_all(text: str, category: str, subject: str | None = None,
                sector: str | None = None) -> list[dict]:
    """Extractors that fit the filing kind (and, for sector packs, the company's sector), over
    whitespace-collapsed text; level KPIs reduced to one headline value per filing."""
    t = re.sub(r"\s+", " ", text or "")
    kind = doc_kind(category, subject)
    if kind == "order":
        return order_win_value(t)
    rows = (headline(order_book(t), kind) + headline(capacity_utilisation(t), kind, False)
            + guidance_quotes(t))
    if sector == "Financial Services":   # lender pack (docs/FILINGS_KPI_ANALYSIS.md)
        rows += fin_ratios(t)
    return rows
