"""Buyback tender-arbitrage: chittorgarh scraper + small-shareholder arb math.

The edge is structural: SEBI reserves 15% of every tender buyback for small
shareholders (holdings <= Rs 2 lakh), a pool institutions cannot touch. We model
the *guaranteed* acceptance (the entitlement ratio) as a conservative floor, and
the Oct-2024 tax change (buyback proceeds now taxed as dividend) as an overlay.
"""
from __future__ import annotations

import io
import re

import pandas as pd

STCG_RATE = 0.20  # short-term capital gains (post Jul 2024)


# --- pure: parsing + arb math -----------------------------------------------

def parse_entitlement(text: str):
    """Small-shareholder entitlement ratio, or None if absent / implausible.

    2026 pages: `Small Shareholders 11 : 56 ...` (ratio table; anchored so the General
    Category row never matches). <= 2025 pages: `5 Equity Shares out of every 56 ...`."""
    text = text or ""
    m = (re.search(r"Small Shareholders\s*(\d+)\s*:\s*(\d+)", text, re.I)
         or re.search(r"(\d+)\s+Equity Shares out of every\s+(\d+)", text, re.I))
    if not m or int(m.group(2)) == 0:
        return None
    r = int(m.group(1)) / int(m.group(2))
    return r if 0 < r <= 1 else None


