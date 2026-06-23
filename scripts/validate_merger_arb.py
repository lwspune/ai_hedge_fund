"""Validate stock-swap merger arbitrage (Form B) over verified Indian deals.

For each fixed-ratio stock swap: at announcement the target should trade below
deal value (= ratio x acquirer price). The hedged arb -- long target, short
`ratio` acquirer via futures -- locks that spread, realised at completion.

We compute the announcement-window spread (both legs from nselib, actual
unadjusted prices) and annualise it over the time to completion. All four deals
completed; Zee-Sony (separate) is the cautionary break.

    python scripts/validate_merger_arb.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# (label, target_sym, acquirer_sym, ratio[acq per target], announce, complete)
DEALS = [
    ("HDFC->HDFCBANK",  "HDFC",       "HDFCBANK",   42 / 25, "2022-04-04", "2023-07-01"),
    ("MINDTREE->LTI",   "MINDTREE",   "LTI",        73 / 100, "2022-05-06", "2022-11-14"),
    ("INOX->PVR",       "INOXLEISURE","PVR",        3 / 10,  "2022-03-27", "2023-02-06"),
    ("SHRIRAMCIT->STFC","SHRIRAMCIT", "SRTRANSFIN", 1.55,    "2021-12-13", "2022-11-30"),
]
ENTRY_LAG = 2  # trading days after announcement (let prices settle)


def nse_close_on_or_after(symbol: str, start: str, lag: int):
    from nselib import capital_market as cm
    s = pd.Timestamp(start)
    f = s.strftime("%d-%m-%Y")
    t = (s + pd.Timedelta(days=18)).strftime("%d-%m-%Y")
    df = cm.price_volume_and_deliverable_position_data(symbol=symbol, from_date=f, to_date=t)
    if df is None or len(df) == 0:
        return None, None
    df = df.copy()
    if "Series" in df.columns:
        df = df[df["Series"].astype(str).str.strip() == "EQ"]  # equity only, not warrants/NCDs
    df["d"] = pd.to_datetime(df["Date"], format="%d-%b-%Y", errors="coerce")
    df = df.dropna(subset=["d"]).sort_values("d")
    df = df[df["d"] >= s]
    if len(df) <= lag:
        return None, None
    row = df.iloc[lag]
    close = float(str(row["ClosePrice"]).replace(",", ""))
    return close, row["d"]


def main():
    print(f"{'DEAL':<20}{'TGT':>9}{'ACQ':>9}{'DEALVAL':>9}{'SPREAD':>8}{'DAYS':>6}{'ANNUALISED':>12}")
    print("-" * 73)
    spreads, annuals = [], []
    for label, tgt, acq, ratio, ann, comp in DEALS:
        pt, dt = nse_close_on_or_after(tgt, ann, ENTRY_LAG)
        pa, da = nse_close_on_or_after(acq, ann, ENTRY_LAG)
        if pt is None or pa is None:
            print(f"{label:<20}  price missing (tgt={pt}, acq={pa})")
            continue
        deal_val = ratio * pa
        spread = deal_val / pt - 1.0
        days = (pd.Timestamp(comp) - dt).days
        annual = (1 + spread) ** (365 / days) - 1 if days > 0 else float("nan")
        spreads.append(spread)
        annuals.append(annual)
        print(f"{label:<20}{pt:>9,.1f}{pa:>9,.1f}{deal_val:>9,.1f}"
              f"{spread*100:>7.1f}%{days:>6}{annual*100:>11.1f}%")
    print("-" * 73)
    if spreads:
        n = len(spreads)
        print(f"n={n} completed deals | mean spread {sum(spreads)/n*100:+.1f}% | "
              f"mean annualised {sum(annuals)/n*100:+.1f}% | all completed")
    print("\nNote: positive spread = target cheap vs deal value -> long target / short "
          f"{ '{ratio}' } acquirer (futures) captures it at completion.")
    print("Break risk (not in sample): Zee-Sony called off Jan 2024 -> ZEEL fell ~30% "
          "in days. One break can erase many completed-deal spreads.")


if __name__ == "__main__":
    main()
