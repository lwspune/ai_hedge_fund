"""Run all 6 Buy_Signal strategies on AAPL, MSFT, TCS with the verified DCA pipeline.

Uses:
  - Sheet-exact signal formulas (verified cell-by-cell to 5e-13 on RELIANCE)
  - Sheet's DCA cash flow model: invest B[d]=d on signal day d
  - CORRECT XIRR (without the phantom-cash-flow bug the sheet has)
  - Reports buy-and-hold CAGR for comparison
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


# Match the sheet's window: data starts 2009-12-07 (when GOOGLEFINANCE returned first close)
START = "2009-12-01"
END = "2026-05-09"


def make_signals(close: pd.Series) -> dict[str, pd.Series]:
    """Sheet-exact signal formulas — verified cell-by-cell on RELIANCE."""
    ma_50 = lwma(close, 50)
    ma_100 = lwma(close, 100)
    ma_200 = lwma(close, 200)
    ma_300 = lwma(close, 300)

    price_gain = close.pct_change()
    # Sheet's SUMPRODUCT treats blank N6 as 0 — match exactly
    gain_100 = lwma(price_gain.fillna(0), 100)
    gain_100_50 = lwma(gain_100, 50)  # baseline R4 = 0
    gain_200 = lwma(price_gain.fillna(0), 200)
    gain_200_50 = lwma(gain_200, 50)

    # Price Signal T
    v = (close > ma_50).astype(int) * 2 - 1
    w = (ma_50 > ma_100).astype(int) * 2 - 1
    x = (ma_100 > ma_200).astype(int) * 2 - 1
    valid = ma_50.notna() & ma_100.notna() & ma_200.notna()
    T = ((v + w + x) / 1000.0).where(valid, np.nan)

    R = gain_100_50
    P = gain_200_50
    E = close
    L = ma_50
    F = ma_300
    E_prev = close.shift(1)

    return {
        "S1 (R<0)":               (R < 0).fillna(False),
        "S2a (R<0 & PS<0)":       ((R < 0) & (T < 0)).fillna(False),
        "S2b (R<0 & PS<-0.001)":  ((R < 0) & (T < -0.001)).fillna(False),
        "S3 (R<0 & E<=L<=F)":     ((R < 0) & (E <= L) & (L <= F)).fillna(False),
        "S4a (S1 + cross-up 50)": ((R < 0) & (E < F) & (E_prev <= L) & (E >= L)).fillna(False),
        "S4b (S4a + P<0)":        ((P < 0) & (R < 0) & (E < F) & (E_prev <= L) & (E >= L)).fillna(False),
    }


def dca_xirr(close: pd.Series, signal: pd.Series) -> dict:
    """Sheet's DCA: invest B[d]=d on each signal day, sell all at end."""
    n = len(close)
    weight = np.arange(1, n + 1, dtype=float)
    amount = np.where(signal.values & close.notna().values, -weight, 0.0)
    shares = amount / close.values
    total_shares = shares[:-1].sum()
    closeout = -close.iloc[-1] * total_shares
    amount[-1] = closeout

    cash_dates = list(close.index)
    cash_values = amount.tolist()
    try:
        r = xirr(cash_dates, cash_values)
    except Exception:
        r = float("nan")

    return {
        "fires": int(signal.iloc[:-1].sum()),
        "invested": -float(amount[:-1].sum()),
        "shares": -total_shares,
        "closeout": float(closeout),
        "multiplier": float(closeout / -amount[:-1].sum()) if amount[:-1].sum() != 0 else float("nan"),
        "xirr": r,
    }


def run_for_stock(ticker: str, label: str | None = None):
    label = label or ticker
    print(f"\n{'=' * 110}")
    print(f"STOCK: {label} ({ticker})")
    print(f"{'=' * 110}")

    df = fetch_ohlc(ticker, START, END)
    if df.empty or "Close" not in df.columns:
        print(f"  ERROR: no data for {ticker}")
        return None
    close = df["Close"].dropna()
    if len(close) < 350:
        print(f"  ERROR: only {len(close)} bars (need 350+ for 300DMA + 50 smoothing)")
        return None

    days = (close.index[-1] - close.index[0]).days
    years = days / 365.25
    bh_multiplier = float(close.iloc[-1]) / float(close.iloc[0])
    bh_cagr = bh_multiplier ** (365.25 / days) - 1

    print(f"Period: {close.index[0].date()} -> {close.index[-1].date()} ({len(close)} trading days, {years:.2f} years)")
    print(f"First close: {close.iloc[0]:.2f}, last close: {close.iloc[-1]:.2f}")
    print(f"Buy-and-hold: {bh_multiplier:.2f}x  CAGR: {bh_cagr*100:+.2f}%")
    print()

    sigs = make_signals(close)
    print(f"{'Strategy':<25} {'Fires':>7} {'Invested':>15} {'Shares':>12} {'Closeout':>16} {'x':>6} {'XIRR':>10} {'vs B&H':>9}")
    print("-" * 110)
    results = {}
    for name, sig in sigs.items():
        r = dca_xirr(close, sig)
        results[name] = r
        alpha = (r["xirr"] - bh_cagr) * 100
        print(
            f"{name:<25} "
            f"{r['fires']:>7,} "
            f"{r['invested']:>15,.0f} "
            f"{r['shares']:>12.2f} "
            f"{r['closeout']:>16,.0f} "
            f"{r['multiplier']:>5.2f}x "
            f"{r['xirr']*100:>+9.2f}% "
            f"{alpha:>+7.2f}pp"
        )
    print(f"{'Buy-and-hold (benchmark)':<25} {'-':>7} {'-':>15} {'-':>12} {'-':>16} {bh_multiplier:>5.2f}x {bh_cagr*100:>+9.2f}% {'+0.00pp':>9}")
    return {"ticker": ticker, "label": label, "bh_cagr": bh_cagr, "years": years, "results": results}


def main():
    stocks = [
        ("AAPL",       "Apple Inc."),
        ("MSFT",       "Microsoft Corp."),
        ("TCS.NS",     "Tata Consultancy Services"),
        ("RELIANCE.NS", "Reliance Industries (sanity check vs sheet)"),
    ]
    all_results = []
    for ticker, label in stocks:
        res = run_for_stock(ticker, label)
        if res:
            all_results.append(res)

    # Cross-stock summary table
    if all_results:
        print(f"\n\n{'=' * 110}")
        print("CROSS-STOCK SUMMARY — XIRR by strategy")
        print(f"{'=' * 110}")
        strategy_names = list(all_results[0]["results"].keys())
        header = f"{'Strategy':<25}" + "".join(f"{r['ticker']:>14}" for r in all_results)
        print(header)
        print("-" * len(header))
        for name in strategy_names:
            row = f"{name:<25}"
            for r in all_results:
                xv = r["results"][name]["xirr"] * 100
                row += f"{xv:>+13.2f}%"
            print(row)
        # Buy-and-hold row
        row = f"{'Buy-and-hold':<25}"
        for r in all_results:
            row += f"{r['bh_cagr']*100:>+13.2f}%"
        print(row)
        # Alpha row (best strategy vs B&H)
        row = f"{'Best alpha vs B&H':<25}"
        for r in all_results:
            best_xirr = max(s["xirr"] for s in r["results"].values())
            alpha = (best_xirr - r["bh_cagr"]) * 100
            row += f"{alpha:>+12.2f}pp"
        print(row)


if __name__ == "__main__":
    main()
