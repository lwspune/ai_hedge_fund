# CLAUDE.md — Personal Market-Intelligence Platform (India)

> **Note on the directory name.** This repo lives in a folder called `AI_Hedge_Fund`,
> but that project is dead and deleted. The old yfinance/Google-Sheets signal work was
> CONCLUDED (negative result) and cleared on 2026-06-23 (recoverable at git commit
> `30f1f1e`). This repo is now a **different project**. Ignore the folder name.

## What this is
A personal tool for **systematic opportunity detection in Indian equities** — surface
candidates, judge them, **trade manually via Kite**. No automated execution. Single
user (Vilas). India-first, NSE.

## The discipline (the whole point — read this first)
**Validate before you trust. Never trade a signal we haven't measured.** Every signal
in the platform carries a hard-won **verdict**, and the runner prints it as a banner so a
falsified signal is never read as edge. Four signals were validated this way; only one
survived. See `CONCLUSIONS.md` for the evidence.

| Signal | Type | Verdict | Role |
|---|---|---|---|
| `buyback_arb` | structural | **conditional edge** | **primary (actionable)** |
| `merger_arb` | spread | thin | watch |
| `mean_reversion` | drift | **null** | lens (informational only) |
| `smart_money_deals` | drift | **null** | lens (informational only) |
| `open_offer_arb` | spread | **null** | documented control |

**The through-line:** edge survives only where there's a *structural barrier* retail
uniquely sits inside (the buyback 15% small-shareholder reservation institutions are
barred from). Drift-prediction signals get arbitraged away; efficiently-priced spreads
(merger arb) get competed to ~risk-free. Do **not** restart drift-signal chasing.

## Architecture
- **Signal registry** — `scanner/catalog.py`: every signal + its `SignalMeta`
  (type/verdict/role) and a `run()`. The honesty layer.
- **Runner** — `scanner/run.py`: `python -m scanner.run --list` (all verdicts) or
  `python -m scanner.run <name>` (run one, behind its verdict banner).
- **Signal logic** — `signals.py` (RSI/200-DMA/quality), `deals.py` (bulk/block
  smart-money), `buyback.py` (chittorgarh scrape + tender-arb math + Oct-2024 tax),
  `universe.py` (NIFTY 50 + financials rule).
- **Validation harness** — `scanner/eventstudy.py` + `scripts/validate_*.py`: the
  event-study engine. Any new signal gets validated here *before* it's trusted.
- **Persistence (P2)** — `scanner/db.py` (raw PostgREST, no ORM) + `db/schema.sql`
  (5 tables: scan_runs, candidates, buybacks, tenders, outcomes). `scanner/track.py`
  is the feedback-loop CLI (record tenders + realized acceptance → calibrates the
  buyback selection). Inactive until you run `db/schema.sql` in Supabase and set
  `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` in `.env` (see `.env.example`).

## Data sources (free, proven; residential IP required)
- **Prices** — yfinance (`.NS`, split-adjusted) primary; **nselib** for historical /
  delisted symbols (filter `Series=='EQ'`!); jugaad-data fallback.
- **Fundamentals** — screener.in scrape (market cap, computed debt/equity).
- **Bulk/block deals** — NSE **static archive CSVs** (`nsearchives.../bulk.csv`,
  `block.csv`). NSE's JSON APIs (PIT/insider/historical) are JS-gated → empty/503; the
  static CSVs are the way in.
- **Buybacks** — chittorgarh detail pages by id (`/buyback/x/<id>/`); list page is
  JS-rendered (not scrapable), so enumerate ids. Symbol is in `nseCode` (double-escaped).

## Run
`python -m pytest` (61 tests) · `python -m scanner.run --list` ·
`python -m scanner.run buyback_arb [--save]` · `python -m scanner.track buybacks|tender|outcome`

## Stack
Python · pandas · yfinance · nselib · jugaad-data · requests/bs4 · pytest · Supabase
(raw PostgREST via requests, no ORM/SDK). **P2 persistence layer built** (apply
`db/schema.sql` + set creds to activate). **P3** (React verdict-aware dashboard) is next.

## Conventions / Don'ts
- **TDD**: pure logic (signal math, arb math, parsers) is tested before implementation.
- **No silent bad data**: every scrape/price path needs sanity guards (we hit warrant
  series mis-picks, delisted-ticker garbage, 246% "premiums"). Guard, don't surface.
- Don't trade a `null`/`thin` signal as if it were edge. Don't restart drift signals.
- Don't add Supabase/React until P2/P3. Keep the validated core clean.
