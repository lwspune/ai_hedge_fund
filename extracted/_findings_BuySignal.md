# Buy Signal Family — Findings

This is a **separate, parallel system** from the EMA/Drawdown/Zone trio. It does *not* feed the `Aggregate_Signal` sheet — its columns aren't in the Aggregate's schema.

## Buy_Signal v1 → v2 → v3 evolution
- **v1**: columns `Buy Zone | Buy Signal 1` (one signal)
- **v2**: columns `Buy Zone | Buy Signal 1 | Buy Signal 2` (two signals)
- **v3**: columns `Buy Zone | Buy Signal 1 | Buy Signal 2 | Buy Signal 3` (three signals)

Universe shifted from 100-stock buckets (v1) to 50-stock buckets (v2/v3) — i.e. v3 uses `India_Top50`, `India_Top51_100`, …, `Nasdaq_50`, `Nasdaq_51_100` etc. for finer granularity.

Many `#DIV/0!` errors in v3 — calculation breakages, especially in newer micro-cap entries lacking enough history.

## Underlying buy-signal logic (from Analyser column structure)
The Analysers compute, per stock per day:

`Date | Close | Price_300DMA | 300DMA_Gain | Price_200DMA | 200DMA_Gain | Price_100DMA | 100DMA_Gain | Price_50DMA | Price_20DMA | Price Gain | Gain_200DMA | Gain_200DMA_50DMA | Gain_100DMA | Gain_100DMA_50DMA | Price_Signal_50DMA | Price_Signal | STD_Signal | Price_GT_50DMA | 50DMA_GT_100DMA | 100DMA_GT_200DMA | Momentum_100DMA_GT_200DMA`

Three derived booleans clearly visible:
- `Price_GT_50DMA` (price above 50-DMA?)
- `50DMA_GT_100DMA`
- `100DMA_GT_200DMA`
- `Momentum_100DMA_GT_200DMA`

Plus computed metrics:
- `Gain_NDMA` = % difference of price from N-day MA
- `Gain_NDMA_MDMA` = comparison of two MA-relative gains (e.g., is price closer to the 50DMA or the 100DMA?)
- `Price_Signal`, `STD_Signal` — composite scoring (definition not visible)

This is a **classic momentum/trend-stack with mean-reversion overlay** — quite different from the "buy weakness" stance of EMA/Drawdown/Zone.

## Buy_Signal_Analyser_15Yr — THE STRONGEST BACKTEST IN THE WHOLE FOLDER

15-year backtest. Per-stock layout. Rules tested:

| Rule | Trades | XIRR | vs NIFTY (12.69%) |
|---|---:|---:|---:|
| 1. `Gain_100DMA_50DMA < 0` | 912 | **28.20%** | +15.51pp |
| 2a. (1) + `Price Signal < 0` | 787 | 28.27% | +15.58pp |
| 2b. (1) + `Price Signal < -0.001` | 360 | 28.24% | +15.55pp |
| 3. (1) + `price < 50DMA` + `50DMA < 300DMA` | 376 | 27.88% | +15.19pp |
| 4a. (1) + `price < 300DMA_Gain` + `price touches 50DMA` | 26 | 27.67% | +14.98pp |
| 4b. (4a) + `Gain_200DMA_50DMA < 0` | 26 | 27.67% | +14.98pp |

**Headline:** the simplest rule alone (Rule 1 — short-term MA gain falling below long-term MA gain, i.e. "recent weakness in a stock that wasn't weak before") generated **28.20% annualized over 15 years across 912 trades**, beating NIFTY by 15.5 percentage points / year. **More-stringent rules don't help.** This is a robust, low-overfit signal.

## Buy_Signal_Analyser (base) — weaker pattern

| Rule | Trades | XIRR | vs NIFTY (12.68%) |
|---|---:|---:|---:|
| 2a. `Gain_100DMA_50DMA < 0 and Price Signal < 0` | 354 | 4.00% | -8.68pp ← under |
| 2b. + `Price Signal < -0.001` | 162 | 3.49% | -9.19pp ← under |
| 3.  + `price < 50DMA, 50DMA < 300DMA` | 164 | 3.65% | -9.03pp ← under |
| 4a. + `price < 300DMA_Gain, price touches 50DMA` | 15 | 18.67% | +5.99pp |
| 4b. + `Gain_200DMA_50DMA < 0` | 14 | 19.31% | +6.63pp |

Here the simple rules **lose to NIFTY**. Only the very strict "price touches 50DMA" rules generate alpha — but with only 14-15 trades. Either:
- Different universe (single stock in this Analyser?), or
- Different period (no full 2008/2020 crashes), or
- Different definition of `Gain_100DMA_50DMA` between the two Analysers.

## Buy_Signal_Analyser_50DMA — also weak

| Rule | Trades | XIRR | vs NIFTY (8.81%) |
|---|---:|---:|---:|
| 2a. `Gain_50DMA_50DMA < 0 and Price Signal < 0` | 211 | 4.28% | -4.53pp |
| 2b. + `Price Signal < -0.001` | 48 | 3.24% | -5.57pp |
| 3.  + `price < 50DMA` | 184 | 4.17% | -4.64pp |
| 4a. + `price < 50DMA_Gain, price touches 50DMA` | 26 | **22.97%** | +14.16pp |

Similar pattern — only the very stringent "touches 50DMA" rule beats NIFTY, with 26 trades.

## Reading across the three Analysers

The 15Yr version is on a different universe / time period and tells a *different story* than the base + 50DMA versions. The 15Yr's strong signal might be:
- A single high-beta stock pulled the average up (need to check what the 15Yr backtests).
- A multi-decade window captures regime changes the others miss.
- A different metric definition.

**This needs follow-up before we trust the 28.20% number for portfolio construction.**

## Why isn't Buy Signal in the Aggregate?

The Aggregate sheet's columns are EMA + Drawdown + Zone only. Buy Signal is not wired in. Possible reasons:
- **Older system**: Buy Signal v1-v3 predate the EMA/Drawdown/Zone redesign.
- **Higher-touch**: Buy Signal requires more discretion (the .docx journal showed manual "Strong Buy / Buy / Watch / Sell" classifications).
- **Calculation fragility**: many `#DIV/0!` / `#REF!` errors in v3 may have made it impractical for the production aggregate.

## Open questions / port notes
1. Is the Buy Signal still being maintained, or was it abandoned in favor of EMA/Drawdown/Zone?
2. The 15Yr Analyser results are very strong — worth reproducing in the Python port and validating with proper out-of-sample testing.
3. Need clearer definition of `Price_Signal`, `STD_Signal`, `Gain_NDMA_MDMA` — these aren't standard indicators.
4. Why do the 3 Analysers tell different stories on the same rules? Universe vs period vs metric drift — needs reconciliation.
