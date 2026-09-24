"""Preferential allotments and their lock-in expiries (`pref_issues` + corporate_events
`pref_lockin_expiry`; candidate signal: pref-allotment lock-in expiry overhang).

Source: NSE `api/corporate-further-issues-pref?index=FIPREFIP` (in-principle stage: allottee
category) and `?index=FIPREFLS` (listing stage: allotment date, price, shares). Date windows
filter on the submission date; the listing list starts in Mar-2023. The listing XBRL
(`in-capmkt` taxonomy) carries the lock-in per tranche (`PeriodOfLockInShares` under the
`LockInOfSharesAxis` Option contexts), e.g. "Equity shares for 6 months".

ICDR lock-in (since Jan-2022): 6 months for non-promoter allottees, 18 months for promoters (up
to 20% of post-issue capital). Expiry = allotment date + months; a filing without a readable
tranche gets the 6-month default, flagged `default: true` in the event details.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime

import requests

PREF_URL = "https://www.nseindia.com/api/corporate-further-issues-pref"
STAGES = {"in_principle": "FIPREFIP", "listing": "FIPREFLS"}
DEFAULT_MONTHS = 6
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept": "*/*", "Accept-Encoding": "gzip, deflate", "Referer": "https://www.nseindia.com/"}
_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "nine": 9, "twelve": 12,
          "eighteen": 18, "twenty four": 24, "thirty six": 36}


def _date(s) -> str | None:
    try:
        return datetime.strptime(str(s).strip()[:11].title(), "%d-%b-%Y").date().isoformat()
    except ValueError:
        return None


def _num(v) -> float | None:
    try:
        return float(str(v).strip().replace(",", "")) if v not in (None, "", "-") else None
    except ValueError:
        return None


def _int(v) -> int | None:
    f = _num(v)
    return int(f) if f is not None else None


def parse_pref_list(raw, stage: str) -> list[dict]:
    """Rows of either stage in one shape; rows without a symbol are dropped."""
    items = raw.get("data", []) if isinstance(raw, dict) else raw
    out = []
    for r in items or []:
        sym = (r.get("nseSymbol") or "").strip().upper()
        app = _int(r.get("appId"))
        if not sym or app is None:
            continue
        out.append({
            "app_id": app, "symbol": sym, "isin": (r.get("isin") or "").strip() or None, "stage": stage,
            "board_res_date": _date(r.get("dateBrdResoln") or r.get("boardResDate")),
            "submission_date": _date(r.get("dateOfSubmission")),
            "allotment_date": _date(r.get("dateOfAllotmentOfShares")),
            "offer_price": _num(r.get("offerPricePerSecurity")),
            "shares_allotted": _int(r.get("totalNumOfSharesAllotted")),
            "amount": _num(r.get("amountRaised") if r.get("amountRaised") is not None else r.get("totalAmtRaised")),
            "allottee_category": (r.get("categoryOfAllottee") or "").strip() or None,
            "xml_url": r.get("xmlFileName") or None,
        })
    return out


def lockin_months(text: str | None) -> int | None:
    """'Equity shares for 6 months' -> 6; '1 year' -> 12; 'Three years' -> 36; else None."""
    if not text:
        return None
    t = text.lower()
    m = re.search(r"(\d+)\s*(month|year)", t)
    n, unit = None, None
    if m:
        n, unit = int(m.group(1)), m.group(2)
    else:
        for w, v in sorted(_WORDS.items(), key=lambda kv: -len(kv[0])):
            u = re.search(rf"\b{w}\s*(month|year)", t)
            if u:
                n, unit = v, u.group(1)
                break
    if n is None:
        return None
    return n * 12 if unit == "year" else n


def _cap(xml: str, tag: str, ctx: str | None = None) -> str | None:
    pat = rf'<in-capmkt:{tag}\s[^>]*contextRef="{re.escape(ctx)}"[^>]*>([^<]*)<' if ctx \
        else rf"<in-capmkt:{tag}[^>]*>([^<]*)<"
    m = re.search(pat, xml)
    return m.group(1).strip() if m and m.group(1).strip() else None


def parse_pref_ls_xbrl(xml: str) -> dict:
    """Allotment facts + lock-in tranches from a listing-stage XBRL."""
    tranches = {}
    for m in re.finditer(r'<in-capmkt:PeriodOfLockInShares\s[^>]*contextRef="D_(\w+)"[^>]*>([^<]*)<', xml):
        tranches.setdefault(m.group(1), {})["period"] = m.group(2).strip()
    for m in re.finditer(r'<in-capmkt:NumberOfLockInShares\s[^>]*contextRef="I_(\w+)"[^>]*>([^<]*)<', xml):
        tranches.setdefault(m.group(1), {})["shares"] = _int(m.group(2))
    lockins = [{"period": t.get("period"), "months": lockin_months(t.get("period")), "shares": t.get("shares")}
               for _, t in sorted(tranches.items())]
    return {"symbol": _cap(xml, "NSESymbol"), "allotment_date": _cap(xml, "DateOfAllotmentOfShares"),
            "offer_price": _num(_cap(xml, "OfferPricePerSecurity")),
            "shares_allotted": _int(_cap(xml, "TotalNumberOfSharesAllotted")),
            "shares_listed": _int(_cap(xml, "NumberOfEquitySharesListed")), "lockins": lockins}


def add_months(iso: str, n: int) -> str:
    """Calendar months forward, day clamped to the target month's length."""
    d = date.fromisoformat(iso)
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1])).isoformat()


