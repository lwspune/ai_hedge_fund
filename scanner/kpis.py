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


def extract_all(text: str, category: str, subject: str | None = None) -> list[dict]:
    """Extractors that fit the filing kind, over whitespace-collapsed text; level KPIs reduced
    to one headline value per filing."""
    t = re.sub(r"\s+", " ", text or "")
    kind = doc_kind(category, subject)
    if kind == "order":
        return order_win_value(t)
    return (headline(order_book(t), kind) + headline(capacity_utilisation(t), kind, False)
            + guidance_quotes(t))
