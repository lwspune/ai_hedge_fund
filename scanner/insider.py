"""Promoter open-market buying (candidate signal #7) from NSE SAST Regulation 29 disclosures.

Source: NSE `api/corporate-sast-reg29` (JSON; answers a plain session with a Referer — unlike the
PIT insider endpoint, which returns empty). Each row: symbol, acquisition/sale, mode (Open
Market / Off Market / ...), promoterType Y/N, stake % acquired/sold and after, disclosure time.

Pure parsing/clustering (tested) + a thin fetcher; the study is scripts/validate_promoter_buys.py.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

import requests

API = "https://www.nseindia.com/api/corporate-sast-reg29"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept": "*/*", "Referer": "https://www.nseindia.com/"}


def _pct(v) -> float | None:
    try:
        return float(str(v).strip()) if v not in (None, "", "-") else None
    except ValueError:
        return None


def _disclosed(v) -> str | None:
    """'08-Sep-2026 12:36' -> '2026-09-08'."""
    try:
        return datetime.strptime(str(v).strip()[:11], "%d-%b-%Y").date().isoformat()
    except ValueError:
        return None


def parse_reg29(raw: list[dict]) -> list[dict]:
    """NSE Reg 29 rows -> normalised dicts; rows without a parseable disclosure date dropped."""
    out = []
    for r in raw:
        d = _disclosed(r.get("sysTime") or r.get("timestamp"))
        sym = (r.get("symbol") or "").strip()
        side = {"Acquisition": "BUY", "Sale": "SELL"}.get((r.get("acqSaleType") or "").strip())
        if not d or not sym or not side:
            continue
        pct = _pct(r.get("totAcqShare")) if side == "BUY" else _pct(r.get("totSaleShare"))
        out.append({"symbol": sym, "side": side, "promoter": r.get("promoterType") == "Y",
                    "mode": (r.get("acquisitionMode") or "").strip(),
                    "instrument": (r.get("acqType") or "").strip(),
                    "disclosed": d, "pct": pct, "after_pct": _pct(r.get("totAftShare"))})
    return out


def disclosure_events(rows: list[dict], side: str, promoter: bool, mode: str = "Open Market",
                      gap_days: int = 10) -> list[dict]:
    """Cluster matching disclosures per symbol: a new event starts when the previous one is
    more than `gap_days` calendar days back. Event date = first disclosure of the cluster."""
    sel = sorted((r for r in rows if r["side"] == side and r["promoter"] == promoter
                  and r["mode"] == mode and r["instrument"].lower().startswith("equity")),
                 key=lambda r: (r["symbol"], r["disclosed"]))
    out: list[dict] = []
    for r in sel:
        last = out[-1] if out and out[-1]["symbol"] == r["symbol"] else None
        if last and (date.fromisoformat(r["disclosed"]) - date.fromisoformat(last["_last"])).days <= gap_days:
            last["n"] += 1
            last["pct"] += r["pct"] or 0.0
            last["_last"] = r["disclosed"]
        else:
            out.append({"symbol": r["symbol"], "date": r["disclosed"], "n": 1,
                        "pct": r["pct"] or 0.0, "_last": r["disclosed"]})
    for e in out:
        e.pop("_last")
    return sorted(out, key=lambda e: (e["date"], e["symbol"]))


def fetch_reg29(frm: date, to: date, session=None) -> list[dict]:
    """Raw Reg 29 rows for [frm, to] (a year per call works)."""
    s = session or requests.Session()
    r = s.get(API, params={"index": "equities", "from_date": frm.strftime("%d-%m-%Y"),
                           "to_date": to.strftime("%d-%m-%Y")}, headers=_HEADERS, timeout=60)
    r.raise_for_status()
    return r.json().get("data", [])


def fetch_range(frm: date, to: date) -> list[dict]:
    """Year-by-year fetch over a long range."""
    s, out, cur = requests.Session(), [], frm
    while cur <= to:
        end = min(date(cur.year, 12, 31), to)
        out += fetch_reg29(cur, end, s)
        cur = end + timedelta(days=1)
    return out


# --- SEBI PIT disclosures (NSE `api/corporates-pit-gg` + per-filing XBRL) ----------------------
# The list endpoint answers a plain session (from GitHub runners too) but carries only filing
# metadata; each filing's XBRL holds the transactions, one `DisclosureN` context per insider
# named (`in-bse-co` taxonomy, shared with BSE). `api/corporates-pit` (no `-gg`) is dead and
# always returns {"data": []}. Dated windows only reach back a few months: a forward feed.

PIT_URL = "https://www.nseindia.com/api/corporates-pit-gg"
_PIT_FIELDS = {
    "NameOfThePerson": ("person", str), "CategoryOfPerson": ("category", str),
    "TypeOfInstrument": ("instrument", str),
    "SecuritiesAcquiredOrDisposedTransactionType": ("txn_type", str),
    "ModeOfAcquisitionOrDisposal": ("mode", str),
    "SecuritiesAcquiredOrDisposedNumberOfSecurity": ("n_securities", int),
    "SecuritiesAcquiredOrDisposedValueOfSecurity": ("value", float),
    "SecuritiesHeldPriorToAcquisitionOrDisposalPercentageOfShareholding": ("pre_pct", float),
    "SecuritiesHeldPostAcquistionOrDisposalPercentageOfShareholding": ("post_pct", float),
    "DateOfAllotmentAdviceOrAcquisitionOfSharesOrSaleOfSharesSpecifyFromDate": ("txn_from", str),
    "DateOfAllotmentAdviceOrAcquisitionOfSharesOrSaleOfSharesSpecifyToDate": ("txn_to", str),
    "ExchangeOnWhichTheTradeWasExecuted": ("exchange", str),
}


def _broadcast(v) -> str | None:
    """'10-Sep-2026 20:46:52' -> '2026-09-10T20:46:52'."""
    try:
        return datetime.strptime(str(v).strip(), "%d-%b-%Y %H:%M:%S").isoformat()
    except ValueError:
        return None


def parse_pit_filings(raw) -> list[dict]:
    """Filing metadata rows; rows without an XBRL link or a parseable broadcast time dropped."""
    items = raw.get("data", []) if isinstance(raw, dict) else raw
    out = []
    for r in items or []:
        ts, url = _broadcast(r.get("broadcastDateTime")), r.get("xmlFileName")
        try:
            app = int(str(r.get("appId")).strip())
        except (TypeError, ValueError):
            continue
        if not ts or not url:
            continue
        out.append({"app_id": app, "symbol": (r.get("symbol") or "").strip().upper(), "broadcast_at": ts,
                    "regulation": (r.get("regulation") or "").strip() or None,
                    "submission": (r.get("typeOfSubmission") or "").strip() or None, "xml_url": url})
    return out


def _cast(kind, s: str):
    try:
        if kind is int:
            return int(float(s))
        if kind is float:
            return float(s)
    except ValueError:
        return None
    return s


def parse_pit_xml(xml: str) -> list[dict]:
    """One dict per `DisclosureN` context; numeric fields typed, missing values None."""
    ids = re.findall(r'<xbrli:context id="(Disclosure\d+)">', xml)
    out = []
    for seq, cid in enumerate(sorted(ids, key=lambda c: int(c[len("Disclosure"):])), 1):
        d: dict = {"seq": seq}
        facts = dict(re.findall(rf'<in-bse-co:(\w+)\s[^>]*contextRef="{cid}"[^>]*>([^<]*)<', xml))
        for tag, (field, kind) in _PIT_FIELDS.items():
            v = facts.get(tag, "").strip()
            d[field] = _cast(kind, v) if v else None
        out.append(d)
    return out


def insider_rows(filing: dict, disclosures: list[dict]) -> list[dict]:
    """`insider_trades` rows: filing metadata joined onto each disclosure (pk app_id + seq)."""
    return [{"app_id": filing["app_id"], "symbol": filing["symbol"], "broadcast_at": filing["broadcast_at"],
             "regulation": filing.get("regulation"), "xml_url": filing["xml_url"], **d} for d in disclosures]


def fetch_pit_filings(frm: date | None = None, to: date | None = None, session=None) -> list[dict]:
    s = session or requests.Session()
    params = {"index": "equities"}
    if frm and to:
        params.update(from_date=frm.strftime("%d-%m-%Y"), to_date=to.strftime("%d-%m-%Y"))
    r = s.get(PIT_URL, params=params, headers=_HEADERS, timeout=120)
    r.raise_for_status()
    return parse_pit_filings(r.json())


def fetch_xml(url: str, session=None) -> str:
    r = (session or requests.Session()).get(url, headers=_HEADERS, timeout=60)
    r.raise_for_status()
    return r.text
