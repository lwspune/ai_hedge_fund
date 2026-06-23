# CLAUDE.md — AI Hedge Fund (CONCLUDED)

## Status
**CONCLUDED 2026-06-13. Accepted negative result. Do not restart strategy work without an explicit new ask.**
Read `CONCLUSIONS.md` first — it is the authoritative capstone (verdict, corrected
results table, why the signals lack edge, what's kept, what's left open).

One-line verdict: a formula-audited, *exact* Python port of Vilas's Google Sheets
signals (Buy Signal / EMA / Drawdown / Zone) does **not** beat NIFTY buy-and-hold on
a portfolio basis with realistic costs. The platform is sound; the strategy
hypothesis was falsified.

## Successor
Active work pivoted to a **new project in a different directory**: AI-assisted
**discretionary fundamental value investing**, India-first, single-company dossier
tool. See the `value-investing-project` memory. Do **not** build it inside this repo.

## What's here (don't rebuild — it works and is trusted)
- `src/ai_hedge_fund/`: `data.py` (yfinance + parquet cache), `moving_averages.py`
  (LWMA, weights 1..N), `signals.py` (Buy Signal family), `pillars.py`
  (EMA/Drawdown/Zone + Aggregate), `backtest.py`, `metrics.py`.
- `tests/`: 60 passing — `python -m pytest`.
- `scripts/run_v1*.py`: backtest drivers.
- `extracted/`: formula-audit + forensic-XIRR toolkit and findings
  (`_findings_*.md`, `audit_signal_formulas.py`); source xlsx in `extracted/sheets/`.
- `data/`: `universe_nifty50.csv` (survivorship-biased — today's constituents),
  `ohlcv_cache/*.parquet`, `v1_*_equity.csv`.

## Facts a future session must not relearn the hard way
- Pillars audited 2026-06-12 against the source xlsx: **EMA = price ≤ LWMA**
  (mean-reversion, not trend), **Drawdown = expanding-ATH cummax**, **Zone = price ==
  rolling-N-low** (strict equality, faithful), **Aggregate Overall/Buy = ALL 3
  pillars** (`aggregate_signal` default `mode="all"`).
- The sheet's famous "28% XIRR" was cherry-picking + a phantom-cashflow XIRR bug
  (blank end-date row → −cashflow at 1899-12-30). Live-sheet fix (not yet applied):
  `=IFERROR(IF(ISBLANK(E_curr),"",E_curr/E_prev-1),"")`.

## Run
`python -m pytest` · `python scripts/run_v1_pillars.py` (uses cached OHLC; offline).

## Stack
Python · pandas · yfinance · openpyxl · pytest. Anthropic-only for any LLM layer
(none currently). No framework, no build step.
