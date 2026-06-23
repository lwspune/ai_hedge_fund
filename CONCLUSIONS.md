# AI Hedge Fund — Project Conclusions

**Status: CONCLUDED (2026-06-12). Accepted negative result.**

## Verdict

A faithful Python port of the Google Sheets signal logic **does not beat NIFTY
buy-and-hold** on a portfolio basis, with realistic costs. After a full formula
audit confirming the signals were reproduced exactly, every pillar and every
aggregation underperformed the benchmark. We stopped here deliberately — the
goal was to *validate before risking capital*, and the validation came back
negative. That is a successful outcome for a research platform: a bad idea killed
cheaply, with no money lost.

## What was tested (NIFTY 50, 2018-01-01 → 2026-05-10, EW daily-rebalance, 0.3%/leg)

Benchmark — **EW-Nifty buy-and-hold: +17.64% CAGR, 0.96 Sharpe, −37.75% MaxDD.**

| Strategy (faithful to the sheet) | CAGR | Sharpe | Alpha |
|---|---:|---:|---:|
| Drawdown pillar (DD ≤ −10%) | +8.48% | 0.53 | −9.15pp |
| Aggregate ANY (≥1 pillar) | +6.00% | 0.42 | −11.63pp |
| EMA pillar (price ≤ MA, mean-reversion) | −2.13% | −0.03 | −19.77pp |
| Aggregate MAJORITY (≥2) | −2.35% | −0.03 | −19.99pp |
| Aggregate ALL — *the sheet's real Overall/Buy* | −34.24% | −1.51 | −51.87pp |
| Zone pillar (price = N-day low) | −35.77% | −1.60 | −53.41pp |

Buy_Signal family (7 variants) was tested earlier — all underperformed too.

## Why the signals don't carry edge (the honest reasons)

1. **No discrimination.** In the DCA single-stock cross-section, the spread between
   strategy variants *within a stock* was <1pp. Outcomes were driven by *which
   stock* was held, not which signal fired. A signal that can't out-predict its own
   variants isn't carrying information.
2. **The "alpha" was a mechanic, not a forecast.** The 33/48-stocks-with-alpha
   result came from DCA (rising cash flows) on volatile cyclicals — buying dips with
   growing contributions flatters returns vs lump-sum almost automatically. It only
   worked on cyclicals (steel, PSUs, Adani, Reliance) and *hurt* on compounders
   (TCS, HDFC, Asian Paints). That's stock selection, not signal.
3. **Base rate.** Simple price-based signals on liquid large-caps are largely
   arbitraged away after costs. The negative result is the expected outcome.

## The most valuable thing this project produced

**It corrected a false belief.** The famous "28% XIRR" in the sheet was not real
edge — it was (a) single-stock cherry-picking (changing one cell to whichever
winner) plus (b) a genuine **phantom-cashflow bug** in the sheet's XIRR: a blank
end-date row injected a −cashflow at serial date 0 (1899-12-30), 110 years before
the data, dominating the calc. Reproduced to 0.0001pp. Corrected XIRRs are far more
modest. **Fix for the live Google Sheet:** wrap the return formula —
`=IFERROR(IF(ISBLANK(E_curr), "", E_curr/E_prev - 1), "")`. (Not yet applied to the
user's sheet — optional follow-up.)

## What we keep (the platform is good — do NOT rebuild it)

Clean, tested (60 passing), honest, and reusable:
- `src/ai_hedge_fund/`: data (yfinance+parquet cache), backtest, metrics,
  moving_averages, signals, pillars.
- `extracted/`: the full formula-audit + forensic-XIRR toolkit and findings.
- The signals were verified exact against the sheets (`_findings_FormulaAudit.md`),
  so the negative result is trustworthy, not an implementation artifact.

## Untested (deliberately left open — would reopen the thesis, not guaranteed to)

- **Exits.** Everything holds-to-rebalance — the worst case for a mean-reversion
  entry. A TP/SL exit grid was never tested. ~30% prior it changes anything.
- **Filtered universe.** Running signals only on high-volatility cyclicals (where
  the cross-section showed real spread) was never isolated.

## If this is ever restarted

Point the *existing* platform at a hypothesis with a real economic prior
(cross-sectional ranking, factor tilts, fundamentals, or the cyclical-tilt
universe selection) rather than another price-pattern signal. Rebuilding the
engine would only re-introduce solved bugs.
