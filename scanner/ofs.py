"""Offer for sale (OFS) retail reservation — candidate signal #23 (`ofs_events`).

An OFS is a promoter/government stake sale through the exchange window: non-retail bidders set
the price on day 1, retail (bids <= Rs 2 lakh) bids on day 2 against a 10% reserved quota, at or
above the floor. Structurally it rhymes with the buyback quota (a reservation only retail can
use, a known price, a one-day hold), so the thesis says measure it.

Source: chittorgarh `/ofs/x/<id>/` (ids from 1, Jan-2025 ->; the Next.js payload carries the
floor price, both dates, the share split and the seller). The cut-off price is not populated
there, so the study measures against the floor: what a retail bidder at the floor pays when the
non-retail book clears at it (a cut-off above the floor makes the realised entry worse, never
better — the study's numbers are an upper bound on the retail leg).

Pure parsing + study math here (tested); loader scripts/refresh_ofs.py; study
scripts/validate_ofs_retail.py.
"""
from __future__ import annotations

import re

import pandas as pd

OFS_URL = "https://www.chittorgarh.com/ofs/x/{id}/"
_PSU = re.compile(r"president of india|governor of|government of|govt", re.I)
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _field(h: str, key: str) -> str | None:
    m = re.search(rf'"{key}":(?:"([^"]*)"|(-?[0-9.]+)|null)', h)
    if not m:
        return None
    v = m[1] if m[1] is not None else m[2]
    return v.strip() if v else None


def _num(s: str | None) -> float | None:
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)", s or "")
    return float(m[1].replace(",", "")) if m else None


def _int(s: str | None) -> int | None:
    v = _num(s)
    return int(v) if v is not None else None


def _date(s: str | None) -> str | None:
    d = pd.to_datetime(s, errors="coerce") if s else pd.NaT
    return None if pd.isna(d) else d.strftime("%Y-%m-%d")


def parse_ofs_page(html: str, oid: int) -> dict | None:
    """chittorgarh OFS detail page -> `ofs_events` row. None unless it has an NSE symbol, a floor
    price and a retail day (the listing/redirect pages have none)."""
    h = (html or "").replace("\\", "")
    sym, floor, retail = _field(h, "nseCode"), _num(_field(h, "floor_price")), _date(_field(h, "offer_open_date_retail"))
    if not sym or not floor or not retail:
        return None
    return {
        "chittorgarh_id": oid, "symbol": sym.upper(), "company": _field(h, "company_name"),
        "seller": _field(h, "seller_name"),
        "floor_price": floor, "cutoff_price": _num(_field(h, "cutoff_price")),
        "base_shares": _int(_field(h, "base_issue_size_shares")),
        "oversub_shares": _int(_field(h, "oversubscription_shares")),
        "total_shares": _int(_field(h, "total_issue_size_share")),
        "retail_shares": _int(_field(h, "retail_shares")),
        "non_retail_shares": _int(_field(h, "non_retail_Shares")),
        "non_retail_date": _date(_field(h, "offer_open_date_non_retail")),
        "retail_date": retail,
        "pct_equity": _num(_field(h, "percentage_of_equity_shares")),
        "listing_at": _field(h, "ofs_listing_at"),
        "last_modified": _date(_field(h, "last_modified_dt")),
    }


def fetch_ofs(oid: int, session=None) -> tuple[bool, dict | None]:
    """(exists, row). Unknown ids 307-redirect to the yearly list — never followed."""
    import requests
    s = session or requests.Session()
    r = s.get(OFS_URL.format(id=oid), headers={"User-Agent": _UA}, timeout=25, allow_redirects=False)
    if r.status_code != 200 or "OFS Detail" not in r.text:
        return False, None
    return True, parse_ofs_page(r.text, oid)


# --- study -------------------------------------------------------------------------

def ofs_rows_to_events(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        floor = float(r["floor_price"]) if r.get("floor_price") else None
        rs, ts = r.get("retail_shares"), r.get("total_shares")
        out.append({
            "chittorgarh_id": r.get("chittorgarh_id"), "symbol": r["symbol"], "floor_price": floor,
            "retail_date": r.get("retail_date"), "non_retail_date": r.get("non_retail_date"),
            "retail_share": (rs / ts) if rs and ts else None,
            "pct_equity": float(r["pct_equity"]) if r.get("pct_equity") not in (None, "") else None,
            "psu": bool(_PSU.search(r.get("seller") or "")),
        })
    return out


def study_events(rows: list[dict], today, min_days: int = 25) -> list[dict]:
    """Events with a floor and a retail day at least `min_days` calendar days ago (T+20 closes)."""
    cutoff = (pd.Timestamp(today) - pd.Timedelta(days=min_days)).strftime("%Y-%m-%d")
    return [e for e in ofs_rows_to_events(rows) if e["floor_price"] and e["retail_date"] and e["retail_date"] <= cutoff]


def ofs_returns(px: pd.Series, floor: float, retail_date, non_retail_date) -> dict | None:
    """Retail leg measured against the floor: pre_close = last close before the non-retail day
    (the announcement usually lands the evening before), the retail-day close, and the closes
    1 / 5 / 20 sessions after the retail day (T+1 = allotment, first sellable session). None
    when the pre-close or the retail-day close is missing."""
    if px is None or not len(px) or not floor:
        return None
    px = px.dropna().sort_index()
    rd, nrd = pd.Timestamp(retail_date), pd.Timestamp(non_retail_date or retail_date)
    before = px[px.index < nrd]
    if not len(before) or rd not in px.index:
        return None
    pre, retail_close = float(before.iloc[-1]), float(px.loc[rd])
    after = px[px.index > rd]
    at = lambda k: (float(after.iloc[k - 1]) / floor - 1) if len(after) >= k else None  # noqa: E731
    return {
        "pre_close": pre, "floor_discount": floor / pre - 1,
        "nonretail_day_move": (float(px.loc[nrd]) / pre - 1) if nrd in px.index else None,
        "retail_close_vs_floor": retail_close / floor - 1,
        "t1": at(1), "t5": at(5), "t20": at(20),
    }


def format_ofs_rows(rows: list[dict]) -> str:
    if not rows:
        return "No OFS with a retail day in the last 3 days or ahead."
    head = f"{'SYM':<12}{'FLOOR':>8}{'NON-RETAIL':>12}{'RETAIL':>12}{'RETAIL%':>9}{'STAKE%':>8}  SELLER"
    out = [head, "-" * len(head)]
    for r in rows:
        rs, ts = r.get("retail_shares"), r.get("total_shares")
        share = f"{rs / ts * 100:.0f}%" if rs and ts else "-"
        stake = f"{float(r['pct_equity']):.1f}%" if r.get("pct_equity") not in (None, "") else "-"
        out.append(f"{r['symbol']:<12}{float(r['floor_price']):>8,.0f}{str(r.get('non_retail_date') or ''):>12}"
                   f"{str(r.get('retail_date') or ''):>12}{share:>9}{stake:>8}  {(r.get('seller') or '')[:40]}")
    return "\n".join(out)
