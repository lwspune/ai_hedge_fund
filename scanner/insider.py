"""Promoter open-market buying (candidate signal #7) from NSE SAST Regulation 29 disclosures.

Source: NSE `api/corporate-sast-reg29` (JSON; answers a plain session with a Referer — unlike the
PIT insider endpoint, which returns empty). Each row: symbol, acquisition/sale, mode (Open
Market / Off Market / ...), promoterType Y/N, stake % acquired/sold and after, disclosure time.

Pure parsing/clustering (tested) + a thin fetcher; the study is scripts/validate_promoter_buys.py.
"""
from __future__ import annotations

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