def _components(entry_price, accept_frac, capital, cost_bps):
    n = int(capital // entry_price)
    if n <= 0:
        return None
    accepted = n * accept_frac
    residual = n - accepted
    buy_cost = n * entry_price * (1 + cost_bps / 1e4)
    return n, accepted, residual, buy_cost


def arb_return(entry_price, buyback_price, post_price, accept_frac,
               capital=200000, cost_bps=30):
    """Gross (pre-tax) return of the small-shareholder tender arb."""
    c = _components(entry_price, accept_frac, capital, cost_bps)
    if c is None:
        return None
    _, accepted, residual, buy_cost = c
    proceeds = accepted * buyback_price + residual * post_price * (1 - cost_bps / 1e4)
    return proceeds / buy_cost - 1


def after_tax_return(entry_price, buyback_price, post_price, accept_frac, regime,
                     slab=0.30, capital=200000, cost_bps=30, stcg_rate=STCG_RATE):
    """After-tax return under the pre/post Oct-2024 buyback-tax regimes."""
    c = _components(entry_price, accept_frac, capital, cost_bps)
    if c is None:
        return None
    _, accepted, residual, buy_cost = c
    proceeds = accepted * buyback_price + residual * post_price * (1 - cost_bps / 1e4)
    residual_tax = stcg_rate * max(0.0, residual * (post_price - entry_price))
    if regime == "pre_oct2024":
        tax = residual_tax                                   # buyback proceeds exempt
    elif regime == "post_oct2024":
        div_tax = slab * (accepted * buyback_price)          # taxed as dividend
        cap_loss_benefit = stcg_rate * (accepted * entry_price)  # accepted cost -> capital loss
        tax = residual_tax + div_tax - cap_loss_benefit
    else:
        raise ValueError(f"unknown regime {regime}")
    return (proceeds - tax) / buy_cost - 1


# --- selection model: acceptance estimate + expected return -----------------

# Heuristic PRIOR (not a fitted model — we lack clean realized-acceptance training
# data). Small-caps see little retail tendering vs the 15% reserved pool, so retail
# acceptance runs high; large-caps get crowded, collapsing toward the entitlement
# floor. The P2 outcomes feedback loop is meant to calibrate these over time.
_MCAP_ACCEPTANCE_PRIOR = [
    (2_000, 0.90),     # < 2,000 cr  -> small-cap
    (10_000, 0.55),    # < 10,000 cr -> small/mid
    (30_000, 0.30),    # < 30,000 cr -> mid
    (float("inf"), 0.12),  # large-cap
]


def mcap_bucket(market_cap_cr) -> str:
    """Market-cap bucket label (matches the _MCAP_ACCEPTANCE_PRIOR thresholds)."""
    if market_cap_cr is None:
        return "unknown"
    labels = ["small", "small_mid", "mid", "large"]
    for (cap, _), name in zip(_MCAP_ACCEPTANCE_PRIOR, labels):
        if market_cap_cr < cap:
            return name
    return "large"


def estimate_acceptance(market_cap_cr, entitlement_small, issue_size_cr=None) -> float:
    """Estimated retail acceptance fraction, never below the entitlement floor.

    A large *relative* buyback (issue size >= 5% of market cap) nudges acceptance up —
    more reserved shares chasing the same small-shareholder float.
    """
    floor = float(entitlement_small or 0.0)
    if market_cap_cr is None:
        return floor
    base = next(a for cap, a in _MCAP_ACCEPTANCE_PRIOR if market_cap_cr < cap)
    if issue_size_cr and market_cap_cr and issue_size_cr / market_cap_cr >= 0.05:
        base = min(0.95, base + 0.15)
    return max(floor, base)


def estimate_entitlement(issue_size_cr, buyback_price, market_cap_cr, price, small_holder_pct,
                         reserved: float = 0.15) -> float | None:
    """Small-shareholder entitlement ratio implied by the float: 15% of the buyback shares over
    the shares held by resident individuals with <= Rs 2 lakh nominal capital (`shareholding`
    table, `small_holder_pct`). This is what the company's published ratio measures on the
    record date, so it fills the gap before the letter of offer publishes it. None without
    every input; capped at 1.0 (a float smaller than the reserved pool)."""
    if not issue_size_cr or not buyback_price or not market_cap_cr or not price or not small_holder_pct:
        return None
    buyback_shares = issue_size_cr / buyback_price          # both in crore-rupee / rupee units
    outstanding = market_cap_cr / price
    small_float = outstanding * small_holder_pct / 100.0
    if small_float <= 0:
        return None
    return min(1.0, reserved * buyback_shares / small_float)


def entitlement_floor(bb: dict, market_cap_cr, price, small_holder_pct) -> tuple[float | None, str | None]:
    """(ratio, 'published'|'estimated'|None): the published ratio when the offer carries one,
    else the float-implied estimate."""
    if bb.get("entitlement_small"):
        return float(bb["entitlement_small"]), "published"
    est = estimate_entitlement(bb.get("issue_size_cr"), bb.get("buyback_price"), market_cap_cr, price,
                               small_holder_pct)
    return (est, "estimated") if est is not None else (None, None)


def calibrate_from_outcomes(records) -> dict:
    """Fit the acceptance prior from realized tenders. records: dicts with
    market_cap_cr + realized_acceptance. Returns {bucket: {n, acceptance(mean)}}.

    Empty until the outcomes table has data — this is what replaces the hardcoded
    _MCAP_ACCEPTANCE_PRIOR once enough real tenders are logged.
    """
    from collections import defaultdict
    acc = defaultdict(list)
    for r in records:
        mc, ra = r.get("market_cap_cr"), r.get("realized_acceptance")
        if mc is None or ra is None:
            continue
        acc[mcap_bucket(mc)].append(float(ra))
    return {b: {"n": len(v), "acceptance": sum(v) / len(v)} for b, v in acc.items()}


def expected_after_tax(price, buyback_price, est_acceptance, record_date, slab=0.30):
    """After-tax expected return at the estimated acceptance, residual sold flat.

    Tax regime is chosen from the record date (Oct-2024 dividend-tax cutover)."""
    regime = "pre_oct2024"
    if record_date is not None and pd.Timestamp(record_date) >= pd.Timestamp("2024-10-01"):
        regime = "post_oct2024"
    return after_tax_return(price, buyback_price, price, est_acceptance,
                            regime=regime, slab=slab)


# --- scraper ----------------------------------------------------------------

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _text(html: str) -> str:
    t = re.sub(r"<[^>]+>", " ", html or "")
    t = re.sub(r"&#?\w+;", " ", t)  # strip HTML entities (&#8377; etc.) — their digits break regexes
    return re.sub(r"\s+", " ", t)


def parse_symbol(html: str):
    """NSE symbol from the embedded JSON, e.g. `\\"nseCode\\":\\"GPIL\\"`.

    The payload is double-encoded JSON, so quotes arrive backslash-escaped; strip
    all backslashes first, then match the nseCode / nse_symbol field.
    """
    clean = (html or "").replace("\\", "")
    m = re.search(r'"nse(?:Code|_symbol)"\s*:\s*"([A-Z0-9&.\-]{2,})"', clean)
    return m.group(1) if m else None


def parse_issue_size(text: str):
    """Buyback issue size in crore from `Issue Size (Amount) ₹60.24 Crores`."""
    t = re.sub(r"&#?\w+;", " ", text or "")  # strip entities (&#8377; digits would mis-match)
    m = re.search(r"Issue Size \(Amount\)\D*?([\d,]+(?:\.\d+)?)\s*Crore", t, re.I)
    return float(m.group(1).replace(",", "")) if m else None


def parse_issue_type(html: str):
    """`Issue Type Tender Offer` -> "tender", `... Open Market` -> "open_market", else None."""
    m = re.search(r"Issue Type\s*(Tender Offer|Open Market)", _text(html), re.I)
    if not m:
        return None
    return "tender" if m.group(1).lower().startswith("tender") else "open_market"


_BUYBACK_URL = "https://www.chittorgarh.com/buyback/x/{}/"


def _fetch_page(bid: int, session):
    """(exists, html) for a buyback id. exists=False on 404 / non-buyback pages."""
    # unknown ids 307-redirect to a listing page (which also says "Buyback") -> never follow
    r = session.get(_BUYBACK_URL.format(bid), headers={"User-Agent": _UA}, timeout=25,
                    allow_redirects=False)
    if r.status_code == 200 and "Buyback" in r.text:
        return True, r.text
    return False, None


def parse_buyback(html: str, bid: int) -> dict | None:
    """Parse a chittorgarh buyback page (no network). None unless it's a tender
    offer with a small-shareholder entitlement (the arbable kind)."""
    txt = _text(html)
    if parse_issue_type(html) == "open_market":
        return None  # only tender offers carry the small-shareholder reservation

    try:
        tables = pd.read_html(io.StringIO(html))
    except Exception:
        return None  # unparseable / no tables -> not a buyback detail page

    # Entitlement table identifies a tender offer (open-market buybacks lack it). The row
    # holds label + ratio in separate cells, so parse the joined row: `<= 2025` wording
    # ("Reserved Category for Small Shareholders | 25 Equity Shares out of every 103") and
    # 2026 wording ("Small Shareholders | 11 : 56 | 90000000") both match.
    entitlement = None
    for tb in tables:
        for _, row in tb.iterrows():
            joined = " ".join(str(x) for x in row.values)
            if "Small Shareholders" in joined:
                entitlement = parse_entitlement(joined)
                if entitlement:
                    break
        if entitlement:
            break
    if entitlement is None:
        entitlement = parse_entitlement(
            txt[txt.find("Small Shareholders"):] if "Small Shareholders" in txt else "")
    if entitlement is None:
        return None  # not an arbable tender offer

    title = ""
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    if m:
        title = m.group(1).replace("Buyback Detail", "").strip()

    symbol = parse_symbol(html)

    pm = (re.search(r"Buyback Price\s*₹?\s*([\d,]+(?:\.\d+)?)\s*per share", txt)
          or re.search(r"buyback price of ₹\s*([\d,]+)", txt, re.I))
    buyback_price = float(pm.group(1).replace(",", "")) if pm else None

    rm = (re.search(r"record date[^.]*?is\s+([A-Z][a-z]+ \d+,\s*\d{4})", txt, re.I)
          or re.search(r"Record Date\s+([A-Z][a-z]+ \d{1,2},\s*\d{4})", txt))
    record_date = pd.to_datetime(rm.group(1), errors="coerce") if rm else pd.NaT

    close_date = pd.NaT
    for tb in tables:
        if tb.shape[1] == 2:
            d = dict(zip(tb.iloc[:, 0].astype(str), tb.iloc[:, 1].astype(str)))
            for k, v in d.items():
                if "Buyback Closing Date" in k:
                    close_date = pd.to_datetime(v, errors="coerce")

    return {
        "id": bid,
        "company": title,
        "symbol": symbol,
        "buyback_price": buyback_price,
        "record_date": record_date,
        "close_date": close_date,
        "entitlement_small": entitlement,
        "issue_size_cr": parse_issue_size(txt),
    }


def fetch_buyback(bid: int, session) -> dict | None:
    """Fetch + parse one buyback by id. None if the page is gone or not a tender."""
    exists, html = _fetch_page(bid, session)
    return parse_buyback(html, bid) if exists else None


def _default_start_id() -> int:
    """Begin the upward probe just below the highest buyback id we've stored."""
    try:
        from scanner import db
        m = db.max_buyback_id()
        if m:
            return max(m - 3, 200)
    except Exception:
        pass
    return 210


def discover_buybacks(start_id: int, max_gap: int = 12, hard_cap: int = 120, session=None,
                      stats: dict | None = None, delay: float = 0.2) -> list[dict]:
    """Probe chittorgarh ids upward from start_id until `max_gap` consecutive misses (or
    `hard_cap` fetches); return the parsed tender offers. `stats` (if given) is filled with
    pages_seen / tender_parsed / rejected — a page that exists but won't parse is how a
    silent format change shows up (WP1: every 2026 page was rejected for nine months)."""
    import time
    import requests

    s = session or requests.Session()
    st = {"pages_seen": 0, "tender_parsed": 0, "rejected": 0}
    out, gap, bid, fetched = [], 0, start_id, 0
    while gap < max_gap and fetched < hard_cap:
        try:
            exists, html = _fetch_page(bid, s)
        except Exception:
            exists, html = False, None
        fetched += 1
        bid += 1
        if delay:
            time.sleep(delay)
        if not exists:
            gap += 1
            continue
        gap = 0
        st["pages_seen"] += 1
        try:
            bb = parse_buyback(html, bid - 1)
        except Exception:
            bb = None
        if not bb or not bb["symbol"] or not bb["buyback_price"] or not bb["entitlement_small"]:
            st["rejected"] += 1
            continue
        st["tender_parsed"] += 1
        out.append(bb)
    if stats is not None:
        stats.update(st)
    return out


def latest_small_holder(symbol: str) -> dict:
    """Newest `shareholding` row's small-holder % for the entitlement estimate ({} if none /
    unreachable — the scan must not fail on a missing feature)."""
    try:
        from scanner import db
        rows = db.select("shareholding", {"select": "quarter_end,small_holder_pct", "symbol": f"eq.{symbol}",
                                          "small_holder_pct": "not.is.null",
                                          "order": "quarter_end.desc", "limit": "1"})
        return rows[0] if rows else {}
    except Exception:
        return {}


def scan_current_buybacks(start_id=None, max_gap=12, hard_cap=120, session=None,
                          only_open=False, stats: dict | None = None) -> list[dict]:
    """Probe chittorgarh ids upward from the latest-known buyback; enrich each tender
    offer with price + market cap + estimated acceptance + after-tax expected return,
    ranked (open tender windows first). Auto-finds new buybacks — no hardcoded range."""
    from datetime import date
    from scanner.fundamentals import fetch_fundamentals
    from scanner.pricestore import get_closes

    if start_id is None:
        start_id = _default_start_id()
    today = pd.Timestamp(date.today())

    out = []
    for bb in discover_buybacks(start_id, max_gap, hard_cap, session, stats):
        try:
            # unadjusted last close from the cloud store: the premium is vs a nominal rupee price
            px = get_closes(bb["symbol"], today - pd.Timedelta(days=15), today, source="db")
            cur = float(px.iloc[-1]) if px is not None else None
        except Exception:
            cur = None
        if not cur:
            continue
        premium = bb["buyback_price"] / cur - 1
        if not (-0.5 < premium < 1.5):
            continue  # implausible premium => stale/wrong price, skip
        try:
            mcap = fetch_fundamentals(bb["symbol"]).get("market_cap_cr")
        except Exception:
            mcap = None
        shp = latest_small_holder(bb["symbol"])
        floor, floor_src = entitlement_floor(bb, mcap, cur, shp.get("small_holder_pct"))
        acc = estimate_acceptance(mcap, floor, issue_size_cr=bb.get("issue_size_cr"))
        bb.update(
            cur_price=cur, premium=premium, market_cap_cr=mcap, est_acceptance=acc,
            small_holder_pct=shp.get("small_holder_pct"), small_holder_quarter=shp.get("quarter_end"),
            est_entitlement=estimate_entitlement(bb.get("issue_size_cr"), bb["buyback_price"], mcap, cur,
                                                 shp.get("small_holder_pct")),
            entitlement_source=floor_src,
            est_return=arb_return(cur, bb["buyback_price"], cur, bb["entitlement_small"]),
            exp_return=expected_after_tax(cur, bb["buyback_price"], acc, bb["record_date"]),
            is_open=bool(pd.notna(bb["close_date"]) and pd.Timestamp(bb["close_date"]) >= today),
        )
        out.append(bb)
    out.sort(key=lambda r: (r["is_open"], r["exp_return"] if r["exp_return"] is not None else -9),
             reverse=True)
    return [r for r in out if r["is_open"]] if only_open else out


def format_buyback_table(rows: list[dict]) -> str:
    if not rows:
        return ("No tender buybacks found in the probed id range — none live, or the "
                "start id needs advancing (persist scans so db.max_buyback_id moves up).")
    head = (f"{'SYM':<11}{'PRICE':>8}{'BUYBACK':>9}{'PREM':>6}{'MCAP_CR':>10}"
            f"{'ENT':>6}{'ACC~':>6}{'EXP~':>7}  WINDOW")
    out = [head, "-" * len(head)]
    for r in rows:
        mc = "-" if r.get("market_cap_cr") is None else f"{r['market_cap_cr']:,.0f}"
        exp = r.get("exp_return") or 0
        out.append(
            f"{r['symbol']:<11}{r['cur_price']:>8,.0f}{r['buyback_price']:>9,.0f}"
            f"{r['premium']*100:>5.0f}%{mc:>10}{r['entitlement_small']*100:>5.0f}%"
            f"{r['est_acceptance']*100:>5.0f}%{exp*100:>6.1f}%  "
            f"{'OPEN' if r.get('is_open') else 'closed'}")
    out.append("\nACC~ = estimated acceptance (heuristic by mkt-cap; the outcomes feedback "
               "loop calibrates it). EXP~ = after-tax expected return at ACC~. "
               "OPEN = tender window still open. Verify before acting.")
    return "\n".join(out)
