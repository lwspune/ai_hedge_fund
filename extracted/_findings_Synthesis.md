# Cross-Family Synthesis — What you've actually built, and what to port

## The system in one sentence
You've built a **multi-pillar trading-signal aggregator** over a 9-bucket universe (India 500 + Nasdaq 100 + S&P 100 + Indices + Crypto), where each pillar tests a distinct hypothesis (trend strength, drawdown depth, proximity to lows) at four timeframes/thresholds, rolled into per-stock binary buy verdicts and a portfolio-level percentage score.

## The 4 strategy families, ranked by backtest evidence

| Family | Best signal | Backtest length | XIRR | Confidence | Status |
|---|---|---:|---:|---|---|
| **Buy Signal (15Yr)** | `Gain_100DMA_50DMA < 0` | 15 yrs | **28.20%** vs NIFTY 12.69% | High | Parallel system, NOT in Aggregate |
| **Drawdown vs NIFTY** | `Rel_DD <= -15%` | 14 yrs | 41.38% hit-rate | Medium | In Aggregate (but uses absolute DD, not relative — opportunity!) |
| **EMA Signal** | 200EMA | 8 yrs | 2.73% (5.8× baseline) | High | In Aggregate |
| **Drawdown vs ATH** | `DD <= -25%` | varies | 31.27% hit-rate | Medium | In Aggregate (uses 10/15/20/30) |
| **Zone (100D_Low)** | 100D_Low | 1.4 yrs | 40.65% (44× baseline) | Low (small N) | In Aggregate |
| **Drawdown vs 200D** | -20% | 16 yrs | 17.69% (no edge) | Low | Not in Aggregate (rightly) |
| **EMA Crossover** | 5_200_Cross | 16.5 yrs | 41.32% | Low (26 trades) | Research sandbox only |

## Where the production Aggregate stands

The Aggregate (`Stocks_Aggregate_Signal`) takes the 3 in-production pillars (EMA, Drawdown vs ATH, Zone) and combines them into:
- **Per-pillar binary verdicts**: `EMA/Signal`, `Drawdown/Signal`, `Zone/Signal` (1 = buy)
- **Aggregate score**: `Signal/Count` % — proportion of the 12 sub-signals (3 pillars × 4 each) that fire
- **Final flag**: `Overall/Buy`

**Aggregation rule for per-pillar binary** is not visible in any sheet; based on the cumulative-Yes pattern in Drawdown_Signal, the most likely rule is "any sub-signal fires → pillar fires", but it could also be "majority fires" (3 of 4). **Worth confirming with you before porting.**

## 5 strategic recommendations for the Python port

### 1. Promote Drawdown_Relative over Drawdown_ATH
Your Drawdown_Analyser_Relative (vs NIFTY) hits 41.38% at -15% — beats Drawdown_ATH (31.27% at -25%) and is closer to "real alpha" (you're isolating idiosyncratic weakness from market-wide moves). The current Aggregate uses absolute drawdown only; **swap or add the relative version**.

### 2. Reintegrate Buy Signal v3 into the ensemble
Buy Signal's 15-year backtest produces the strongest signal in the whole folder (28.20% XIRR, NIFTY +15pp, 912 trades). It's currently parallel to the Aggregate. **Port Buy Signal as a 4th pillar** with its own binary, expanding the ensemble from 12 sub-signals (3×4) to ~16 (3×4 + 4 momentum signals).

### 3. Re-weight, don't equal-weight
The Aggregate currently treats all 12 sub-signals equally. Based on backtest confidence:
- EMA 200D, Drawdown_Relative, Buy Signal Rule 1 → high confidence, higher weight
- Zone 200D/300D, EMA crossovers, Drawdown_200D → low confidence (small N or no edge), lower weight or drop

### 4. Design and backtest exit rules — currently the biggest gap
You confirmed exits are discretionary today. For the Python port, design and backtest at least 3 exit candidates:
- **Time-based**: hold N days regardless (simplest, lets you isolate signal alpha)
- **Reverse-signal**: exit when `EMA/Signal` flips back to 0 (your "below 200 DMA" rule from the .docx)
- **Trailing-stop**: exit when price < entry × (1 - X%), e.g. -10% trailing from peak post-entry

The .docx journal hinted at "Sell once below 200 DMA" — formalize this and compare.

### 5. Universe normalization across families
Buy Signal v3 uses 50-stock buckets (`India_Top50`, `India_Top51_100`, etc.); the rest use 100-stock buckets. **Pick one** for the port — 50-stock is more granular but the buckets are arbitrary anyway, since they're just for organization. Recommend a flat universe table keyed by ticker, with metadata columns (`region`, `cap_bucket`, `sector`).

## Concrete next steps (tomorrow's coding session)
1. Create `data/universe.csv` flattening all 9 buckets into a single ticker list with metadata
2. Build `signals/ema_signal.py` reproducing the 50/100/200/300 EMA Yes/No logic
3. Re-backtest EMA on Indian 8-year window using yfinance — compare to 2.73% baseline
4. Build `signals/drawdown_relative.py` (the under-utilized winner)
5. Skip Buy Signal until we can recover what `Price_Signal` / `STD_Signal` mean (those are in the formula bar, not visible to Drive MCP — you may need to paste those formulas to me directly)

## Things you should know that *aren't* in the sheets
- **No commission/slippage modeling** in any backtest. India costs (STT 0.1%, brokerage 0.03%, GST 18%) compound — for a 28% XIRR strategy with 912 trades, that's a couple hundred bps drag annually. Real returns will be lower.
- **No position sizing**. All "trades" are binary "did this signal fire". The portfolio-construction layer doesn't exist yet — that's a big design gap for the Python port.
- **No market-regime conditioning**. Drawdown signals get worse in sustained bear markets; trend signals get worse in chop. The aggregate doesn't know what regime it's in. Adding a regime filter (e.g., NIFTY 200DMA > 0?) could materially improve real-world results.
