"""Company master (infra I1): every NSE-listed equity, from NSE/niftyindices static CSVs.

Sources (all static files — reachable from residential and datacenter IPs):
  EQUITY_L.csv      — every listed equity: symbol, name, series, listing date, ISIN, face value
  symbolchange.csv  — headerless (company, old, new, date); renames break joins without it
  delisted.csv      — NSE's delisting list (stale: stops ~2020, still useful for history)
  ind_*list.csv     — niftyindices constituents: industry + index membership

Pure parsers (tested) + `fetch_all()` / `build_companies()`. Guards: rows with a blank
symbol or a malformed ISIN are dropped rather than stored.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime

import requests

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
_ISIN = re.compile(r"^IN[A-Z0-9]{10}$")

NSE = "https://nsearchives.nseindia.com/content/equities"
EQUITY_URL = f"{NSE}/EQUITY_L.csv"
SYMBOL_CHANGE_URL = f"{NSE}/symbolchange.csv"
DELISTED_URL = f"{NSE}/delisted.csv"
# index key -> niftyindices constituent file. Order matters: first industry seen wins.
INDEX_URLS = {
    "nifty50": "https://niftyindices.com/IndexConstituent/ind_nifty50list.csv",
    "niftynext50": "https://niftyindices.com/IndexConstituent/ind_niftynext50list.csv",
    "midcap150": "https://niftyindices.com/IndexConstituent/ind_niftymidcap150list.csv",
    "smallcap250": "https://niftyindices.com/IndexConstituent/ind_niftysmallcap250list.csv",
    "microcap250": "https://niftyindices.com/IndexConstituent/ind_niftymicrocap250_list.csv",
    "totalmarket": "https://niftyindices.com/IndexConstituent/ind_niftytotalmarket_list.csv",
}
FINANCIAL_INDUSTRY = "Financial Services"


def _date(s: str | None, fmts=("%d-%b-%Y", "%d-%b-%y")) -> date | None:
    s = (s or "").strip()
    for f in fmts:
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            continue
    return None


def _float(s: str | None) -> float | None:
    try:
        return float((s or "").strip())
    except ValueError:
        return None


def _rows(text: str) -> list[dict]:
    """DictReader with whitespace-stripped headers and values (NSE pads both)."""
    reader = csv.reader(io.StringIO(text))
    header = [h.strip() for h in next(reader, [])]
    return [{h: (v or "").strip() for h, v in zip(header, rec)} for rec in reader]


def parse_equity_list(text: str) -> list[dict]:
    out = []
    for r in _rows(text):
        sym, isin = r.get("SYMBOL", ""), r.get("ISIN NUMBER", "")
        if not sym or not _ISIN.match(isin):
            continue
        out.append({"symbol": sym, "name": r.get("NAME OF COMPANY") or None,
                    "series": r.get("SERIES") or None,
                    "listing_date": _date(r.get("DATE OF LISTING")),
                    "face_value": _float(r.get("FACE VALUE")), "isin": isin})
    return out


def parse_symbol_changes(text: str) -> list[dict]:
    out = []
    for rec in csv.reader(io.StringIO(text)):
        if len(rec) < 4:
            continue
        company, old, new, when = (c.strip() for c in rec[:4])
        changed_on = _date(when)
        if not old or not new or changed_on is None:
            continue
        out.append({"company": company or None, "old_symbol": old, "new_symbol": new,
                    "changed_on": changed_on})
    return out


def parse_delisted(text: str) -> list[dict]:
    out = []
    for r in _rows(text):
        sym, when = r.get("Symbol", ""), _date(r.get("Delisted Date"))
        if not sym or when is None:
            continue
        out.append({"symbol": sym, "name": r.get("Company") or None, "delisted_on": when,
                    "reason": r.get("Type of Delisting") or None})
    return out


def parse_index_list(text: str) -> list[dict]:
    return [{"symbol": r["Symbol"], "industry": r.get("Industry") or None,
             "isin": r.get("ISIN Code") or None}
            for r in _rows(text) if r.get("Symbol")]


def resolve_symbol(symbol: str, changes: list[dict]) -> str:
    """Follow old->new renames to the current symbol (latest change wins; cycle-safe)."""
    nxt = {}
    for c in sorted(changes, key=lambda c: c["changed_on"]):
        nxt[c["old_symbol"]] = c["new_symbol"]
    seen, cur = {symbol}, symbol
    while cur in nxt and nxt[cur] not in seen:
        cur = nxt[cur]
        seen.add(cur)
    return cur


def _iso(d):
    return d.isoformat() if d else None


def build_companies(equities: list[dict], indices: dict[str, list[dict]],
                    delisted: list[dict]) -> list[dict]:
    """Merge the listed universe with index membership/industry and historical delistings
    into `companies` rows (JSON-ready). A symbol currently listed is never marked delisted."""
    industry, member = {}, {}
    for key, rows in indices.items():
        for r in rows:
            member.setdefault(r["symbol"], []).append(key)
            if r["industry"] and r["symbol"] not in industry:
                industry[r["symbol"]] = r["industry"]

    out, listed = [], set()
    for e in equities:
        ind = industry.get(e["symbol"])
        listed.add(e["symbol"])
        out.append({**e, "listing_date": _iso(e["listing_date"]), "industry": ind,
                    "indices": sorted(member.get(e["symbol"], [])),
                    "is_financial": None if ind is None else ind == FINANCIAL_INDUSTRY,
                    "status": "listed", "delisted_on": None})
    for d in delisted:
        if d["symbol"] in listed:
            continue
        listed.add(d["symbol"])
        out.append({"symbol": d["symbol"], "name": d["name"], "series": None,
                    "listing_date": None, "face_value": None, "isin": None, "industry": None,
                    "indices": [], "is_financial": None, "status": "delisted",
                    "delisted_on": _iso(d["delisted_on"])})
    return out


def _get(url: str) -> str:
    r = requests.get(url, headers=_UA, timeout=30)
    r.raise_for_status()
    return r.text


def fetch_all() -> tuple[list[dict], list[dict]]:
    """Fetch every source; returns (companies rows, symbol_changes rows)."""
    equities = parse_equity_list(_get(EQUITY_URL))
    indices = {k: parse_index_list(_get(u)) for k, u in INDEX_URLS.items()}
    companies = build_companies(equities, indices, parse_delisted(_get(DELISTED_URL)))
    changes = [{**c, "changed_on": _iso(c["changed_on"])}
               for c in parse_symbol_changes(_get(SYMBOL_CHANGE_URL))]
    return companies, changes