def lockin_expiry_events(rows: list[dict]) -> list[dict]:
    """corporate_events rows: one per lock-in tranche of every listing-stage allotment. Rows
    without readable tranches get the ICDR 6-month default (flagged); tranches whose period
    isn't a duration ('Not applicable') produce nothing."""
    out = []
    for r in rows:
        if r.get("stage") != "listing" or not r.get("allotment_date"):
            continue
        tr = [t for t in (r.get("lockins") or []) if t.get("months")]
        default = not r.get("lockins")
        if default:
            tr = [{"months": DEFAULT_MONTHS, "shares": r.get("shares_allotted")}]
        listed = r.get("shares_listed")
        for t in tr:
            share = round(t["shares"] / listed, 4) if t.get("shares") and listed else None
            out.append({"symbol": r["symbol"], "event_type": "pref_lockin_expiry",
                        "event_date": add_months(r["allotment_date"], t["months"]), "record_date": None,
                        "details": {"months": t["months"], "shares": t.get("shares"),
                                    "allotment_date": r["allotment_date"], "offer_price": r.get("offer_price"),
                                    "share_of_listed": share, "app_id": r.get("app_id"), "default": default},
                        "source": "nse_pref"})
    return out


# --- thin I/O -----------------------------------------------------------------

def session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_HEADERS)
    return s


def fetch_pref(stage: str, frm: date | None = None, to: date | None = None,
               s: requests.Session | None = None) -> list[dict]:
    params = {"index": STAGES[stage]}
    if frm and to:
        params.update(from_date=frm.strftime("%d-%m-%Y"), to_date=to.strftime("%d-%m-%Y"))
    r = (s or session()).get(PREF_URL, params=params, timeout=60)
    r.raise_for_status()
    return parse_pref_list(r.json(), stage)


def fetch_xbrl(url: str, s: requests.Session | None = None) -> str:
    r = (s or session()).get(url, timeout=60)
    r.raise_for_status()
    return r.text


def study_events(rows: list[dict]) -> list[dict]:
    """Event-study rows from corporate_events `pref_lockin_expiry` rows (details flattened,
    two-year era label from the expiry year)."""
    out = []
    for r in rows:
        if r.get("event_type") != "pref_lockin_expiry":
            continue
        d = r.get("details") or {}
        y = int(r["event_date"][:4])
        start = y - (y - 2024) % 2
        out.append({"symbol": r["symbol"], "expiry": r["event_date"], "months": d.get("months"),
                    "shares": d.get("shares"), "allotment_date": d.get("allotment_date"),
                    "offer_price": d.get("offer_price"), "share_of_listed": d.get("share_of_listed"),
                    "app_id": d.get("app_id"), "default": bool(d.get("default")),
                    "era": f"{start}-{str(start + 1)[2:]}"})
    return out
