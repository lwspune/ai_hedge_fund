# Zone Family — Findings

## Zone_Signal (live snapshot, per-stock)
- Same structural template as EMA_Signal (a per-stock current-state sheet, **not** a backtest)
- Window: 14/8/2023 → 10/5/2026 (~2.7 years)
- Per-stock columns: `Ticker | Name | 50D_Low | 100D_Low | 200D_Low | 300D_Low`
- Each column = `"Yes"` if price is at / very near the rolling N-day low
- "50DMA: NN" rows show per-ticker count of qualifying days in window
- Some `#DIV/0!` errors (tickers without enough history)

## Zone_Signal_Analyser (backtest)
- Period: **2/15/2024 → 6/29/2025** (~16 months — short)
- Strategy: "buy when price equals N-day low"
- Results (XIRR / trades):

| Trigger | XIRR | Trades |
|---|---:|---:|
| 0EMA (buy every day, baseline) | 0.93% | 335 |
| 20D_Low | 39.10% | 33 |
| 50D_Low | 36.56% | 20 |
| **100D_Low** | **40.65%** | 17 |
| 200D_Low | 97.63% | 5 ← too few, ignore |
| 300D_Low | #NUM! | 0 |

**Insight:** "buy at 100-day low" gives 40.65% XIRR with 17 trades — about 44× the baseline. The signal works, but **17 trades over 16 months is statistically thin** — would want this re-run on a multi-year window before betting on it.

**Caveat:** the 200D_Low result of 97.63% is from only 5 trades and means nothing — looks like noise, not signal. The 0 trades at 300D_Low confirms 300-day lows are too rare in this window. The Aggregate's use of 300D_Low as a sub-signal is theoretically sensible but empirically untested.

## Stock_Correlation_Analyser
- **Not what the name suggests** — does *not* compute per-stock pairwise correlations.
- Instead tracks **NIFTY 50 index vs NIFTY Bees ETF** with rolling 5-day correlation and cumulative gains comparison.
- Period observed: 10/10/2025 → at least 12/15/2025 (recent)
- Columns: `Date | Close (NIFTY 50) | Niftuy_Bees_price | Niftuy_Bees_price_adj | corr_5D | Gain_nifty | Gain_nifty_bees | Gain_nifty_sum | Gain_nifty_bees_sum`
- corr_5D values consistently ~98-99% (as expected — Bees is an ETF tracking NIFTY)
- **Likely purpose:** validating NIFTY Bees as a tradeable proxy for the index, and tracking small tracking-error gains/losses.
- Not directly part of the signal pipeline — operational tool.

## Cross-comparison: Zone vs EMA vs Drawdown

Best-performing trigger from each family (backtested):

| Family | Best trigger | XIRR | Trades | vs baseline | Confidence |
|---|---|---:|---:|---:|---|
| EMA_Signal_Analyser | 200EMA | 2.73% | 750 | 5.8× | High (long sample) |
| EMA_Crossover_Analyser | 5_200_Cross | 41.32% | 26 | 0.92× | Low (small N) |
| Drawdown_a (vs ATH) | -25% | 31.27% | n/a | 1.04× | Medium |
| Drawdown_b (vs 200D) | -20% | 17.69% | n/a | 1.01× | Low (no edge) |
| Drawdown_c (vs NIFTY) | -15% | 41.38% | n/a | 1.07× | Medium |
| Zone | 100D_Low | 40.65% | 17 | 43.7× | Low (small N) |

**Strategic takeaways:**
- High-XIRR results in Zone (40%+) and Drawdown_Relative (41%) come from short-window backtests during recent bull conditions — needs longer-window validation.
- 200-day EMA in the long-sample Signal_Analyser is the most statistically robust signal (5.8× over baseline with 750 trades).
- The current ensemble trusts all three pillars equally; based on these numbers, **EMA should probably get higher weight than Drawdown or Zone in the production aggregate**.

## Open questions / port notes
1. The "Stock_Correlation_Analyser" is mis-named for what it actually does (NIFTY/Bees tracking). Real cross-stock correlation is missing — worth building in the Python port for portfolio-level diversification logic.
2. Zone backtest window is too short — re-run on 8+ years like the EMA Signal Analyser.
3. The 0EMA baseline interpretation needs verification: probably "buy every day" (which is the right interpretation given trade counts).
