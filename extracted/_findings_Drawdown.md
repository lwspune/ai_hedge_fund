# Drawdown Family — Findings

## Drawdown_Signal (live snapshot)
- Columns per stock: `Ticker | Name | Drawdown | Drawdown_10% | Drawdown_15% | Drawdown_20% | Drawdown_30%`
- "Drawdown" = current drawdown from peak as a percentage (e.g. `-23.42%`)
- "Drawdown_X%" cells = `"Yes"` when `current_drawdown <= -X%`, blank otherwise
- **Cumulative "Yes" pattern confirmed:** if a 30% Yes fires, 10/15/20 also fire. So the four columns aren't independent triggers — they're depth bands.
- Examples observed:
  - AAPL: 0.00% → no Yes
  - TSLA: -12.56% → 10% Yes only
  - MSFT: -23.42% → 10%/15%/20% Yes
  - NFLX: -34.67%, ADBE: -60.14%, PYPL: -50.58% → all four Yes
- **Threshold note:** Drawdown_Signal uses 10/15/20/**30**%, matching the Aggregate. (Earlier I saw a `Drawdown_25%` row — that was in a sub-section of the Signal sheet, not the live universe table.)

## Drawdown_Analyser_a → "Stocks_Drawdown_Analyser" (BASE — vs all-time high)
- Reference price: `Price_ATH` (all-time high since record start)
- Daily series: `Date | Close | Price_ATH | Drawdown | Year | Price_50D_Low`
- Hit-rate / "buy when DD <= threshold" results:

| Threshold | Hit% / Amount |
|---|---:|
| LT 0%   | 29.95% |
| LT -3%  | 30.20% |
| LT -5%  | 30.11% |
| LT -10% | 29.86% |
| LT -15% | 27.14% |
| LT -20% | 27.20% |
| LT -25% | **31.27%** ← peak |

Insight: deeper drawdowns produce slightly better hit rates, peaking at the -25% bucket — the classic "buy panic" signal works, but the edge is modest (~3pp over the 0% baseline).

## Drawdown_Analyser_b → "Stocks_Drawdown_Analyser_200_Days" (vs rolling 200-day high)
- Reference price: `Price_200D_ATH` (highest close in last 200 trading days)
- Period: **4/4/2008 → 9/7/2024** (~16.5 years)
- Hit rates:

| Threshold | Hit% |
|---|---:|
| LT 0%   | 17.58% |
| LT -5%  | 17.42% |
| LT -10% | 17.36% |
| LT -15% | 17.52% |
| LT -20% | **17.69%** |
| LT -25% | 17.15% |

Insight: 200-day-high reference gives much **flatter and lower** hit rates than ATH (17% vs ~30%). Drawdowns from a 200D peak are more frequent (so more samples) but the threshold barely matters — the signal carries less information.

## Drawdown_Analyser_c → "Stocks_Drawdown_Analyser_Relative" (vs NIFTY_50 benchmark)
- Reference: NIFTY_50 index — measures **relative drawdown** = stock_DD − NIFTY_50_DD
- Period: **12/30/2010 → 9/7/2024** (~14 years)
- Columns: `Date | Close | Price_ATH | NSE:BAJFINANCE_Drawdown | Year | NIFTY_50 | NIFTY_50_ATH | NIFTY_50_DD | BAJFINANCE_ATH | BAJFINANCE_DD | BAJFINANCE_Rel_DD`
- Hit rates:

| Threshold (Rel_DD) | Hit% |
|---|---:|
| LT 0%   | 38.82% |
| LT -5%  | 39.23% |
| LT -10% | 39.36% |
| LT -15% | **41.38%** ← peak |
| LT -20% | 40.97% |
| LT -25% | 36.89% |

Insight: **Relative drawdown is the best of the three variants** (peak 41.38% vs 31.27% absolute and 17.69% vs-200D). "Buy when stock has fallen 15% more than the index" beats absolute drawdown signals. This is alpha-by-construction — you're isolating idiosyncratic weakness from market-wide moves.

## Cross-comparison — which drawdown reference works best?

| Reference | Best threshold | Hit rate |
|---|---:|---:|
| All-time high | -25% | 31.27% |
| 200-day high | -20% | 17.69% |
| **vs NIFTY_50** | **-15%** | **41.38%** |

**Strategic insight:** the production `Drawdown_Signal` (and Aggregate) currently uses absolute ATH. The Relative variant is materially stronger — worth promoting it (or adding it as a 5th sub-signal) in the Python port.

## Open questions / port notes
1. The "Amount/Shares_bought" column meaning is unclear — likely the average amount/share count traded when each threshold fires. Need to verify whether it's hit-rate, win-rate, or position-size proxy.
2. Aggregation rule for `Drawdown/Signal` (the binary that feeds Aggregate) — not visible. Probably "any of 4 sub-signals fires → Yes", but need to confirm.
3. The 4 thresholds (10/15/20/30%) skip 25% — yet 25% is where Analyser_a peaks. **Worth testing 25% inclusion.**
4. Relative drawdown needs a benchmark choice for non-Indian stocks (S&P 500 for US, BTC index for crypto, etc.).
