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
    """`5 Equity Shares out of every 56 ...` -> 5/56. None if absent."""
    m = re.search(r"(\d+)\s+Equity Shares out of every\s+(\d+)", text or "", re.I)
    return int(m.group(1)) / int(m.group(2)) if m else None


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


def estimate_acceptance(market_cap_cr, entitlement_small) -> float:
    """Estimated retail acceptance fraction, never below the entitlement floor."""
    floor = float(entitlement_small or 0.0)
    if market_cap_cr is None:
        return floor
    base = next(a for cap, a in _MCAP_ACCEPTANCE_PRIOR if market_cap_cr < cap)
    return max(floor, base)


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
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def parse_symbol(html: str):
    """NSE symbol from the embedded JSON, e.g. `\\"nseCode\\":\\"GPIL\\"`.

    The payload is double-encoded JSON, so quotes arrive backslash-escaped; strip
    all backslashes first, then match the nseCode / nse_symbol field.
    """
    clean = (html or "").replace("\\", "")
    m = re.search(r'"nse(?:Code|_symbol)"\s*:\s*"([A-Z0-9&.\-]{2,})"', clean)
    return m.group(1) if m else None


_BUYBACK_URL = "https://www.chittorgarh.com/buyback/x/{}/"


def _fetch_page(bid: int, session):
    """(exists, html) for a buyback id. exists=False on 404 / non-buyback pages."""
    r = session.get(_BUYBACK_URL.format(bid), headers={"User-Agent": _UA}, timeout=25)
    if r.status_code == 200 and "Buyback" in r.text:
        return True, r.text
    return False, None


def parse_buyback(html: str, bid: int) -> dict | None:
    """Parse a chittorgarh buyback page (no network). None unless it's a tender
    offer with a small-shareholder entitlement (the arbable kind)."""
    txt = _text(html)

    try:
        tables = pd.read_html(io.StringIO(html))
    except Exception:
        return None  # unparseable / no tables -> not a buyback detail page

    # Entitlement table identifies a tender offer (open-market buybacks lack it).
    entitlement = None
    for tb in tables:
        flat = " ".join(map(str, tb.astype(str).values.flatten()))
        if "Reserved Category for Small Shareholders" in flat:
            for _, row in tb.iterrows():
                cells = [str(x) for x in row.values]
                if any("Small Shareholders" in c for c in cells):
                    for c in cells:
                        e = parse_entitlement(c)
                        if e:
                            entitlement = e
            break
    if entitlement is None:
        return None  # not an arbable tender offer

    title = ""
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    if m:
        title = m.group(1).replace("Buyback Detail", "").strip()

    symbol = parse_symbol(html)

    pm = re.search(r"buyback price of ₹\s*([\d,]+)", txt, re.I)
    buyback_price = float(pm.group(1).replace(",", "")) if pm else None

    rm = re.search(r"record date[^.]*?is\s+([A-Z][a-z]+ \d+,\s*\d{4})", txt, re.I)
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


def scan_current_buybacks(start_id=None, max_gap=8, hard_cap=80, session=None,
                          only_open=False) -> list[dict]:
    """Probe chittorgarh ids upward from the latest-known buyback; enrich each tender
    offer with price + market cap + estimated acceptance + after-tax expected return,
    ranked (open tender windows first). Auto-finds new buybacks — no hardcoded range."""
    import time
    from datetime import date
    import requests
    import yfinance as yf
    from scanner.fundamentals import fetch_fundamentals

    s = session or requests.Session()
    if start_id is None:
        start_id = _default_start_id()
    today = pd.Timestamp(date.today())

    out, gap, bid, fetched = [], 0, start_id, 0
    while gap < max_gap and fetched < hard_cap:
        try:
            exists, html = _fetch_page(bid, s)
        except Exception:
            exists, html = False, None
        fetched += 1
        bid += 1
        time.sleep(0.2)
        if not exists:
            gap += 1
            continue
        gap = 0
        try:
            bb = parse_buyback(html, bid - 1)
        except Exception:
            bb = None
        if not bb or not bb["symbol"] or not bb["buyback_price"] or not bb["entitlement_small"]:
            continue
        try:
            px = yf.Ticker(f"{bb['symbol']}.NS").history(period="5d")["Close"].dropna()
            cur = float(px.iloc[-1]) if len(px) else None
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
        acc = estimate_acceptance(mcap, bb["entitlement_small"])
        bb.update(
            cur_price=cur, premium=premium, market_cap_cr=mcap, est_acceptance=acc,
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
