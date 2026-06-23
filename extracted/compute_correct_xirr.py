"""Compute the CORRECT XIRR for all 6 Buy_Signal strategies on RELIANCE.

Uses the verified DCA cash flow model from the sheet:
  - On signal day d: invest B[d] = d rupees → buy B[d]/E[d] shares
  - On final day: sell all accumulated shares at E[last]
  - XIRR of the resulting cash flow stream

For comparison, also computes:
  - The sheet's BROKEN XIRR (reproduces by adding phantom cash flow at 1899-12-30)
  - Buy-and-hold XIRR for the stock over the same period
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from pyxirr import xirr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ai_hedge_fund.moving_averages import lwma

SHEET_DATA = Path(r"c:\Users\vilas\Downloads\AI_Hedge_Fund\extracted\_aapl_sheet_data.csv")
PHANTOM_DATE = pd.Timestamp("1899-12-30")  # sheet's blank-cell epoch
PHANTOM_AMT_FN = lambda n: -float(n + 1)  # AB at the phantom row = -(n+1) when n = data length


def make_signals(close: pd.Series) -> dict[str, pd.Series]:
    """Reproduce the 6 strategy signals using sheet-exact formulas."""
    # All MAs use LWMA per the sheet
    ma_50 = lwma(close, 50)
    ma_100 = lwma(close, 100)
    ma_200 = lwma(close, 200)
    ma_300 = lwma(close, 300)

    # Price Gain (col N) — keep NaN at idx 0
    price_gain = close.pct_change()

    # Gain_100DMA (Q) — sheet uses SUMPRODUCT which treats blank as 0
    gain_100 = lwma(price_gain.fillna(0), 100)
    # Gain_100DMA_50DMA (R)
    gain_100_50 = lwma(gain_100, 50)  # baseline R4 = 0

    # Gain_200DMA (O) and Gain_200DMA_50DMA (P)
    gain_200 = lwma(price_gain.fillna(0), 200)
    gain_200_50 = lwma(gain_200, 50)

    # Price Signal (T) = (Price_GT_50 + 50_GT_100 + 100_GT_200) / 1000
    v = ((close > ma_50).astype(int) * 2 - 1)
    w = ((ma_50 > ma_100).astype(int) * 2 - 1)
    x = ((ma_100 > ma_200).astype(int) * 2 - 1)
    valid = ma_50.notna() & ma_100.notna() & ma_200.notna()
    price_signal = ((v + w + x) / 1000.0).where(valid, np.nan)

    R = gain_100_50
    P = gain_200_50
    E = close
    L = ma_50
    F = ma_300
    T = price_signal
    E_prev = close.shift(1)

    sigs = {
        "S1 (R<0)":               (R < 0).fillna(False),
        "S2a (R<0 & PS<0)":       ((R < 0) & (T < 0)).fillna(False),
        "S2b (R<0 & PS<-0.001)":  ((R < 0) & (T < -0.001)).fillna(False),
        "S3 (R<0 & E<=L<=F)":     ((R < 0) & (E <= L) & (L <= F)).fillna(False),
        "S4a (S1 + cross-up 50)": ((R < 0) & (E < F) & (E_prev <= L) & (E >= L)).fillna(False),
        "S4b (S4a + P<0)":        ((P < 0) & (R < 0) & (E < F) & (E_prev <= L) & (E >= L)).fillna(False),
    }
    return sigs


def dca_xirr(close: pd.Series, signal: pd.Series, with_phantom: bool = False) -> dict:
    """Sheet's DCA model: invest B[d]=d rupees on each signal day, sell all at end."""
    n = len(close)
    weight = np.arange(1, n + 1, dtype=float)  # B[d] = 1, 2, ..., n
    amount = np.where(signal.values & (close.notna().values), -weight, 0.0)
    shares = amount / close.values  # negative shares = bought
    total_shares = shares[:-1].sum()  # exclude last row from accumulation (sheet convention)
    closeout = -close.iloc[-1] * total_shares  # positive cash flow
    amount[-1] = closeout

    cash_dates = list(close.index)
    cash_values = amount.tolist()
    if with_phantom:
        cash_dates = [PHANTOM_DATE] + cash_dates
        cash_values = [PHANTOM_AMT_FN(n)] + cash_values

    try:
        r = xirr(cash_dates, cash_values)
    except Exception as e:
        r = float("nan")

    return {
        "fires": int(signal.sum()),
        "invested": -amount[:-1].sum(),
        "shares": -total_shares,
        "closeout": closeout,
        "multiplier": closeout / (-amount[:-1].sum()) if amount[:-1].sum() != 0 else float("nan"),
        "xirr": r,
    }


def main():
    sheet = pd.read_csv(SHEET_DATA, parse_dates=["date"]).set_index("date")
    close = sheet["close"].dropna()
    print(f"Stock: RELIANCE")
    print(f"Period: {close.index[0].date()} -> {close.index[-1].date()}  ({len(close)} trading days, {(close.index[-1]-close.index[0]).days/365.25:.2f} years)")
    print(f"First close: Rs.{close.iloc[0]:.2f}, last close: Rs.{close.iloc[-1]:.2f}")
    bh_multiplier = close.iloc[-1] / close.iloc[0]
    bh_cagr = bh_multiplier ** (365.25 / (close.index[-1] - close.index[0]).days) - 1
    print(f"Buy-and-hold multiplier: {bh_multiplier:.3f}x  CAGR: {bh_cagr*100:.2f}%")
    print()

    sigs = make_signals(close)

    print("=" * 110)
    print(f"{'Strategy':<25} {'Fires':>7} {'Invested':>15} {'Shares':>12} {'Closeout':>15} {'x':>6} {'CORRECT XIRR':>14} {'Sheet (buggy)':>16}")
    print("=" * 110)
    rows = []
    for name, sig in sigs.items():
        clean = dca_xirr(close, sig, with_phantom=False)
        buggy = dca_xirr(close, sig, with_phantom=True)
        rows.append((name, clean, buggy))
        print(
            f"{name:<25} "
            f"{clean['fires']:>7,} "
            f"Rs.{clean['invested']:>12,.0f} "
            f"{clean['shares']:>12.2f} "
            f"Rs.{clean['closeout']:>12,.0f} "
            f"{clean['multiplier']:>5.2f}x "
            f"{clean['xirr']*100:>+12.4f}%  "
            f"{buggy['xirr']*100:>+14.4f}%"
        )
    print("-" * 110)
    print(f"{'Buy-and-hold (benchmark)':<25} {'-':>7} {'-':>15} {'-':>12} {'-':>15} {bh_multiplier:>5.2f}x {bh_cagr*100:>+12.4f}%  {'-':>14}")
    print()
    print("CORRECT XIRR = computed with valid dates only (clean cash flow stream)")
    print("Sheet (buggy) = reproduces the sheet's broken value by adding a phantom -Rs.B at 1899-12-30")
    print()
    print("Note: 'Sheet (buggy)' depends on B value of the phantom row, which is exactly n+1")
    print("      where n = total spreadsheet data rows. For RELIANCE n=4049, phantom = -4050")
    print("      (my earlier reconciliation matched at phantom = -4049 to within 0.0001 pp)")


if __name__ == "__main__":
    main()
