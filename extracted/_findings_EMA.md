# EMA Family — Findings

## EMA_Signal (live snapshot)
- Per-stock current values for 50/100/200/300-day EMA across the universe
- Window: 14/8/2023 → 10/5/2026 (~2.7 years)
- Each stock × 4 timeframes → Yes/No "price above this EMA"
- "50DMA: NN" rows: per-ticker count of days above 50DMA in window
- A few `#DIV/0!` errors visible (some tickers fail the calculation)

## EMA_Signal_Analyser (medium-horizon backtest)
- Period: **8/17/2017 → 11/3/2025** (~8 years)
- Strategy tested: "buy when price crosses above N-day EMA"
- Results — XIRR (annualized) / trade count:

| Trigger | XIRR | Trades |
|---|---:|---:|
| 0EMA (baseline / always-buy) | 0.47% | 2,024 |
| 20EMA | 2.13% | 997 |
| 50EMA | 2.36% | 916 |
| 100EMA | 2.55% | 844 |
| **200EMA** | **2.73%** | 750 |
| 300EMA | 2.64% | 660 |

**Insight:** 200-day EMA edges out other timeframes. Best EMA strategy adds ~5.8× over the always-buy baseline (2.73% vs 0.47%) — the EMA filter clearly adds value, though absolute returns are modest.

## EMA_Crossover_Analyser (long-horizon backtest)
- Period: **1/24/2009 → 6/29/2025** (~16.5 years)
- Strategy: short-EMA crossing long-EMA (e.g. 5-day cross 50-day)
- Results:

| Trigger | XIRR | Trades |
|---|---:|---:|
| 0EMA (always-buy baseline) | **44.90%** | 4,043 |
| 5_50_Crossover | 39.61% | 62 |
| 5_100_Crossover | 40.57% | 45 |
| 5_200_Crossover | 41.32% | 26 |
| 5_300_Crossover | 41.26% | 27 |
| 300EMA | 42.77% | 710 |

**Insight:** Over 16 years, **buy-and-hold beats every crossover strategy** in this universe. Crossovers cut trade frequency 60-150× but don't improve per-trade outcomes. Crossover trade counts (26-62) are too small for confident statistical inference.

## Cross-comparison: why Signal vs Crossover analysers tell different stories
- **Signal_Analyser** = fixed-horizon return after each signal (the baseline "always-buy" gets 0.47% because each trade is short-held)
- **Crossover_Analyser** = hold from signal to end-of-backtest (long compounding period; baseline benefits from 16-yr index uptrend → 44.90%)
- The user's *production* aggregate uses the Signal_Analyser style — at any given day, count how many of 4 EMA timeframes show "price above EMA", and roll up to a Yes/No `EMA/Signal`.

## Open questions for the port
1. The aggregation rule (4 sub-signals → `EMA/Signal`) is not visible in the analyser sheets — need to confirm: majority? all? threshold?
2. Crossover strategies seem to *not* feed into the Aggregate (Aggregate has `EMA Signal/50D_EMA` etc. for "above EMA" tests, no crossover columns). The Crossover Analyser appears to be a research sandbox, not a production input.
3. What's the actual exit rule when a Signal stops firing? (User confirmed exits are discretionary today.)
