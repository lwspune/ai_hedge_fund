"""v1: run Strategy 1 across NIFTY 50 with daily-rebalance equal-weight portfolio.

Compares to NIFTY 50 buy-and-hold benchmark over the same window.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ai_hedge_fund.data import fetch_universe_closes, fetch_ohlc
from ai_hedge_fund.signals import strategy_1
from ai_hedge_fund.backtest import run_backtest
from ai_hedge_fund.metrics import summarize


def load_universe() -> list[str]:
    csv_path = Path(__file__).resolve().parent.parent / "data" / "universe_nifty50.csv"
    df = pd.read_csv(csv_path)
    return df["ticker"].tolist()


def main():
    START = "2018-01-01"
    END = "2026-05-10"
    INITIAL = 100_000.0
    COST_PER_LEG = 0.003  # 0.3% per leg ≈ Indian round-trip 0.6%

    print(f"\n{'=' * 80}")
    print("v1 BACKTEST — Strategy 1 on NIFTY 50, daily-rebalance equal-weight")
    print(f"{'=' * 80}")
    print(f"Window: {START} -> {END}")
    print(f"Initial capital: Rs.{INITIAL:,.0f}")
    print(f"Cost per leg: {COST_PER_LEG * 100:.2f}%")
    print()

    tickers = load_universe()
    print(f"Universe: {len(tickers)} tickers (Nifty 50)")
    print(f"Fetching closes via yfinance...")
    closes = fetch_universe_closes(tickers, START, END)
    if closes.empty:
        print("No data fetched. Aborting.")
        return
    print(f"  Got {closes.shape[0]} days x {closes.shape[1]} tickers\n")

    print("Computing Strategy 1 signals per ticker...")
    signals = pd.DataFrame(index=closes.index, columns=closes.columns, dtype=bool)
    for ticker in closes.columns:
        signals[ticker] = strategy_1(closes[ticker])
    n_active_avg = signals.sum(axis=1).mean()
    print(f"  Avg active signals per day: {n_active_avg:.1f}")
    print(f"  Days with at least one active signal: {(signals.sum(axis=1) > 0).sum()} of {len(signals)}\n")

    print("Running portfolio backtest...")
    result = run_backtest(closes, signals, initial_capital=INITIAL, cost_per_trade=COST_PER_LEG)
    eq = result["equity"]
    metrics = summarize(eq)

    print("\n--- Strategy 1 Portfolio Results ---")
    print(f"  Final equity:      Rs.{eq.iloc[-1]:,.0f}")
    print(f"  Total return:      {metrics['total_return'] * 100:+.2f}%")
    print(f"  CAGR:              {metrics['cagr'] * 100:+.2f}%")
    print(f"  Sharpe (ann.):     {metrics['sharpe']:.2f}")
    print(f"  Sortino (ann.):    {metrics['sortino']:.2f}")
    print(f"  Max drawdown:      {metrics['max_drawdown'] * 100:+.2f}%")

    # NIFTY 50 benchmark
    print("\nFetching NIFTY 50 benchmark (^NSEI)...")
    nifty = fetch_ohlc("^NSEI", START, END)
    if not nifty.empty:
        nifty_eq = (nifty["Close"] / nifty["Close"].iloc[0] * INITIAL).rename("equity")
        nifty_metrics = summarize(nifty_eq)
        print("\n--- NIFTY 50 Buy-and-Hold ---")
        print(f"  Final equity:      Rs.{nifty_eq.iloc[-1]:,.0f}")
        print(f"  Total return:      {nifty_metrics['total_return'] * 100:+.2f}%")
        print(f"  CAGR:              {nifty_metrics['cagr'] * 100:+.2f}%")
        print(f"  Sharpe (ann.):     {nifty_metrics['sharpe']:.2f}")
        print(f"  Max drawdown:      {nifty_metrics['max_drawdown'] * 100:+.2f}%")
        print(f"\n--- Strategy alpha (CAGR vs NIFTY) ---")
        alpha = (metrics["cagr"] - nifty_metrics["cagr"]) * 100
        print(f"  Strategy CAGR - NIFTY CAGR = {alpha:+.2f} pp")
    else:
        print("  Could not fetch NIFTY 50 benchmark")

    # Equal-weight Nifty buy-and-hold (more apples-to-apples than the index)
    ew_eq = (closes / closes.iloc[0]).mean(axis=1) * INITIAL
    ew_metrics = summarize(ew_eq.rename("equity"))
    print("\n--- Equal-weighted Nifty 50 buy-and-hold (apples-to-apples benchmark) ---")
    print(f"  Final equity:      Rs.{ew_eq.iloc[-1]:,.0f}")
    print(f"  Total return:      {ew_metrics['total_return'] * 100:+.2f}%")
    print(f"  CAGR:              {ew_metrics['cagr'] * 100:+.2f}%")
    print(f"  Max drawdown:      {ew_metrics['max_drawdown'] * 100:+.2f}%")
    ew_alpha = (metrics["cagr"] - ew_metrics["cagr"]) * 100
    print(f"\n  Strategy CAGR - EW-Nifty CAGR = {ew_alpha:+.2f} pp")

    # Save equity curve for inspection
    eq_path = Path(__file__).resolve().parent.parent / "data" / "v1_equity.csv"
    pd.DataFrame({
        "strategy": eq,
        "ew_nifty": ew_eq.reindex(eq.index),
    }).to_csv(eq_path)
    print(f"\nEquity curve saved to {eq_path}")


if __name__ == "__main__":
    main()
