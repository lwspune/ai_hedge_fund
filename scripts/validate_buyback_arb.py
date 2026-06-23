"""Validate small-shareholder buyback tender arbitrage with a historical study.

For each completed tender buyback: buy ~Rs 2L before the record date, capture the
buyback premium on the guaranteed-accepted (entitlement) portion, sell the
residual ~1 month after close. Reports gross, full-acceptance, and after-tax
(the Oct-2024 dividend-tax regime) returns.

    python scripts/validate_buyback_arb.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner.buyback import fetch_buyback, arb_return, after_tax_return  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
PRICES = CACHE / "prices"
CACHE.mkdir(exist_ok=True)
PRICES.mkdir(exist_ok=True)

ID_RANGE = range(90, 226)
RESIDUAL_LAG = 21          # trading days after close to sell the residual
TAX_CUTOVER = pd.Timestamp("2024-10-01")
SLAB = 0.30


def scrape() -> pd.DataFrame:
    import requests
    fp = CACHE / "buybacks.csv"
    if fp.exists():
        return pd.read_csv(fp, parse_dates=["record_date", "close_date"])
    s = requests.Session()
    rows = []
    for bid in ID_RANGE:
        try:
            bb = fetch_buyback(bid, s)
            if bb:
                rows.append(bb)
                print(f"  {bid}: {bb['symbol']} {bb['company'][:28]}")
        except Exception as e:
            print(f"  {bid}: err {repr(e)[:60]}")
        time.sleep(0.8)
    df = pd.DataFrame(rows)
    df.to_csv(fp, index=False)
    return df


def get_prices(symbol: str):
    fp = PRICES / f"{symbol}.parquet"
    if fp.exists():
        s = pd.read_parquet(fp)["close"]
        return s if len(s) else None
    import yfinance as yf
    s = pd.Series(dtype="float64")
    for attempt in range(2):
        try:
            h = yf.Ticker(f"{symbol}.NS").history(period="max", interval="1d", auto_adjust=True)
            s = h["Close"].dropna()
            if len(s):
                s.index = s.index.tz_localize(None)
                break
        except Exception:
            pass
        time.sleep(1 + attempt)
    pd.DataFrame({"close": s}).to_parquet(fp)
    return s if len(s) else None


def price_on_or_before(s, d):
    sub = s[s.index <= d]
    return float(sub.iloc[-1]) if len(sub) else None


def price_after(s, d, lag):
    sub = s[s.index > d]
    return float(sub.iloc[lag]) if len(sub) > lag else None


def main():
    bb = scrape()
    bb = bb.dropna(subset=["symbol", "buyback_price", "record_date", "close_date",
                           "entitlement_small"])
    print(f"\nTender buybacks scraped with full data: {len(bb)}")

    recs = []
    for _, r in bb.iterrows():
        s = get_prices(r["symbol"])
        if s is None:
            continue
        entry = price_on_or_before(s, r["record_date"])
        post = price_after(s, r["close_date"], RESIDUAL_LAG)
        if not entry or not post:
            continue
        ent = float(r["entitlement_small"])
        bp = float(r["buyback_price"])
        regime = "post_oct2024" if r["record_date"] >= TAX_CUTOVER else "pre_oct2024"
        recs.append({
            "symbol": r["symbol"],
            "record_date": r["record_date"],
            "regime": regime,
            "premium": bp / entry - 1,
            "gross_floor": arb_return(entry, bp, post, ent),
            "gross_full": arb_return(entry, bp, post, min(ent * 3, 1.0)),
            "aftertax_floor": after_tax_return(entry, bp, post, ent, regime=regime, slab=SLAB),
            "aftertax_now": after_tax_return(entry, bp, post, ent, regime="post_oct2024", slab=SLAB),
        })
    d = pd.DataFrame(recs)
    if d.empty:
        print("No events with usable prices.")
        return

    def show(label, col, sub=None):
        x = (sub if sub is not None else d)[col].dropna()
        if len(x) == 0:
            print(f"  {label:<34} n=0"); return
        print(f"  {label:<34} n={len(x):>3}  mean={x.mean()*100:+6.2f}%  "
              f"median={x.median()*100:+6.2f}%  win={ (x>0).mean()*100:4.0f}%")

    print(f"\n=== BUYBACK TENDER ARB ({len(d)} events, ~Rs 2L, entitlement-floor acceptance) ===")
    show("Avg buyback premium vs entry", "premium")
    show("GROSS return (entitlement floor)", "gross_floor")
    show("GROSS return (3x entitlement)", "gross_full")
    show("AFTER-TAX (regime of the day)", "aftertax_floor")
    show("AFTER-TAX (today's rules, 30% slab)", "aftertax_now")
    print("\n  -- by tax regime (gross floor) --")
    show("pre-Oct-2024 events", "gross_floor", d[d.regime == "pre_oct2024"])
    show("post-Oct-2024 events", "gross_floor", d[d.regime == "post_oct2024"])
    print("\n  -- after-tax floor, by regime --")
    show("pre-Oct-2024 (tax-free buyback)", "aftertax_floor", d[d.regime == "pre_oct2024"])
    show("post-Oct-2024 (dividend-taxed)", "aftertax_floor", d[d.regime == "post_oct2024"])


if __name__ == "__main__":
    main()
