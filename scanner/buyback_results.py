"""Realized buyback acceptance from NSE post-buyback public announcements (`buyback_results`).

After a tender closes the company files a *Post Buyback Public Announcement* (SEBI Buyback
Regulations, reg 24(vi)) with the response table: shares reserved, valid bids and shares validly
tendered per category (small shareholders / general). Small-shareholder acceptance follows from
it — the number the selection model's prior is guessing (`_MCAP_ACCEPTANCE_PRIOR`).

Source: NSE `api/corporate-announcements?symbol=&from_date=&to_date=` (per-symbol windows reach
back to 2023 at least). Categories: "Post Buyback Public Announcement" (the table itself),
"Copy of Newspaper Publication" whose subject says post buyback (same table as a newspaper
scan — often an image PDF, then `needs_manual`), and "Closure of Buy Back" (sometimes repeats
the table). Pure parsing here (tested); loader scripts/refresh_buyback_results.py.
"""
from __future__ import annotations

import re
from datetime import datetime

_NUM = r"(\d[\d,]*)"
_PCT = r"(\d+(?:\.\d+)?)\s*%?"
_POST = re.compile(r"post[\s-]*buy[\s-]*back", re.I)
_RESULT_CATEGORIES = {"Post Buyback Public Announcement", "Closure of Buy Back"}


def _int(s: str) -> int:
    return int(s.replace(",", ""))


_TOKEN = re.compile(r"\d[\d,]*(?:\.\d+)?%?")
_BEFORE, _AFTER = 110, 260   # a wrapped layout puts the label after its numbers (Garware)
_MIN_RESERVED = 100


def _tokens(window: str) -> list[tuple[str, int]]:
    """(token, position) for every number in the window; a token with a '.' or '%' can only be
    the response column (percent or times), a plain integer only a share count."""
    return [(m[0], m.start()) for m in _TOKEN.finditer(window)]


def _category(text: str, label: str) -> dict | None:
    """One response-table row: reserved, [bids], tendered, response (% or 'times'). Column order
    varies, OCR drops digits and inserts noise, and some layouts print the label after its
    numbers — so the row is *solved*, not matched: the first (reserved, tendered) pair, in
    reading order, whose ratio agrees with a response figure in the same window. A mis-aligned
    pick fails the arithmetic instead of storing garbage."""
    # the label also appears in prose and in the table header: try every occurrence, first
    # solvable row wins
    for lm in re.finditer(label, text, re.I):
        after = text[lm.end():lm.end() + _AFTER]
        # stop at the next row/label so one row's numbers never answer for another
        nxt = re.search(r"General Category|\bTotal\b|Not in Master|Small Shareholder|Reserved Category", after[1:], re.I)
        if nxt:
            after = after[:1 + nxt.start()]
        windows = [after]
        if label.lower().startswith("small"):   # wrapped layout: the row's numbers precede the label
            before = text[max(0, lm.start() - _BEFORE):lm.start()]
            if not re.search(r"General|Total", before, re.I):   # never borrow the general row
                windows.append(before)
        for window in windows:
            row = _solve(window)
            if row:
                return row
    return None


def _solve(window: str) -> dict | None:
    toks = _tokens(window)
    ints = [int(t.replace(",", "")) for t, _ in toks if "." not in t and "%" not in t]
    resp = [(float(t.rstrip("%").replace(",", "")), t.endswith("%")) for t, _ in toks if "." in t or "%" in t]
    # two-decimal figures: agreement within rounding only (a neighbouring column is off by far
    # more — Garware's gross vs valid tendered differ by 0.11 points)
    for x, is_pct in resp:
        for i, a in enumerate(ints):
            if a < _MIN_RESERVED:
                continue
            for j in range(i + 1, len(ints)):
                b = ints[j]
                ratio = b / a
                if abs(ratio * 100 - x) <= 0.03:                     # response in percent
                    pct = x
                elif not is_pct and abs(ratio - x) <= 0.006:         # response in times
                    pct = round(ratio * 100, 2)
                else:
                    continue
                between = ints[i + 1:j]
                return {"reserved": a, "bids": between[0] if between else None, "tendered": b, "response_pct": pct}
    return None


