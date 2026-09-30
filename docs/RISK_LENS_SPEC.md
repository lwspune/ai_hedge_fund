# Risk lens v1 — security-level risk analytics — implementation spec

**Status:** built 2026-09-30 (see §11) · **Written:** 2026-09-30 · **Owner:** Vilas · **Builder:** coding agent
**Read first:** `CLAUDE.md` (conventions, the discipline, decisions log). This spec assumes it.

## 0. Why this exists

The platform is a research and data spine (company master, six years of prices, events, fundamentals,
filings, ratings, shareholding). It has no risk layer: nothing tells you, next to a candidate, how volatile
the name is, how it moves with the market, how far it has already fallen, or how many days it would take to
get out. The owner's direction (2026-09-30) is to grow toward a personal Aladdin **without a position book
for now**, so the pillars that stay reachable are the ones computed on securities and the market, not on
holdings. This is the first of them.

**What it is:** a daily, per-symbol table of risk measurements over the whole listed universe, computed from
data the store already holds, surfaced on the company page and next to every Act / Watch row on the Desk.

**What it is not:** a signal. Risk is measurement, not alpha. It carries no verdict, does not enter the
catalog, and never ranks candidates by itself. A composite "risk score" is explicitly out (the flat-45%
acceptance prior taught us not to invent gradients); raw measurements plus honest percentile ranks only.

Hard constraints carried from `CLAUDE.md`:

1. **Runs on GitHub Actions, never the laptop.** One new daily step; no local parquet as source of truth.
2. **Database budget.** The DB sits at ~274 MB with a 300 MB warn / 400 MB fail line. The new table is one
   row per symbol, overwritten daily: ~2,500 rows, well under 1 MB. **No history table in v1.**
3. **No silent bad data.** Unadjusted closes across a split or bonus produce a fake −50% day. Every series
   is corporate-action-adjusted through the guarded `pricestore.adjust_for_actions`; a symbol whose action
   cannot be verified gets **null metrics and a flag**, never a wrong number.
4. **TDD.** Every pure function in §3 has a failing test before its implementation (§7).

## 1. Scope

**In (v1):**
- `scanner/risk.py` — pure functions: returns, volatility, beta / correlation / idiosyncratic vol, drawdown,
  worst day / week, trailing returns, liquidity (ADV, days-to-exit), flags, percentile ranks, DB row shaping.
- `db/schema.sql` — table `risk_metrics` (§4) + freshness rule + volume floor (§5).
- `scripts/refresh_risk.py` — the daily loader (§5), one pass over the universe via `pricestore.bar_panel`.
- Dashboard — company page **Risk** tab + one header stat; risk chips on Desk Act / Avoid rows (§6).
- Docs — `CLAUDE.md` architecture bullet + decisions-log line, `learnings.json` entry, `SUGGESTIONS.md`
  ledger entries for v2 (§8).

