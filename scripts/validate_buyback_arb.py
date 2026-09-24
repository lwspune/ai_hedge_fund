"""Validate small-shareholder buyback tender arbitrage with a historical study.

For each completed tender buyback: buy ~Rs 2L at the LAST CUM-ENTITLEMENT CLOSE (T+1 era:
the session before the record date, which is itself the ex-date; T+2 era: two sessions
before — `buyback.last_buy_close`), capture the buyback premium on the guaranteed-accepted
(entitlement) portion, sell the residual ~1 month after close. Reports gross,
full-acceptance, and after-tax (the Oct-2024 dividend-tax regime) returns.

Until 2026-09-24 the entry was the record-day close — an ex-entitlement price nobody can
tender from; stocks drop a median ~2.5% that day, which the old table booked as premium.

    python scripts/validate_buyback_arb.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner.validation import exclude_results, run  # noqa: E402
from scanner.pricestore import get_closes  # noqa: E402
from scanner.buyback import arb_return, after_tax_return, last_buy_close  # noqa: E402
from scanner.pointintime import mcap_bucket_at  # noqa: E402

RESIDUAL_LAG = 21          # trading days after close to sell the residual
TAX_CUTOVER = pd.Timestamp("2024-10-01")
SLAB = 0.30
LOW_SLABS = (0.20, 0.05, 0.0)   # the post-Oct-2024 verdict depends on the slab
PREMIUM_BOUNDS = (-0.5, 1.5)   # outside = stale/mis-matched price, not a real offer (as edge fn)
DB_FROM = pd.Timestamp("2020-02-01")   # first month safely inside the cloud price store


def scrape() -> pd.DataFrame:
    """Tender buybacks from the Supabase `buybacks` table (kept current by the daily scan's
    chittorgarh discovery) — no laptop cache, so the study reruns identically on Actions."""
    from scanner import db
    rows = db.select_all("buybacks", {"select": "chittorgarh_id,symbol,buyback_price,record_date,close_date,"
                                                "entitlement_small,issue_size_cr", "order": "chittorgarh_id"})
    df = pd.DataFrame(rows)
    for c in ("record_date", "close_date"):
        df[c] = pd.to_datetime(df[c])
    return df


def get_prices(symbol: str, record_date) -> pd.Series | None:
    # UNADJUSTED closes: the buyback price is a nominal rupee price, so entry/residual must be
    # too (yfinance back-adjusts for later splits/bonuses: SPORTKING 1:10 -> "+1282%" premium).
    # The cloud store covers 2020->; earlier events use nselib.
    t = pd.Timestamp(record_date)
    return get_closes(symbol, t - pd.Timedelta(days=30), t + pd.Timedelta(days=120),
                      source="db" if t >= DB_FROM else "nse")


def price_on_or_before(s, d):
    sub = s[s.index <= d]
    return float(sub.iloc[-1]) if len(sub) else None


def price_after(s, d, lag):
    sub = s[s.index > d]
    return float(sub.iloc[lag]) if len(sub) > lag else None


def main(args) -> dict | None:
    bb = scrape()
    bb = bb.dropna(subset=["symbol", "buyback_price", "record_date", "close_date",
                           "entitlement_small"])
    print(f"\nTender buybacks scraped with full data: {len(bb)}")

    recs, dropped = [], []
    for _, r in bb.iterrows():
        s = get_prices(r["symbol"], r["record_date"])
        if s is None:
            continue
        cum = last_buy_close(s, r["record_date"])       # the last close a tendering buyer can pay
        post = price_after(s, r["close_date"], RESIDUAL_LAG)
        if not cum or not cum[1] or not post:
            continue
        entry_date, entry = cum
        record_close = price_on_or_before(s, r["record_date"])   # kept for the ex-day drop audit
        ent = float(r["entitlement_small"])
        bp = float(r["buyback_price"])
        if not PREMIUM_BOUNDS[0] <= bp / entry - 1 <= PREMIUM_BOUNDS[1]:
            dropped.append((r["symbol"], round(bp / entry - 1, 2)))
            continue
        regime = "post_oct2024" if r["record_date"] >= TAX_CUTOVER else "pre_oct2024"
        recs.append({
            "symbol": r["symbol"],
            "record_date": r["record_date"],
            "entry_date": entry_date,
            "entry": entry,
            # audit of the old flaw: the record-day (ex-entitlement) close vs the cum entry
            "ex_day_move": (record_close / entry - 1) if record_close else None,
            "regime": regime,
            # market cap AS OF the record date (WP5) — today's cap would be lookahead
            "mcap_bucket": mcap_bucket_at(r["symbol"], r["record_date"].date()),
            "premium": bp / entry - 1,
            "gross_floor": arb_return(entry, bp, post, ent),
            "gross_full": arb_return(entry, bp, post, min(ent * 3, 1.0)),
            "aftertax_floor": after_tax_return(entry, bp, post, ent, regime=regime, slab=SLAB),
            "aftertax_now": after_tax_return(entry, bp, post, ent, regime="post_oct2024", slab=SLAB),
            "aftertax_full_now": after_tax_return(entry, bp, post, min(ent * 3, 1.0),
                                                  regime="post_oct2024", slab=SLAB),
            # today's rules at 3x entitlement for lower slabs (the verdict is slab-conditional)
            **{f"aftertax_full_now_{int(sl * 100)}": after_tax_return(
                entry, bp, post, min(ent * 3, 1.0), regime="post_oct2024", slab=sl)
               for sl in LOW_SLABS},
        })
    if dropped:
        print(f"Dropped {len(dropped)} implausible premiums: {dropped}")
    d = exclude_results(pd.DataFrame(recs), "record_date", args.exclude_results_window)
    if d.empty:
        print("No events with usable prices.")
        return None

    def show(label, col, sub=None):
        x = (sub if sub is not None else d)[col].dropna()
        if len(x) == 0:
            print(f"  {label:<34} n=0"); return
        print(f"  {label:<34} n={len(x):>3}  mean={x.mean()*100:+6.2f}%  "
              f"median={x.median()*100:+6.2f}%  win={ (x>0).mean()*100:4.0f}%")

    print(f"\n=== BUYBACK TENDER ARB ({len(d)} events, record dates {d.record_date.min():%b-%Y} -> "
          f"{d.record_date.max():%b-%Y}, ~Rs 2L, entry = last CUM-entitlement close, "
          f"entitlement-floor acceptance) ===")
    show("Record-day (ex) close vs cum entry", "ex_day_move")
    show("Avg buyback premium vs entry", "premium")
    show("GROSS return (entitlement floor)", "gross_floor")
    show("GROSS return (3x entitlement)", "gross_full")
    show("AFTER-TAX (regime of the day)", "aftertax_floor")
    show("AFTER-TAX (today's rules, 30% slab)", "aftertax_now")
    show("AFTER-TAX today's rules @ 3x entitl.", "aftertax_full_now")
    for sl in LOW_SLABS:
        show(f"  ... same at a {int(sl * 100)}% slab", f"aftertax_full_now_{int(sl * 100)}")
    print("\n  -- by tax regime (gross floor) --")
    show("pre-Oct-2024 events", "gross_floor", d[d.regime == "pre_oct2024"])
    show("post-Oct-2024 events", "gross_floor", d[d.regime == "post_oct2024"])
    print("\n  -- gross floor, by market cap AS OF the record date (the acceptance prior's buckets) --")
    for b in ("small", "small_mid", "mid", "large", "unknown"):
        show(b, "gross_floor", d[d.mcap_bucket == b])
    print("\n  -- after-tax floor, by regime --")
    show("pre-Oct-2024 (tax-free buyback)", "aftertax_floor", d[d.regime == "pre_oct2024"])
    show("post-Oct-2024 (dividend-taxed)", "aftertax_floor", d[d.regime == "post_oct2024"])
    return {"results": d}


if __name__ == "__main__":
    run("buyback_arb", main)
