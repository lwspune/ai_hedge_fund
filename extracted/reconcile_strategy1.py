"""Cell-by-cell reconciliation of Strategy 1 against the xlsx.

Sheet model (verified from formulas):
  - B[d] = d  (linear weight = "rupees invested" on day d if signal fires)
  - Signal fires when gain_100dma_50dma < 0
  - AB[d] = -B[d] if signal, else 0
  - AC[d] = AB[d] / E[d]  (= shares bought, negative)
  - Closeout: AB[last] = -E[last] * SUM(AC[d] for d in 6..4940)
  - XIRR(AB6:AB4941, D6:D4941) = headline result

Reproducing this in Python:
  1. price_gain = close.pct_change()  → fillna(0) to match sheet's blank-as-zero
  2. gain_100dma = LWMA(price_gain, 100)
  3. gain_100dma_50dma = LWMA(gain_100dma, 50) - baseline (R4 = 0)
  4. signal = gain_100dma_50dma < 0
  5. weight = 1, 2, ..., n
  6. amount = -weight if signal else 0
  7. shares = amount / close
  8. closeout = -close[last] * sum(shares)
  9. cash_flows[last] = closeout (override)
  10. xirr(cash_flows, dates) → compare to sheet's AC4
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


def compare(label: str, mine: pd.Series, theirs: pd.Series, atol=1e-6, rtol=1e-4):
    """Side-by-side comparison with diagnostic output."""
    aligned = pd.DataFrame({"mine": mine, "theirs": theirs})
    both_valid = aligned.dropna()
    print(f"\n--- {label} ---")
    print(f"  My valid: {mine.notna().sum()}, theirs valid: {theirs.notna().sum()}, both valid: {len(both_valid)}")
    if len(both_valid) == 0:
        print("  No overlap to compare!")
        return False
    diff = (both_valid["mine"] - both_valid["theirs"]).abs()
    max_diff = diff.max()
    print(f"  Max abs diff: {max_diff:.6g}")
    print(f"  Mean abs diff: {diff.mean():.6g}")
    # Show first 3 disagreements
    tol_mask = diff > (atol + rtol * both_valid["theirs"].abs())
    disagreements = both_valid[tol_mask]
    if len(disagreements) > 0:
        print(f"  DISAGREEMENTS ({len(disagreements)} of {len(both_valid)}):")
        print(disagreements.head(5).to_string())
        return False
    else:
        print(f"  MATCH (within atol={atol}, rtol={rtol})")
        return True


def main():
    sheet = pd.read_csv(SHEET_DATA, parse_dates=["date"]).set_index("date")
    print(f"Loaded sheet data: {len(sheet)} rows, {sheet.index[0].date()} -> {sheet.index[-1].date()}")

    close = sheet["close"].copy()
    n = len(close)

    # --- Step 1: Reproduce moving averages ---
    print("\n" + "=" * 70)
    print("STEP 1: Moving averages (LWMA of close)")
    print("=" * 70)
    mine_ma_20 = lwma(close, 20)
    mine_ma_50 = lwma(close, 50)
    mine_ma_100 = lwma(close, 100)
    mine_ma_200 = lwma(close, 200)
    mine_ma_300 = lwma(close, 300)

    compare("MA_20",  mine_ma_20,  sheet["MA_20"])
    compare("MA_50",  mine_ma_50,  sheet["MA_50"])
    compare("MA_100", mine_ma_100, sheet["MA_100"])
    compare("MA_200", mine_ma_200, sheet["MA_200"])
    compare("MA_300", mine_ma_300, sheet["MA_300"])

    # --- Step 2: Reproduce daily price gain ---
    print("\n" + "=" * 70)
    print("STEP 2: Price Gain (N) = E/E_prev - 1")
    print("=" * 70)
    mine_price_gain = close.pct_change()
    # Sheet has price_gain blank at first row (N7 is first formula). Compare from idx 1+.
    compare("price_gain (raw)", mine_price_gain, sheet["price_gain"])

    # --- Step 3: Reproduce Gain_100DMA (Q) = LWMA(price_gain, 100) ---
    print("\n" + "=" * 70)
    print("STEP 3: Gain_100DMA = LWMA(Price Gain, 100)")
    print("=" * 70)
    # The sheet's SUMPRODUCT treats blank N6 as 0. fillna(0) on the leading NaN.
    price_gain_safe = mine_price_gain.fillna(0)
    mine_gain_100dma = lwma(price_gain_safe, 100)
    compare("gain_100dma (with fillna(0))", mine_gain_100dma, sheet["gain_100dma"])

    # Without the fillna fix, for comparison
    mine_gain_100dma_naive = lwma(mine_price_gain, 100)
    compare("gain_100dma (NaN propagation, my v1 bug)", mine_gain_100dma_naive, sheet["gain_100dma"])

    # --- Step 4: Reproduce Gain_100DMA_50DMA (R) ---
    print("\n" + "=" * 70)
    print("STEP 4: Gain_100DMA_50DMA = LWMA(Gain_100DMA, 50) - R4")
    print("=" * 70)
    # R4 baseline is empty in xlsx → 0
    mine_gain_100_50 = lwma(mine_gain_100dma, 50)
    compare("gain_100dma_50dma", mine_gain_100_50, sheet["gain_100dma_50dma"])

    # --- Step 5: Reproduce Strategy 1 amount column ---
    print("\n" + "=" * 70)
    print("STEP 5: Strategy 1 amount (AB) = IF(R<0, -B, 0)")
    print("=" * 70)
    weight = np.arange(1, n + 1, dtype=float)  # B = 1, 2, ..., n
    signal = (mine_gain_100_50 < 0) & mine_gain_100_50.notna()
    mine_amount = pd.Series(np.where(signal, -weight, 0.0), index=close.index)

    # Compare excluding last row (which has a different closeout formula)
    compare("strategy1_amt (excluding last row)",
            mine_amount.iloc[:-1], sheet["strategy1_amt"].iloc[:-1])

    # --- Step 6: Reproduce shares and closeout ---
    print("\n" + "=" * 70)
    print("STEP 6: Shares bought + closeout")
    print("=" * 70)
    mine_shares = mine_amount / close.values  # element-wise
    # Exclude last row from share calc (sheet sets shares at last via different formula)
    total_shares = mine_shares.iloc[:-1].sum()
    closeout_value = -close.iloc[-1] * total_shares  # = positive cash flow
    print(f"  Total signal fires (mine): {int(signal.iloc[:-1].sum())} (sheet: {int(sheet['strategy1_amt'].iloc[:-1].lt(0).sum())})")
    print(f"  Sum of -weights for signal days (mine): {-mine_amount.iloc[:-1].sum():,.2f}")
    print(f"  Sum of -weights for signal days (sheet): {-sheet['strategy1_amt'].iloc[:-1].sum():,.2f}")
    print(f"  Total shares accumulated (mine): {total_shares:,.4f}")
    print(f"  Closeout value (mine): Rs.{closeout_value:,.2f}")
    print(f"  Closeout value (sheet AB last row): Rs.{sheet['strategy1_amt'].iloc[-1]:,.2f}")

    # --- Step 7: XIRR ---
    print("\n" + "=" * 70)
    print("STEP 7: XIRR")
    print("=" * 70)
    mine_amount_with_closeout = mine_amount.copy()
    mine_amount_with_closeout.iloc[-1] = closeout_value
    # Build cash flow list (only non-zero entries with dates)
    cash_dates = mine_amount_with_closeout.index.tolist()
    cash_values = mine_amount_with_closeout.values.tolist()
    my_xirr_result = xirr(cash_dates, cash_values)
    print(f"  My XIRR:    {my_xirr_result:.6f} = {my_xirr_result * 100:.4f}%")
    print(f"  Sheet AC4:  0.054606 = 5.4606%")
    diff_pp = (my_xirr_result - 0.054606) * 100
    print(f"  Difference: {diff_pp:+.4f} pp")


if __name__ == "__main__":
    main()
