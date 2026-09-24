"""Company master (infra I1): every NSE-listed equity, from NSE/niftyindices static CSVs.

Sources (all static files — reachable from residential and datacenter IPs):
  EQUITY_L.csv      — every mainboard equity: symbol, name, series, listing date, ISIN, face value
  SME_EQUITY_L.csv  — NSE Emerge (SME board), same fields; underscored headers, 2-digit years
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
SME_EQUITY_URL = "https://nsearchives.nseindia.com/emerge/corporates/content/SME_EQUITY_L.csv"
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
    """DictReader with normalised headers (NSE pads them; the SME file uses underscores) and
    whitespace-stripped values."""
    reader = csv.reader(io.StringIO(text))
    header = [h.strip().replace("_", " ") for h in next(reader, [])]
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


MIN_MAINBOARD, MIN_SME = 1800, 300   # a truncated download must never mass-delist the market
MAX_NEW_DELISTINGS = 50              # per weekly run; NSE delists a handful a week


class TruncatedList(ValueError):
    """EQUITY_L / SME_EQUITY_L parsed to implausibly few rows."""


class TooManyDelistings(ValueError):
    """The diff would delist more symbols in one run than is plausible."""


def check_list_sizes(n_mainboard: int, n_sme: int) -> None:
    if n_mainboard < MIN_MAINBOARD or n_sme < MIN_SME:
        raise TruncatedList(f"EQUITY_L {n_mainboard} (< {MIN_MAINBOARD}?) / SME {n_sme} (< {MIN_SME}?)")


def check_delistings(rows: list[dict], today: date) -> None:
    n = sum(r["status"] == "delisted" and r.get("delist_source") == "equity_l_diff"
            and r["delisted_on"] == today.isoformat() for r in rows)
    if n > MAX_NEW_DELISTINGS:
        raise TooManyDelistings(f"{n} symbols newly delisted by diff (> {MAX_NEW_DELISTINGS})")


def build_companies(equities: list[dict], indices: dict[str, list[dict]], delisted: list[dict],
                    screener_sectors: dict | None = None, previous_listed: list[dict] | None = None,
                    changes: list[dict] | None = None, today: date | None = None) -> list[dict]:
    """Merge the listed universe with index membership/industry and historical delistings
    into `companies` rows (JSON-ready). A symbol currently listed is never marked delisted.

    Industry: niftyindices first, else the screener sector (same 'Financial Services' label, so
    `is_financial` agrees wherever both exist). Delisting by diff: a row listed last run
    (`previous_listed`) that is absent today is marked delisted today — never deleted. A renamed
    symbol's old row also gives up its ISIN (the new row carries it; ISIN is unique) and is
    emitted first so the upsert frees the ISIN before the new row claims it."""
    today = today or date.today()
    sectors = screener_sectors or {}
    industry, member = {}, {}
    for key, rows in indices.items():
        for r in rows:
            member.setdefault(r["symbol"], []).append(key)
            if r["industry"] and r["symbol"] not in industry:
                industry[r["symbol"]] = r["industry"]

    out, listed, isins = [], set(), set()
    for e in equities:
        # mainboard list comes first: a migrated SME (same symbol or same ISIN) keeps that row
        if e["symbol"] in listed or e["isin"] in isins:
            continue
        ind, src = industry.get(e["symbol"]), "niftyindices"
        if ind is None and sectors.get(e["symbol"]):
            ind, src = sectors[e["symbol"]], "screener"
        listed.add(e["symbol"])
        isins.add(e["isin"])
        out.append({**e, "listing_date": _iso(e["listing_date"]), "industry": ind,
                    "industry_source": src if ind else None,
                    "indices": sorted(member.get(e["symbol"], [])),
                    "is_financial": None if ind is None else ind == FINANCIAL_INDUSTRY,
                    "status": "listed", "delisted_on": None, "delist_source": None,
                    "last_seen_listed": today.isoformat()})

    gone = []
    for p in previous_listed or []:
        if p["symbol"] in listed:
            continue
        renamed = resolve_symbol(p["symbol"], changes or []) != p["symbol"]
        gone.append({**p, "status": "delisted", "delisted_on": today.isoformat(),
                     "delist_source": "equity_l_diff",
                     "isin": None if renamed or p.get("isin") in isins else p.get("isin")})
        listed.add(p["symbol"])

    for d in delisted:
        if d["symbol"] in listed:
            continue
        listed.add(d["symbol"])
        out.append({"symbol": d["symbol"], "name": d["name"], "series": None,
                    "listing_date": None, "face_value": None, "isin": None, "industry": None,
                    "industry_source": None, "indices": [], "is_financial": None,
                    "status": "delisted", "delisted_on": _iso(d["delisted_on"]),
                    "delist_source": "nse_delisted_csv", "last_seen_listed": None})
    return gone + out


def _get(url: str) -> str:
    r = requests.get(url, headers=_UA, timeout=30)
    r.raise_for_status()
    return r.text


def fetch_all(screener_sectors: dict | None = None, previous_listed: list[dict] | None = None,
              today: date | None = None) -> tuple[list[dict], list[dict], dict]:
    """Fetch every source; returns (companies rows, symbol_changes rows, {index_key: symbols}).
    Raises TruncatedList / TooManyDelistings rather than write a market-wide delisting from a
    bad download."""
    today = today or date.today()
    main, sme = parse_equity_list(_get(EQUITY_URL)), parse_equity_list(_get(SME_EQUITY_URL))
    check_list_sizes(len(main), len(sme))
    indices = {k: parse_index_list(_get(u)) for k, u in INDEX_URLS.items()}
    changes = parse_symbol_changes(_get(SYMBOL_CHANGE_URL))
    companies = build_companies(main + sme, indices, parse_delisted(_get(DELISTED_URL)),
                                screener_sectors, previous_listed, changes, today)
    check_delistings(companies, today)
    members = {k: {r["symbol"] for r in rows} for k, rows in indices.items() if rows}
    return companies, [{**c, "changed_on": _iso(c["changed_on"])} for c in changes], members


# --- WP5: point-in-time index membership (index_membership intervals) -----------------------

def membership_diff(current_open: list[dict], todays: dict, today: date) -> tuple[list[dict], list[dict]]:
    """(intervals to close, intervals to open). current_open: open rows {symbol, index_key,
    from_date}; todays: {index_key: set(symbols)} from today's niftyindices lists. An index
    absent from `todays` (its download failed) is left untouched rather than emptied."""
    have = {(r["symbol"], r["index_key"]) for r in current_open}
    close = [{**r, "to_date": today.isoformat()} for r in current_open
             if r["index_key"] in todays and r["symbol"] not in todays[r["index_key"]]]
    open_ = [{"symbol": s, "index_key": k, "from_date": today.isoformat(), "to_date": None,
              "source": "niftyindices_list"}
             for k, syms in todays.items() for s in sorted(syms) if (s, k) not in have]
    return close, open_


def curated_intervals(rows: list[dict], index_key: str, record_start: str) -> list[dict]:
    """Membership intervals from a curated add/drop event list (e.g. the Next-50 file built from
    niftyindices press releases). A drop with no earlier add = member since before the record
    starts, so its interval opens at `record_start`."""
    out, open_from = [], {}
    for r in sorted(rows, key=lambda r: (r["effective"], r["leg"] != "drop")):
        sym = r["symbol"]
        if r["leg"] == "add":
            open_from.setdefault(sym, r["effective"])
        elif r["leg"] == "drop":
            out.append({"symbol": sym, "index_key": index_key,
                        "from_date": open_from.pop(sym, record_start), "to_date": r["effective"],
                        "source": "curated"})
    out += [{"symbol": s, "index_key": index_key, "from_date": f, "to_date": None, "source": "curated"}
            for s, f in open_from.items()]
    return sorted(out, key=lambda r: (r["symbol"], r["from_date"]))
