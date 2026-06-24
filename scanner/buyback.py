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


def fetch_buyback(bid: int, session) -> dict | None:
    """Parse one chittorgarh buyback by id. Returns None unless it's a tender
    offer with a small-shareholder entitlement (the arbable kind)."""
    r = session.get(f"https://www.chittorgarh.com/buyback/x/{bid}/",
                    headers={"User-Agent": _UA}, timeout=25)
    if r.status_code != 200 or "Buyback" not in r.text:
        return None
    html = r.text
    txt = _text(html)

    try:
        tables = pd.read_html(io.StringIO(html))
    except ValueError:
        return None

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


def scan_current_buybacks(ids=range(214, 230), session=None) -> list[dict]:
    """Scrape recent tender buybacks, attach current price + arb estimate, rank.

    Returns structured dicts (id/symbol/company/cur_price/buyback_price/premium/
    entitlement_small/est_return/dates) for both display and persistence. Skips
    implausible premiums (stale/wrong price) so no bad data is surfaced.
    """
    import requests
    import yfinance as yf

    s = session or requests.Session()
    out = []
    for bid in ids:
        try:
            bb = fetch_buyback(bid, s)
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
        est = arb_return(cur, bb["buyback_price"], cur, bb["entitlement_small"])
        out.append({**bb, "cur_price": cur, "premium": premium, "est_return": est})
    out.sort(key=lambda r: (r["est_return"] or -9), reverse=True)
    return out


def format_buyback_table(rows: list[dict]) -> str:
    if not rows:
        return "No current tender buybacks with usable data in the scanned range."
    head = f"{'SYM':<12}{'PRICE':>9}{'BUYBACK':>9}{'PREMIUM':>9}{'ENTITLE':>9}{'EST_FLOOR':>10}"
    out = [head, "-" * len(head)]
    for r in rows:
        out.append(f"{r['symbol']:<12}{r['cur_price']:>9,.1f}{r['buyback_price']:>9,.1f}"
                   f"{r['premium']*100:>8.1f}%{r['entitlement_small']*100:>8.1f}%"
                   f"{(r['est_return'] or 0)*100:>9.1f}%")
    out.append("\nEST_FLOOR = guaranteed-acceptance floor, residual flat. Real return is "
               "higher when acceptance > entitlement (small-caps); apply tax overlay before acting.")
    return "\n".join(out)
