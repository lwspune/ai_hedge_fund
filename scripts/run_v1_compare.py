"""v1 comparison: Strategy 1 vs Strategy 1 INVERTED vs EW-Nifty buy-and-hold.

Adds per-year breakdown to dig into when each approach won/lost.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ai_hedge_fund.data import fetch_universe_closes
from ai_hedge_fund.signals import strategy_1, strategy_1_inverted, strategy_3
from ai_hedge_fund.backtest import run_backtest
from ai_hedge_fund.metrics import summarize


def yearly_returns(equity: pd.Series) -> pd.Series:
    """Per-calendar-year total return."""
    yearly = equity.resample("YE").last()
    yearly_start = equity.resample("YE").first()
    rets = (yearly / yearly_start - 1).rename(equity.name or "ret")
    rets.index = rets.index.year
    return rets


def main():
    START = "2018-01-01"
    END = "2026-05-10"
    INITIAL = 100_000.0
    COST_PER_LEG = 0.003

    print(f"\n{'=' * 80}")
    print("v1 COMPARISON: Strategy 1 (buy weakness) vs Inverted (buy strength) vs EW-Nifty")
    print(f"{'=' * 80}")
    print(f"Window: {START} -> {END}\n")

    csv_path = Path(__file__).resolve().parent.parent / "data" / "universe_nifty50.csv"
    tickers = pd.read_csv(csv_path)["ticker"].tolist()
    closes = fetch_universe_closes(tickers, START, END)
    print(f"Universe: {closes.shape[1]} tickers x {closes.shape[0]} days\n")

    # Strategy 1 (original)
    s1_signals = pd.DataFrame({t: strategy_1(closes[t]) for t in closes.columns}, index=closes.index)
    s1_eq = run_backtest(closes, s1_signals, INITIAL, COST_PER_LEG)["equity"].rename("S1")

    # Strategy 1 inverted
    s1i_signals = pd.DataFrame({t: strategy_1_inverted(closes[t]) for t in closes.columns}, index=closes.index)
    s1i_eq = run_backtest(closes, s1i_signals, INITIAL, COST_PER_LEG)["equity"].rename("S1_inverted")

    # Strategy 3 (deeper-weakness filter)
    s3_signals = pd.DataFrame({t: strategy_3(closes[t]) for t in closes.columns}, index=closes.index)
    s3_eq = run_backtest(closes, s3_signals, INITIAL, COST_PER_LEG)["equity"].rename("S3")

    # EW-Nifty buy-and-hold
    ew_eq = ((closes / closes.iloc[0]).mean(axis=1) * INITIAL).rename("EW_Nifty")

    # Aggregate metrics
    print("                       Strategy 1     S1 INVERTED     Strategy 3     EW-Nifty")
    print("                       (buy weak)     (buy strong)    (deeper weak)  (buy-hold)")
    print("-" * 95)
    for name, fn in [
        ("Final equity (Rs.)",   lambda e: f"{e.iloc[-1]:>12,.0f}"),
        ("Total return",         lambda e: f"{(e.iloc[-1]/e.iloc[0] - 1) * 100:>+11.2f}%"),
        ("CAGR",                 lambda e: f"{summarize(e)['cagr'] * 100:>+11.2f}%"),
        ("Sharpe",               lambda e: f"{summarize(e)['sharpe']:>12.2f}"),
        ("Sortino",              lambda e: f"{summarize(e)['sortino']:>12.2f}"),
        ("Max drawdown",         lambda e: f"{summarize(e)['max_drawdown'] * 100:>+11.2f}%"),
    ]:
        print(f"  {name:<22} {fn(s1_eq):>12}   {fn(s1i_eq):>12}   {fn(s3_eq):>12}   {fn(ew_eq):>12}")

    # Avg signals per day
    s1_avg = s1_signals.sum(axis=1).mean()
    s1i_avg = s1i_signals.sum(axis=1).mean()
    s3_avg = s3_signals.sum(axis=1).mean()
    print(f"  {'Avg signals/day':<22} {s1_avg:>9.1f}/48   {s1i_avg:>9.1f}/48   {s3_avg:>9.1f}/48   {'48/48':>12}")
    s3_days_active = (s3_signals.sum(axis=1) > 0).sum()
    print(f"  Strategy 3 days with at least 1 active signal: {s3_days_active} of {len(s3_signals)}")

    print(f"\nAlpha vs EW-Nifty CAGR:")
    s1_a = (summarize(s1_eq)["cagr"] - summarize(ew_eq)["cagr"]) * 100
    s1i_a = (summarize(s1i_eq)["cagr"] - summarize(ew_eq)["cagr"]) * 100
    s3_a = (summarize(s3_eq)["cagr"] - summarize(ew_eq)["cagr"]) * 100
    print(f"  Strategy 1:        {s1_a:+.2f} pp/year")
    print(f"  S1 inverted:       {s1i_a:+.2f} pp/year")
    print(f"  Strategy 3:        {s3_a:+.2f} pp/year")

    # Per-year breakdown
    print(f"\n{'=' * 80}")
    print("PER-YEAR RETURNS")
    print(f"{'=' * 80}")
    s1_y = yearly_returns(s1_eq)
    s1i_y = yearly_returns(s1i_eq)
    s3_y = yearly_returns(s3_eq)
    ew_y = yearly_returns(ew_eq)
    df = pd.DataFrame({
        "Strategy 1": s1_y,
        "S1 inverted": s1i_y,
        "Strategy 3": s3_y,
        "EW-Nifty": ew_y,
    })
    df["S1 alpha"] = df["Strategy 1"] - df["EW-Nifty"]
    df["S3 alpha"] = df["Strategy 3"] - df["EW-Nifty"]
    pct = (df * 100).round(2)
    print(pct.to_string(float_format=lambda x: f"{x:+.2f}%"))

    # Save equity curves
    eq_path = Path(__file__).resolve().parent.parent / "data" / "v1_compare_equity.csv"
    pd.DataFrame({
        "S1": s1_eq, "S1_inverted": s1i_eq, "S3": s3_eq, "EW_Nifty": ew_eq.reindex(s1_eq.index)
    }).to_csv(eq_path)
    print(f"\nEquity curves saved to {eq_path}")


if __name__ == "__main__":
    main()