**Out (v2, logged in SUGGESTIONS.md, do not build):**
- Basket / candidate-list risk (concentration by industry, cap bucket, shared event week).
- Stress test / scenario repricing over the worst historical weeks since 2020.
- Market regime view (index drawdown, breadth, vol regime).
- Industry-relative beta and correlation (needs sector indices; `index_prices` holds only ^NSEI, ^CRSLDX).
- F&O bhavcopy / implied volatility (backlog #24).
- Risk history / time series of the metrics (needs a bucket design; not a table).

## 2. Definitions (the contract the tests pin)

All prices are **adjusted closes**: `pricestore.get_bars` / `bar_panel` closes (unadjusted, cloud store),
passed through `pricestore.clean_series` then `pricestore.adjust_for_actions` with that symbol's
`corporate_events` rows of type `split` / `bonus` / `consolidation` inside the window. Benchmark is
**NIFTY 500** (`^CRSLDX` from `index_prices` via `get_closes("^CRSLDX", source="db")`), the same benchmark
every validation uses.

Window: `WINDOW_DAYS = 400` calendar days back from `as_of` (≈ 270 sessions), which is also the
`daily_prices` retention window. Session counts below are trading sessions the stock actually printed.

| Metric | Column | Definition | Requires |
|---|---|---|---|
| Daily log return | — | `r_t = ln(P_t / P_{t-1})` on the stock's own consecutive prints | — |
| 1-year volatility | `vol_1y` | `std(r, ddof=1) × √252` over the last 250 sessions (or all if fewer) | ≥ 120 sessions |
| 3-month volatility | `vol_3m` | same over the last 60 sessions | ≥ 60 sessions |
| Beta | `beta_1y` | `cov(r_s, r_m) / var(r_m)` on dates both stock and benchmark printed, last 250 sessions | ≥ 120 aligned sessions and not `sparse` |
| Correlation | `corr_1y` | Pearson of the same aligned returns | as beta |
| Idiosyncratic vol | `idio_vol_1y` | `std(r_s − beta·r_m, ddof=1) × √252` | as beta |
| Max drawdown | `max_dd_1y` | `min_t (P_t / max_{u≤t} P_u − 1)` over the window | ≥ 60 sessions |
| Current drawdown | `dd_now` | `P_last / max(P over window) − 1` | ≥ 60 sessions |
| Worst day | `worst_day_1y` | `min_t (P_t / P_{t-1} − 1)` | ≥ 60 sessions |
| Worst week | `worst_week_1y` | `min_t (P_t / P_{t-5} − 1)` (5 sessions) | ≥ 60 sessions |
| Trailing returns | `ret_1m`, `ret_3m`, `ret_1y` | `P_last / P_{last−k} − 1`, k = 21 / 63 / 250 sessions | that many sessions, else null |
| ADV | `adv_20_cr` | median `turnover_lakh` over the last 20 sessions ÷ 100 (₹ crore/day). Turnover is in rupees so splits do not touch it — **no adjustment**. | ≥ 10 sessions |
| Days to exit | `days_to_exit_5l` | `ceil(POSITION_INR / (PARTICIPATION × adv_20_cr × 1e7))`, floor 1; `POSITION_INR = 5e5`, `PARTICIPATION = 0.10` | adv present |
| Delivery | `delivery_pct_20` | median `delivery_pct` over the last 20 sessions | ≥ 10 sessions |
| Vol rank | `vol_rank` | percentile (0-100) of `vol_1y` among symbols with a value in the same run; 100 = most volatile | — |
| Liquidity rank | `liq_rank` | percentile (0-100) of `adv_20_cr`; 100 = most liquid | — |

Both constants are module-level in `scanner/risk.py` and pinned by a test, like `refresh_prices.KEEP_DAYS`.
`days_to_exit(position_inr, adv_cr, participation)` is a public pure function so the dashboard number can
be re-derived for another position size later.

**Flags** (`flags text[]`, may be empty; order irrelevant):

| Flag | Rule | Effect on metrics |
|---|---|---|
| `short_history` | fewer than 120 sessions in the window | 1y metrics null; 3m ones computed if ≥ 60 |
| `sparse` | the stock printed on < 80% of the benchmark's sessions in the window (suspended, illiquid) | beta / corr / idio null |
| `action_unverified` | `adjust_for_actions` returned `None` (an action inside the window whose jump the prices don't show) | **all price metrics null**; liquidity metrics still computed |
| `illiquid` | `adv_20_cr < 1.0` (the consolidation scan's ₹1 crore/day line) | none |
| `sme` | series in SM / ST / SZ | none |
| `asm`, `gsm` | symbol is on the latest `surveillance_daily` snapshot's ASM (long or short term) / GSM list — read the table's columns in `db/schema.sql` before wiring this | none |

## 3. Module `scanner/risk.py` — public API

```python
WINDOW_DAYS = 400
POSITION_INR = 5e5
PARTICIPATION = 0.10
MIN_SESSIONS_1Y, MIN_SESSIONS_3M, MIN_SESSIONS_LIQ = 120, 60, 10
SPARSE_COVERAGE = 0.80
ILLIQUID_ADV_CR = 1.0

def log_returns(closes: pd.Series) -> pd.Series
def ann_vol(r: pd.Series, n: int | None = None) -> float | None            # last n returns, None if < 2
def beta_stats(r_stock: pd.Series, r_mkt: pd.Series, n: int = 250) -> dict  # {beta, corr, idio_vol, n_aligned}
def drawdowns(closes: pd.Series) -> dict                                     # {max_dd, dd_now}
def worst_moves(closes: pd.Series) -> dict                                   # {worst_day, worst_week}
def trailing_returns(closes: pd.Series) -> dict                              # {ret_1m, ret_3m, ret_1y} (None when short)
def liquidity(bars: pd.DataFrame) -> dict                                    # {adv_20_cr, delivery_pct_20, days_to_exit_5l}
def days_to_exit(position_inr: float, adv_cr: float | None, participation: float = PARTICIPATION) -> int | None
def coverage(stock_dates, mkt_dates) -> float                                # share of benchmark sessions the stock printed
def symbol_metrics(sym: str, bars: pd.DataFrame, mkt_closes: pd.Series, actions: list[dict],
                   series: str | None, surveillance: set[str]) -> dict       # one flat dict incl. flags; the orchestrator
def add_ranks(rows: list[dict]) -> list[dict]                                # fills vol_rank / liq_rank across the run
def risk_row(m: dict, as_of: date) -> dict                                   # DB boundary: NaN/inf/NaT -> None, floats rounded, flags list
def format_table(rows: list[dict]) -> str                                    # CLI print
```

Rules for the orchestrator `symbol_metrics`:
1. `closes = clean_series(bars["close"])`; if fewer than `MIN_SESSIONS_LIQ` prints → liquidity only + `short_history`.
2. `adj = adjust_for_actions(closes, actions)`; `None` → flag `action_unverified`, all price metrics `None`.
3. `coverage` against the benchmark's dates inside the stock's own first/last print → `sparse` if below 0.80.
4. Everything else per §2. The function never raises on a bad symbol: it returns a row with flags. It *does*
   propagate a `BadPriceData` from `clean_series` upward (that is a corrupt store, not a bad stock).

`risk_row` is the DB boundary and is tested against the 2026-09-30 lesson (a `NaT` reached Postgres as
`22007` and blinded the buyback save for six days): every value is a plain `float | int | str | None`,
`math.isfinite` is enforced, dates are ISO strings.

## 4. Schema — `db/schema.sql` (append; apply via the Supabase MCP, keep the file in sync)

```sql
-- Risk lens v1 (docs/RISK_LENS_SPEC.md): one row per listed symbol, overwritten daily by
-- scripts/refresh_risk.py. Measurements, not a signal — no verdict, no composite score.
create table if not exists risk_metrics (
  symbol           text primary key references companies(symbol) on update cascade,
  as_of            date not null,                      -- last session in the window
  sessions         integer not null check (sessions >= 0),
  vol_1y           real check (vol_1y is null or vol_1y >= 0),
  vol_3m           real check (vol_3m is null or vol_3m >= 0),
  beta_1y          real,
  corr_1y          real check (corr_1y is null or corr_1y between -1 and 1),
  idio_vol_1y      real check (idio_vol_1y is null or idio_vol_1y >= 0),
  max_dd_1y        real check (max_dd_1y is null or (max_dd_1y <= 0 and max_dd_1y >= -1)),
  dd_now           real check (dd_now is null or (dd_now <= 0 and dd_now >= -1)),
  worst_day_1y     real check (worst_day_1y is null or worst_day_1y >= -1),
  worst_week_1y    real check (worst_week_1y is null or worst_week_1y >= -1),
  ret_1m           real, ret_3m real, ret_1y real,
  adv_20_cr        real check (adv_20_cr is null or adv_20_cr >= 0),
  days_to_exit_5l  integer check (days_to_exit_5l is null or days_to_exit_5l >= 1),
  delivery_pct_20  real check (delivery_pct_20 is null or delivery_pct_20 between 0 and 100),
  vol_rank         real check (vol_rank is null or vol_rank between 0 and 100),
  liq_rank         real check (liq_rank is null or liq_rank between 0 and 100),
  flags            text[] not null default '{}',
  updated_at       timestamptz not null default now()
);
alter table risk_metrics enable row level security;
create policy "anon read risk_metrics" on risk_metrics for select to anon using (true);
```

Ratios are stored as fractions (0.32 = 32%), the convention of every other table. `real` is enough for a
display lens and keeps the row small. No index beyond the primary key.

## 5. Loader — `scripts/refresh_risk.py`

```
python scripts/refresh_risk.py                 # whole listed universe, upsert (needs SUPABASE_SERVICE_KEY)
python scripts/refresh_risk.py --symbols A,B   # subset, still upserts
python scripts/refresh_risk.py --print         # compute + print, no write (dev)
```

Steps, one process:
1. `as_of = today`; `start = as_of − WINDOW_DAYS`.
2. `panel = pricestore.bar_panel(start, as_of)` — one pass over ~14 bucket months (the consolidation scan
   already does this daily for 120 days; measure the 400-day run time, target < 5 min on a runner; if the
   month reads dominate, cache-free is still fine — do not add local parquet as a dependency).
3. `mkt = get_closes("^CRSLDX", start, as_of, source="db")`; fail the run if it is `None` or ends more
   than 3 trading days before `as_of` (a stale benchmark makes every beta wrong).
4. `companies` where `status = 'listed'` → universe and `series`; `corporate_events` with `event_type in
   (split,bonus,consolidation)` and `event_date >= start`, grouped by symbol; latest `surveillance_daily`
   snapshot → ASM / GSM symbol sets.
5. `rows = [symbol_metrics(...) for each universe symbol present in the panel]`; `add_ranks(rows)`;
   `risk_row(m, as_of)` each.
6. Guards that **fail the run** (non-zero exit → GitHub email): fewer than 1,500 rows; more than 20% of
   rows flagged `action_unverified`; benchmark stale (step 3).
7. `db.upsert_resilient("risk_metrics", rows, on_conflict="symbol")` in pages; print counts and the flag
   histogram.

**Scheduling:** insert `["refresh_risk.py"]` in `scripts/scheduled_refresh.py` `daily` right after
`["refresh_prices.py"]` (it reads today's close) and before the scans; extend `tests/test_scheduled_refresh.py`
to pin the order. **Freshness:** add `"risk_metrics": ("risk_metrics", "as_of", {}, 1)` to
`TRADING_QUERIES` in `scripts/check_freshness.py` and a volume floor of 1,500 rows (whole table). The existing
test that forces every dated table in `db/schema.sql` to carry a rule will fail until this is done — that is
the intended order.

First population: merge, then `gh workflow run refresh-daily.yml`. Do not populate from the laptop.

## 6. Dashboard

Read-only, anon key, hash-routed, no new dependencies. Formatting only via `src/lib/format.js`.

1. **Route.** Add `'risk'` to `COMPANY_TABS` in `src/useHashRoute.js` (after `events`, before `filings`);
   extend `useHashRoute.test.js`.
2. **Data.** `src/lib/risk.js`: `loadRisk(symbol)` (one row), `loadRiskFor(symbols)` (`symbol=in.(...)`,
   used by the Desk), `flagLabel(flag)` (short human text per §2 flag, a test covers every flag),
   `fmtDaysToExit(n)` ("1 day" / "12 days" / "—"). Unit-test the pure helpers.
3. **Company page `Risk` tab** (`src/components/company/RiskTab.jsx`, fetched only when the tab is open,
   like the other tabs):
   - A `StatGrid` in three groups — *Volatility* (1y vol, 3m vol, beta, correlation, idiosyncratic vol),
     *Drawdown* (max 1y, current, worst day, worst week), *Liquidity* (ADV ₹ cr, days to exit ₹5 lakh at 10%
     participation, delivery %). Ranks shown as a `sub` on vol and ADV ("82nd pct of market").
   - Flags rendered as `Badge`s with `flagLabel` text; `action_unverified` explains why the metrics are blank.
   - A one-line footer: "As of {as_of} · 400-day window · NIFTY 500 benchmark · not a signal".
   - Empty / error / skeleton states through the shared `ui/States` and `ui/Skeleton`.
4. **Header stat.** One `Stat` in `CompanyHeader`: label "1y vol", value `fmtPct(vol_1y)`, sub `β {beta}`.
   Omitted (not "—") when there is no row, like the credit-rating stat.
5. **Desk chips.** On each Act row (open buybacks, rights entitlements) and Avoid row (anchor unlocks), a
   small chip: `vol 34% · exit 3 d` with a `title` carrying the flags. One `loadRiskFor` call per list.
   A flagged `asm` / `gsm` / `illiquid` symbol gets a warning tone on the chip.
6. **Accessibility** (global rule): the tab is keyboard-reachable through the existing `Tabs`; chips carry
   `aria-label` text ("Risk: 1-year volatility 34%, 3 days to exit"); tones meet AA contrast via the
   existing tokens.

## 7. Tests (write first; each must fail for the right reason before its implementation)

`tests/test_risk.py`, synthetic data only, no network:

- `log_returns` on a doubling then halving series gives `+ln2, −ln2`.
- `ann_vol` of constant returns is 0; of two known returns matches `std(ddof=1) × √252`; fewer than 2 → None.
- `beta_stats`: `r_s = 1.5 · r_m` exactly → beta 1.5, corr 1.0, idio 0.0; benchmark dates the stock lacks are
  dropped (alignment), `n_aligned` reports the count; `n_aligned < 120` handled by the caller, not here.
- `drawdowns`: path 100 → 120 → 90 → 110 gives `max_dd = −0.25`, `dd_now = 110/120 − 1`.
- `worst_moves`: worst day and worst 5-session window on a hand-built path.
- `trailing_returns`: exact at 21 / 63 / 250 sessions; `None` when the series is shorter.
- `liquidity`: turnover_lakh 250 on every day → `adv_20_cr = 2.5`; `days_to_exit(5e5, 2.5) == 1`;
  `days_to_exit(5e5, 0.02) == 25`; `adv None` → None; median ignores a single spike day.
- `coverage`: stock printing 70 of 100 benchmark sessions → 0.70 → `sparse`.
- `symbol_metrics`: (a) a 1:2 split inside the window with prices that show the jump → beta/vol computed on
  the adjusted series and **no** fake −50% worst day; (b) the same action with prices that do not show it →
  `action_unverified`, all price metrics None, liquidity present; (c) 50 sessions → `short_history`, 1y
  metrics None; (d) series `SM` → `sme`; (e) symbol in the ASM set → `asm`; (f) adv 0.4 → `illiquid`.
- `add_ranks`: three symbols with vols 0.2 / 0.4 / 0.6 → ranks 0 / 50 / 100; None vols excluded and left None.
- `risk_row`: NaN, inf and `pd.NaT` become None; every value is JSON-serialisable; `as_of` is ISO;
  constants `WINDOW_DAYS == 400`, `POSITION_INR == 5e5`, `PARTICIPATION == 0.10` pinned.
- `format_table` renders flags and blanks without raising on None.

`tests/test_scheduled_refresh.py`: `refresh_risk.py` sits after `refresh_prices.py` and before the first
`scanner.run` step. `tests/test_freshness.py`: the schema-rule test passes with the new rule and floor.

Dashboard (`vitest`): `useHashRoute.test.js` (tab parses and defaults), `src/lib/risk.test.js`
(`flagLabel` covers every flag in §2 — read the flag list from one exported constant so a new flag without
a label fails the test, the `signalLabels` pattern; `fmtDaysToExit`).

## 8. Docs and housekeeping (same PR, separate `docs:` commit)

- `CLAUDE.md` → Architecture: a **Risk lens (2026-09-30)** bullet (module, table, loader, tab, "not a
  signal"); Decisions log: one dated line — *risk analytics are measurements surfaced next to candidates,
  not a catalog signal; no composite score; benchmark NIFTY 500; ₹5 lakh / 10% participation exit constant.*
  Update the daily-run description and the loader list in **Run**.
- `dashboard/src/learnings.json`: one entry, section `method`, e.g. *"Risk is measurement, not alpha"* — a
  lens needs no verdict and must never become a ranking; link `signals: []` or the relevant ones.
- `SUGGESTIONS.md`: a new dated section "Risk lens v2" with the §1 out-of-scope items as separate entries.
- `CANDIDATE_SIGNALS.md`: untouched (this is not a signal).

## 9. Commits (conventional, atomic)

1. `test: risk lens pure functions` → 2. `feat: scanner/risk.py` (tests green) →
3. `feat: risk_metrics table, refresh_risk loader, freshness rule, daily step` →
4. `feat: company Risk tab, header stat, Desk risk chips` → 5. `docs: risk lens v1`.

## 10. Definition of done

- `python -m pytest` green; `npm run lint --prefix dashboard`, `npm test --prefix dashboard`,
  `npm run build --prefix dashboard` green.
- `python scripts/refresh_risk.py --symbols RELIANCE,VRLLOG --print` prints sane numbers (RELIANCE beta
  near 1, vol 15-30%, exit 1 day; a small-cap shows the difference).
- Golden path in the browser (headless Edge screenshot per the project memory): `#/company/RELIANCE/risk`
  renders the three groups and the footer; Desk rows show chips; a symbol with no row shows the empty state.
- After merge: one `refresh-daily` run on Actions populates ≥ 1,500 rows and `check_freshness.py` passes
  with the new rule; the run time of the step is recorded in the PR description.

## 11. Build notes (2026-09-30) — where the build departs from this spec

- **`price_break` flag (added).** The first full run showed −65% to −80% one-session "falls" on ~2% of
  symbols (VMARCIND, SHANKARA, INDIAGLYCO, ALLCARGO …): splits / bonuses / demergers missing from
  `corporate_events`, which §2's guard cannot see (it only verifies actions it is given). A move beyond
  −30% / +43% after adjustment (outside every NSE price band), or a `demerger` event inside the window,
  now blanks the price metrics exactly like `action_unverified`. The loader fetches `demerger` events too;
  the 20% run guard counts both flags.
- **`as_of` is the symbol's last print**, not the run date (a suspended stock shows when its numbers are
  from). The freshness rule reads the newest `as_of`, so it is unaffected.
- **`--symbols` computes the whole run** and writes only the subset, so `vol_rank` / `liq_rank` stay
  market-wide percentiles.
- **Gap warning.** The loader WARNs on trading sessions missing from the benchmark inside the window —
  the store has a hole 2026-09-01..09 (SUGGESTIONS.md, Risk lens v2 section).
- **Desk chip is a link** to the company Risk tab, with the spoken sentence as its `aria-label`
  (`ui/RiskChip.jsx`). Same-day split + bonus (8 symbols) stays `action_unverified` — the fix belongs to
  `pricestore.adjust_for_actions` — fixed the same day (same-date factors multiply; 8 → 0).
- Measured: the full run takes ~30 s on the laptop (panel read 7-12 s); 3,157 rows; flags illiquid 1,560,
  sme 572, short_history 433, asm 228, sparse 187, price_break 64, gsm 64, action_unverified 8.
- After the price-hole backfill and that fix (same evening): action_unverified 0, price_break 36, no
  missing sessions in the window.
- First population on Actions (refresh-daily run 36739845402, 2026-09-30): 3,157 rows upserted; step time
  **41 s on the runner** (panel read 27 s); `check_freshness.py` passed with the new risk and hole rules.
