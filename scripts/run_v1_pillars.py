"""Test the 3 production pillars (EMA, Drawdown, Zone) and the Aggregate ensemble."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ai_hedge_fund.data import fetch_universe_closes
from ai_hedge_fund.pillars import (
    ema_pillar, drawdown_pillar, zone_pillar,
    aggregate_signal, signal_count_pct,
)
from ai_hedge_fund.backtest import run_backtest
from ai_hedge_fund.metrics import summarize


def yearly_returns(equity: pd.Series) -> pd.Series:
    yearly = equity.resample("YE").last()
    yearly_start = equity.resample("YE").first()
    rets = (yearly / yearly_start - 1)
    rets.index = rets.index.year
    return rets


def main():
    START = "2018-01-01"
    END = "2026-05-10"
    INITIAL = 100_000.0
    COST_PER_LEG = 0.003

    print(f"\n{'=' * 110}")
    print("v1 PILLARS: EMA / Drawdown / Zone / Aggregate vs EW-Nifty")
    print(f"{'=' * 110}")
    print(f"Window: {START} -> {END}, equal-weight daily rebalance, cost {COST_PER_LEG*100:.2f}%/leg\n")

    csv_path = Path(__file__).resolve().parent.parent / "data" / "universe_nifty50.csv"
    tickers = pd.read_csv(csv_path)["ticker"].tolist()
    closes = fetch_universe_closes(tickers, START, END)
    print(f"Universe: {closes.shape[1]} tickers x {closes.shape[0]} days\n")

    # EW-Nifty benchmark
    ew_eq = ((closes / closes.iloc[0]).mean(axis=1) * INITIAL).rename("EW_Nifty")
    ew_metrics = summarize(ew_eq)
    ew_cagr = ew_metrics["cagr"]

    strategies = [
        ("EW_Nifty (buy-hold)",         lambda p: pd.Series(True, index=p.index)),  # always-true placeholder
        ("EMA pillar (price<=MA, dip)",  ema_pillar),
        ("Drawdown pillar (DD<=-10%)",  drawdown_pillar),
        ("Zone pillar (any N-day low)", zone_pillar),
        ("Aggregate ANY",               lambda p: aggregate_signal(p, "any")),
        ("Aggregate MAJORITY (>=2)",    lambda p: aggregate_signal(p, "majority")),
        ("Aggregate ALL [prod Overall/Buy]", lambda p: aggregate_signal(p, "all")),
    ]

    results = {}
    for name, fn in strategies:
        if name == "EW_Nifty (buy-hold)":
            results[name] = (ew_eq, ew_metrics, 48.0, len(closes))
            continue
        sig = pd.DataFrame({t: fn(closes[t]) for t in closes.columns}, index=closes.index)
        eq = run_backtest(closes, sig, INITIAL, COST_PER_LEG)["equity"]
        m = summarize(eq)
        avg_active = sig.sum(axis=1).mean()
        days_active = (sig.sum(axis=1) > 0).sum()
        results[name] = (eq, m, avg_active, days_active)

    # Headline table
    print(f"{'Strategy':<32} {'CAGR':>9} {'Sharpe':>8} {'Sortino':>9} {'MaxDD':>9} {'Final (Rs.)':>14} {'Alpha':>8} {'Avg act':>9}")
    print("-" * 110)
    for name, (eq, m, avg_active, _) in results.items():
        alpha = (m["cagr"] - ew_cagr) * 100
        print(
            f"{name:<32} "
            f"{m['cagr']*100:>+8.2f}% "
            f"{m['sharpe']:>8.2f} "
            f"{m['sortino']:>9.2f} "
            f"{m['max_drawdown']*100:>+8.2f}% "
            f"{eq.iloc[-1]:>14,.0f} "
            f"{alpha:>+7.2f}pp "
            f"{avg_active:>6.1f}/48"
        )

    # Per-year breakdown (only for the most interesting strategies)
    print(f"\n{'=' * 110}")
    print("PER-YEAR RETURNS (%)")
    print(f"{'=' * 110}")
    yearly_df = pd.DataFrame({name: yearly_returns(eq) for name, (eq, _, _, _) in results.items()})
    yearly_pct = (yearly_df * 100).round(2)
    print(yearly_pct.to_string(float_format=lambda x: f"{x:+6.2f}"))

    # Save
    eq_path = Path(__file__).resolve().parent.parent / "data" / "v1_pillars_equity.csv"
    eq_df = pd.DataFrame({name: eq for name, (eq, _, _, _) in results.items()})
    eq_df.to_csv(eq_path)
    print(f"\nEquity curves saved to {eq_path}")


if __name__ == "__main__":
    main()
