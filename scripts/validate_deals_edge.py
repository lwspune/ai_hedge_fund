"""Validate the bulk/block-deal 'smart money' edge with an event study.

Question: does a public follower, entering at T+1 after a notable institutional
BUY is disclosed, earn positive benchmark-adjusted returns? Placebo: the same
for prop/LLP buys -- if institutions outperform and prop doesn't, the classifier
captures real signal rather than 'deals cluster in moving stocks'.

    python scripts/validate_deals_edge.py

Caches raw deals + prices under cache/ so re-runs are fast.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner.deals import classify_client, NOTABLE          # noqa: E402
from scanner.eventstudy import forward_abnormal_return, summarize  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
PRICES = CACHE / "prices"
CACHE.mkdir(exist_ok=True)
PRICES.mkdir(exist_ok=True)

FROM, TO = "01-01-2024", "31-12-2025"   # events; all have T+60 within yfinance range
HORIZONS = [5, 20, 60]
VALUE_MIN = 1e7                          # >= 1 cr
BENCH = "^NSEI"


# --- deals (nselib, monthly chunks, cached) ---------------------------------

def _month_starts(frm, to):
    a, b = pd.to_datetime(frm, format="%d-%m-%Y"), pd.to_datetime(to, format="%d-%m-%Y")
    return pd.date_range(a, b, freq="MS")


def load_deals() -> pd.DataFrame:
    cache_file = CACHE / f"deals_{FROM}_{TO}.csv".replace("/", "-")
    if cache_file.exists():
        return pd.read_csv(cache_file, dtype=str)

    from nselib import capital_market as cm
    frames = []
    for ms in _month_starts(FROM, TO):
        me = (ms + pd.offsets.MonthEnd(0))
        f, t = ms.strftime("%d-%m-%Y"), me.strftime("%d-%m-%Y")
        for fn, kind in ((cm.bulk_deal_data, "bulk"), (cm.block_deals_data, "block")):
            for attempt in range(3):
                try:
                    df = fn(from_date=f, to_date=t)
                    if df is not None and len(df):
                        df["kind"] = kind
                        frames.append(df)
                    break
                except Exception as e:
                    print(f"  retry {kind} {f}: {repr(e)[:80]}")
                    time.sleep(3 + 3 * attempt)
        print(f"pulled {ms:%Y-%m} | running rows: {sum(len(x) for x in frames)}")
        time.sleep(1)
    deals = pd.concat(frames, ignore_index=True)
    deals.to_csv(cache_file, index=False)
    return deals


def normalize(deals: pd.DataFrame) -> pd.DataFrame:
    col = {c.lower().replace(" ", "").replace(".", "").replace("/", ""): c
           for c in deals.columns}

    def pick(*keys):
        for k in keys:
            if k in col:
                return col[k]
        raise KeyError(keys)

    out = pd.DataFrame({
        "date": pd.to_datetime(deals[pick("date")], format="%d-%b-%Y", errors="coerce"),
        "symbol": deals[pick("symbol")].astype(str).str.strip(),
        "client": deals[pick("clientname")].astype(str).str.strip(),
        "side": deals[pick("buysell")].astype(str).str.strip().str.upper(),
        "qty": pd.to_numeric(deals[pick("quantitytraded")].astype(str)
                             .str.replace(",", "", regex=False), errors="coerce"),
        "price": pd.to_numeric(deals[pick("tradepricewghtavgprice", "tradeprice")]
                               .astype(str).str.replace(",", "", regex=False), errors="coerce"),
    })
    out["value"] = out["qty"] * out["price"]
    out["category"] = out["client"].map(classify_client)
    out = out.dropna(subset=["date", "qty", "price"])
    return out


def build_events(norm: pd.DataFrame, categories) -> pd.DataFrame:
    """One event per (symbol, date) where a buy in `categories` cleared VALUE_MIN."""
    buys = norm[(norm["side"] == "BUY") & (norm["value"] >= VALUE_MIN)
                & (norm["category"].isin(categories))]
    ev = (buys.groupby(["symbol", "date"], as_index=False)
              .agg(value=("value", "sum"), n=("client", "nunique")))
    return ev


# --- prices (yfinance, cached per symbol) -----------------------------------

def get_prices(symbol: str) -> pd.Series | None:
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


def run_study(events: pd.DataFrame, bench: pd.Series, label: str) -> dict:
    by_h = {h: [] for h in HORIZONS}
    pre = []
    miss = 0
    for sym, grp in events.groupby("symbol"):
        s = get_prices(sym)
        if s is None:
            miss += grp.shape[0]
            continue
        for d in grp["date"]:
            for h in HORIZONS:
                by_h[h].append(forward_abnormal_return(s, bench, d, h, entry_lag=1))
            pre.append(forward_abnormal_return(s, bench, d, horizon=10, entry_lag=-10))
    print(f"\n=== {label} (events={len(events)}, price-missing rows={miss}) ===")
    print(f"  PRE-event T-10->T0 : {fmt(summarize(pre))}")
    for h in HORIZONS:
        print(f"  POST T+1->T+{h:<3}    : {fmt(summarize(by_h[h]))}")
    return by_h


def fmt(s: dict) -> str:
    if s["n"] == 0:
        return "n=0"
    return (f"n={s['n']:>4}  mean={s['mean']*100:+6.2f}%  median={s['median']*100:+6.2f}%  "
            f"win={s['pct_positive']*100:4.1f}%  t={s['t_stat']:+.2f}"
            if s["t_stat"] is not None else f"n={s['n']}")


def main():
    print("Loading deals (cached after first run)...")
    norm = normalize(load_deals())
    print(f"Normalized deals: {len(norm)} | categories: "
          f"{norm['category'].value_counts().to_dict()}")

    inst = build_events(norm, NOTABLE)
    prop = build_events(norm, {"prop_broker"})
    # Fair, bounded placebo: sample prop events down to the institutional count.
    if len(prop) > len(inst):
        prop = prop.sample(n=len(inst), random_state=42).reset_index(drop=True)
    print(f"\nInstitutional buy-events: {len(inst)} | Placebo (prop) buy-events: {len(prop)}")

    import yfinance as yf
    bh = yf.Ticker(BENCH).history(period="max", interval="1d", auto_adjust=True)["Close"].dropna()
    bh.index = bh.index.tz_localize(None)

    run_study(inst, bh, "INSTITUTIONAL BUYS")
    run_study(prop, bh, "PLACEBO: PROP/LLP BUYS")
    print("\nReading: post-event mean ~0 / t<2 => no follower edge; "
          "pre-event >> post => front-running (return already gone).")


if __name__ == "__main__":
    main()