def parse_post_buyback(text: str) -> dict | None:
    """The response table of a post-buyback announcement (PyMuPDF-flattened text) -> dict, or
    None when the small-shareholder row is absent (scanned image, unrelated PDF)."""
    t = re.sub(r"\s+", " ", text or "")
    ss = _category(t, r"Small Shareholders?")
    if not ss:
        return None
    gen = _category(t, r"General Category(?: for| of)?(?: other)?(?: Eligible)?(?: Shareholders)?")
    tot = _category(t, r"\bTotal\b")
    # validity: the small row must be its own row, and the total must add up (else it is
    # garbage — drop it rather than let it decide the acceptance)
    if gen and (gen["reserved"], gen["tendered"]) == (ss["reserved"], ss["tendered"]):
        return None
    if tot:
        if gen:
            ok = abs(ss["reserved"] + gen["reserved"] - tot["reserved"]) <= 0.01 * tot["reserved"] + 2
        else:   # SEBI: >= 15% of the offer is reserved for small shareholders
            ok = 0.12 <= ss["reserved"] / tot["reserved"] <= 0.5
        if not ok or tot["tendered"] < ss["tendered"]:
            tot = None
    m = re.search(r"approximately\s+(\d+(?:\.\d+)?)\s+times", t, re.I)
    times = float(m[1]) if m else (tot["tendered"] / tot["reserved"] if tot else None)
    return {
        "ss_reserved": ss["reserved"], "ss_bids": ss["bids"], "ss_tendered": ss["tendered"],
        "ss_response_pct": ss["response_pct"],
        "gen_reserved": gen["reserved"] if gen else None, "gen_tendered": gen["tendered"] if gen else None,
        "total_reserved": tot["reserved"] if tot else None, "total_tendered": tot["tendered"] if tot else None,
        "times_subscribed": times,
    }


def ss_acceptance(r: dict) -> float | None:
    """Fraction of a small shareholder's tendered shares accepted. Everything is accepted when
    the reserved pool is undersubscribed, or when the whole offer is (the unsubscribed general
    portion spills over); otherwise pro-rata on the reserved pool. Conservative when only the
    general category is undersubscribed and its spill-over is partial."""
    res, ten = r.get("ss_reserved"), r.get("ss_tendered")
    if not res or not ten:
        return None
    tr, tt = r.get("total_reserved"), r.get("total_tendered")
    if ten <= res or (tr and tt and tt <= tr):
        return 1.0
    return min(1.0, res / ten)


def is_result_announcement(a: dict) -> bool:
    cat, subj = (a.get("desc") or "").strip(), a.get("attchmntText") or ""
    return cat in _RESULT_CATEGORIES or (cat == "Copy of Newspaper Publication" and bool(_POST.search(subj)))


def _rank(a: dict) -> tuple:
    cat = (a.get("desc") or "").strip()
    order = {"Post Buyback Public Announcement": 0, "Copy of Newspaper Publication": 1, "Closure of Buy Back": 2}
    try:
        ts = datetime.strptime(str(a.get("an_dt") or "").strip(), "%d-%b-%Y %H:%M:%S")
    except ValueError:
        ts = datetime.max
    return (order.get(cat, 9), ts)


def pick_result(announcements: list[dict]) -> list[dict]:
    """Candidate PDFs in the order to try: the announcement proper, then the newspaper copy,
    then the closure filing; earliest first within a category."""
    return sorted((a for a in announcements if is_result_announcement(a) and a.get("attchmntFile")), key=_rank)


def results_row(buyback_id: int, parsed: dict | None, url: str | None = None, seq_id: int | None = None,
                parsed_by: str = "rule_v1") -> dict:
    """`buyback_results` row; a None parse (image PDF) stores the pointer with needs_manual."""
    p = parsed or {}
    return {"buyback_id": buyback_id,
            "ss_reserved": p.get("ss_reserved"), "ss_bids": p.get("ss_bids"), "ss_tendered": p.get("ss_tendered"),
            "ss_response_pct": p.get("ss_response_pct"),
            "gen_reserved": p.get("gen_reserved"), "gen_tendered": p.get("gen_tendered"),
            "total_reserved": p.get("total_reserved"), "total_tendered": p.get("total_tendered"),
            "times_subscribed": p.get("times_subscribed"),
            "ss_acceptance": ss_acceptance(p) if parsed else None,
            "source_url": url, "source_seq_id": seq_id,
            "parsed_by": parsed_by if parsed else None, "needs_manual": parsed is None}


# --- fetch (thin) ---------------------------------------------------------------

def fetch_symbol_announcements(symbol: str, frm, to, session) -> list[dict]:
    from scanner.filings import API, _HEADERS
    r = session.get(API, params={"index": "equities", "symbol": symbol,
                                 "from_date": frm.strftime("%d-%m-%Y"), "to_date": to.strftime("%d-%m-%Y")},
                    headers=_HEADERS, timeout=60)
    r.raise_for_status()
    d = r.json()
    return d if isinstance(d, list) else d.get("data", [])
