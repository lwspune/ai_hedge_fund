"""Run all 6 strategies on the full Nifty 50 universe — find where the signals work.

For each stock:
  - Fetch 16.4 years of close prices (cached)
  - Compute all 6 strategy XIRRs under the DCA model (verified sheet-exact)
  - Compute buy-and-hold CAGR
  - Best strategy alpha = max(strategy XIRR) - B&H CAGR

Output a sortable cross-section table.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from pyxirr import xirr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ai_hedge_fund.moving_averages import lwma
from ai_hedge_fund.data import fetch_ohlc

START = "2009-12-01"
END = "2026-05-09"


def make_signals(close: pd.Series) -> dict[str, pd.Series]:
    ma_50 = lwma(close, 50)
    ma_100 = lwma(close, 100)
    ma_200 = lwma(close, 200)
    ma_300 = lwma(close, 300)
    price_gain = close.pct_change()
    gain_100 = lwma(price_gain.fillna(0), 100)
    gain_100_50 = lwma(gain_100, 50)
    gain_200 = lwma(price_gain.fillna(0), 200)
    gain_200_50 = lwma(gain_200, 50)
    v = (close > ma_50).astype(int) * 2 - 1
    w = (ma_50 > ma_100).astype(int) * 2 - 1
    x = (ma_100 > ma_200).astype(int) * 2 - 1
    valid = ma_50.notna() & ma_100.notna() & ma_200.notna()
    T = ((v + w + x) / 1000.0).where(valid, np.nan)
    R, P, E, L, F = gain_100_50, gain_200_50, close, ma_50, ma_300
    E_prev = close.shift(1)
    return {
        "S1":  (R < 0).fillna(False),
        "S2a": ((R < 0) & (T < 0)).fillna(False),
        "S2b": ((R < 0) & (T < -0.001)).fillna(False),
        "S3":  ((R < 0) & (E <= L) & (L <= F)).fillna(False),
        "S4a": ((R < 0) & (E < F) & (E_prev <= L) & (E >= L)).fillna(False),
        "S4b": ((P < 0) & (R < 0) & (E < F) & (E_prev <= L) & (E >= L)).fillna(False),
    }


def dca_xirr(close: pd.Series, signal: pd.Series) -> float:
    n = len(close)
    weight = np.arange(1, n + 1, dtype=float)
    amount = np.where(signal.values & close.notna().values, -weight, 0.0)
    if (amount < 0).sum() == 0:
        return float("nan")
    shares = amount / close.values
    total_shares = shares[:-1].sum()
    closeout = -close.iloc[-1] * total_shares
    amount[-1] = closeout
    try:
        return float(xirr(list(close.index), amount.tolist()))
    except Exception:
        return float("nan")


def bh_cagr(close: pd.Series) -> float:
    days = (close.index[-1] - close.index[0]).days
    if days <= 0 or close.iloc[0] <= 0:
        return float("nan")
    return (close.iloc[-1] / close.iloc[0]) ** (365.25 / days) - 1


def run_one(ticker: str) -> dict | None:
    df = fetch_ohlc(ticker, START, END)
    if df.empty or "Close" not in df.columns:
        return None
    close = df["Close"].dropna()
    if len(close) < 350:
        return None
    sigs = make_signals(close)
    row = {"ticker": ticker, "bars": len(close), "bh_cagr": bh_cagr(close)}
    for name, sig in sigs.items():
        row[name] = dca_xirr(close, sig)
    strat_vals = [row[s] for s in ("S1", "S2a", "S2b", "S3", "S4a", "S4b") if not pd.isna(row[s])]
    if strat_vals:
        row["best"] = max(strat_vals)
        row["best_name"] = max(
            (s for s in ("S1", "S2a", "S2b", "S3", "S4a", "S4b") if not pd.isna(row[s])),
            key=lambda s: row[s],
        )
        row["alpha"] = row["best"] - row["bh_cagr"]
    return row


def main():
    csv_path = Path(__file__).resolve().parent.parent / "data" / "universe_nifty50.csv"
    tickers = pd.read_csv(csv_path)["ticker"].tolist()
    print(f"Running on {len(tickers)} Nifty 50 tickers...\n")

    rows = []
    for t in tickers:
        try:
            r = run_one(t)
        except Exception as e:
            print(f"  ! {t}: {e}")
            continue
        if r is None:
            print(f"  ! {t}: no usable data")
            continue
        rows.append(r)

    if not rows:
        print("No data!")
        return

    df = pd.DataFrame(rows)
    df["years"] = df["bars"] / 252.0  # approx trading-day-to-year

    # Sort by alpha descending
    df = df.sort_values("alpha", ascending=False).reset_index(drop=True)

    print(f"\n{'=' * 110}")
    print(f"NIFTY 50 CROSS-SECTION  ({len(df)} stocks with usable data)")
    print(f"{'=' * 110}")
    print(f"Sorted by best-strategy alpha vs B&H, descending\n")

    pct = lambda v: f"{v*100:>+7.2f}%" if not pd.isna(v) else "  N/A  "
    header = f"{'Rank':>4}  {'Ticker':<14} {'Yrs':>5} {'B&H':>9}  {'S1':>9} {'S2a':>9} {'S2b':>9} {'S3':>9} {'S4a':>9} {'S4b':>9}  {'Best':>9}  {'Alpha':>9}"
    print(header)
    print("-" * len(header))
    for i, row in df.iterrows():
        print(
            f"{i+1:>4}  {row['ticker']:<14} "
            f"{row['years']:>5.1f} {pct(row['bh_cagr'])}  "
            f"{pct(row['S1'])} {pct(row['S2a'])} {pct(row['S2b'])} {pct(row['S3'])} {pct(row['S4a'])} {pct(row['S4b'])}  "
            f"{pct(row['best'])}  {pct(row['alpha'])}"
        )

    # Summary
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    pos_alpha = (df["alpha"] > 0).sum()
    neg_alpha = (df["alpha"] < 0).sum()
    print(f"  Stocks where best strategy beats B&H:  {pos_alpha} / {len(df)}  ({pos_alpha/len(df)*100:.1f}%)")
    print(f"  Stocks where every strategy loses B&H: {neg_alpha} / {len(df)}  ({neg_alpha/len(df)*100:.1f}%)")
    print(f"  Median best-strategy alpha: {df['alpha'].median()*100:+.2f}pp")
    print(f"  Mean best-strategy alpha:   {df['alpha'].mean()*100:+.2f}pp")
    print(f"  Max alpha: {df['alpha'].max()*100:+.2f}pp ({df.iloc[0]['ticker']})")
    print(f"  Min alpha: {df['alpha'].min()*100:+.2f}pp ({df.iloc[-1]['ticker']})")
    print()
    print("Best strategy frequency (which rule wins most often):")
    print(df["best_name"].value_counts().to_string())

    out = Path(__file__).resolve().parent / "_nifty50_cross_section.csv"
    df.to_csv(out, index=False)
    print(f"\nFull table saved to {out}")


if __name__ == "__main__":
    main()
