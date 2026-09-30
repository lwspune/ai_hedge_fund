# Market regime view v1 — implementation spec

**Status:** built 2026-09-30 (see §12) · **Written:** 2026-09-30 · **Owner:** Vilas · **Builder:** coding agent
**Read first:** `CLAUDE.md` (conventions, the discipline, decisions log) and `docs/RISK_LENS_SPEC.md`
(the pattern this follows). This spec assumes both.

## 0. Why this exists

The risk lens (2026-09-30) describes each security. Nothing yet describes **the market it sits in**. Is
NIFTY 500 near its high or in a correction? Is the rally broad or carried by a few names? Is volatility
calm or stressed against its own history? The same thin buyback spread or cheap rights entitlement reads
differently in each case. This is the second pillar of the "personal Aladdin without a position book"
direction and, like the first, it needs no holdings.

**What it is:** one row per trading day of market-wide measurements. It covers index drawdown, index
volatility and its percentile against history, and breadth: the share of liquid stocks above their 50 /
200-day averages, new 52-week highs and lows, and advancers. History goes back to 2020. It is shown as a
one-line strip on the Desk and a small **Market** page with charts.

**What it is not:** a signal or a timing rule. It carries no verdict, is not in the catalog, never gates an
alert, and has **no composite "risk-on / risk-off" label**. The flat-45% prior taught us not to invent
gradients. "Does breadth predict returns?" is a drift claim; it belongs in `CANDIDATE_SIGNALS.md` under the
drift bar, and nothing in this build may imply it.

Hard constraints carried from `CLAUDE.md`:

1. **Runs on GitHub Actions, never the laptop.** One new daily step plus a one-off backfill via `backfill.yml`.
2. **Database budget** (~275 MB, warn 300 / fail 400). One row per trading day since 2020: ~1,650 rows ×
   ~20 numbers, well under 1 MB. Unlike the risk lens, **history is a table**, because it is tiny.
3. **No silent bad data.** Breadth over unadjusted closes turns every bonus into a stock "below its 200-DMA".
   Every stock series is corporate-action-adjusted, and a stock is dropped from breadth on any date whose
   lookback spans a break it can't adjust (§2.3). The count of dropped stocks is stored, not hidden.
4. **No lookahead.** Every value on date *t* uses data up to *t* only, including the volatility percentile
   (expanding window) and the breadth universe (liquidity measured as of *t*).
5. **TDD.** Every pure function in §3 has a failing test before its implementation (§7).

**Reuse, not rebuild** (Avoid Duplication): `pricestore.bar_panel`, `pricestore.adjust_for_actions` /
`_action_factor`, `risk.PRICE_BREAK`, `risk.log_returns`, `risk.ann_vol`, `consolidation.MIN_TURNOVER_LAKH`.

## 1. Scope

**In (v1):**
- `scanner/regime.py`: pure functions for index metrics, adjusted segments, per-stock daily states,
  breadth aggregation and DB row shaping (§3).
- `db/schema.sql`: table `market_regime` (§4), a freshness rule and a floor (§5).
- `scripts/refresh_regime.py`: daily incremental run plus `--from` full rebuild (§5).
- `scripts/refresh_prices.py --indices-only`: backfill `index_prices` 2020-01 → 2022-07 from Yahoo (§5.1).
- `pricestore.bar_panel`: **additive** `series` column (§2.3). This touches shipped code; see §9.
- Dashboard: Desk regime strip + `#/market` page (three small-multiple charts + a recent-days table) (§6).
- Docs: `CLAUDE.md` bullet + decisions line, `learnings.json` entry if a lesson emerges, SUGGESTIONS v2 (§8).

**Out (v2, log in SUGGESTIONS.md, do not build):**
- Sector breadth / sector rotation (needs sector index closes; `index_prices` has ^NSEI, ^CRSLDX only).
- Breadth by cap bucket (large / mid / small via `pointintime.mcap_bucket_at`, which is heavy per date).
- FII / DII flows, India VIX, advance-decline from the NSE market-breadth endpoint (new sources).
- Any study of whether regime predicts returns (a drift candidate, not this build).

## 2. Definitions (the contract the tests pin)

### 2.1 Index block (from `index_prices`)

Benchmark **NIFTY 500** (`^CRSLDX`); **NIFTY 50** (`^NSEI`) is shown alongside for the large-cap contrast.

| Metric | Column | Definition |
|---|---|---|
| Close | `n500_close` | NIFTY 500 close on *t* |
| Drawdown | `n500_dd` | `close_t / max(close_u, 2020-01-01 ≤ u ≤ t) − 1` |
| NIFTY 50 drawdown | `n50_dd` | same for ^NSEI |
| Trailing return | `n500_ret_1m`, `n500_ret_3m` | `close_t / close_{t−k} − 1`, k = 21 / 63 index sessions; null when shorter |
| Realised vol | `n500_vol_20` | `risk.ann_vol` of the last 20 daily log returns (needs 20) |
| Vol percentile | `n500_vol_pct` | percentile (0-100) of `n500_vol_20` on *t* among all `n500_vol_20` values from the first computable date up to and including *t* (expanding, point-in-time); **null until 250 values exist** |

Index returns are on the index's own consecutive sessions. A trading day missing from `index_prices` is
now a freshness failure (hole rule), so no gap handling is needed beyond "the previous print".

### 2.2 Breadth universe (per date *t*)

A stock is **in the universe on *t*** when all of these hold:
- it printed on *t* in a mainboard series (`EQ`, `BE`, `BZ`); SME series (`SM`, `ST`, `SZ`) are out
  (thin, different participants, and most of the missing corporate actions live there);
- it has ≥ 200 adjusted prints up to *t* (the 200-DMA exists);
- its median `turnover_lakh` over its last 20 prints up to *t* ≥ `MIN_TURNOVER_LAKH` (₹1 crore/day, the
  consolidation scan's line), measured **as of *t***;
- it is not **excluded on *t*** by §2.3.

The company master is **not** a filter: the panel includes every symbol that printed, including ones
since delisted, so the history is survivorship-free.

### 2.3 Adjusted segments and exclusions

Per symbol, over its whole panel history: `adjust_segments(closes, actions) -> (adjusted, break_dates)`.
- Same-date split / bonus / consolidation groups whose jump the prices confirm (the `adjust_for_actions`
  rule, product of factors, `ADJUST_TOLERANCE`) are applied.
- A group the prices **don't** confirm is **not** applied; its ex-date goes into `break_dates`. This
  differs from `adjust_for_actions`, which returns None for the whole series. Six years of history must
  not be lost to one bad record.
- After adjustment, every one-session move beyond `risk.PRICE_BREAK` and every `demerger` ex-date also go
  into `break_dates`.

A stock is **excluded on *t*** when a break date lies within its last 250 prints up to *t*: that is the
longest lookback any breadth metric uses, so the metric would span the break. `n_excluded` counts stocks
that would otherwise be in the universe on *t*.

To drop SME series, `bar_panel` returns a `series` column: the series of the print it kept (EQ preferred,
as today). This is additive and existing callers read named columns. See §9.

### 2.4 Breadth metrics (over the universe on *t*, `n_universe` stocks)

| Metric | Column | Definition |
|---|---|---|
| Above 200-DMA | `pct_above_200` | share with `P_t > mean(P over last 200 prints)` |
| Above 50-DMA | `pct_above_50` | share with `P_t > mean(P over last 50 prints)` (≥ 50 prints; all universe stocks have 200) |
| New 52-week highs | `new_highs` | count with `P_t ≥ max(P over last 250 prints incl. t)` and ≥ 250 prints |
| New 52-week lows | `new_lows` | count with `P_t ≤ min(P over last 250 prints incl. t)` and ≥ 250 prints |
| Advancers | `up_share` | `adv / (adv + dec)` where adv / dec = universe stocks whose `P_t` is above / below their previous print; unchanged counted in neither; **null if the stock's previous print is more than 5 sessions back** (not a one-day move) |
| Universe | `n_universe`, `n_excluded` | as defined above |

Shares are fractions (0.38 = 38%). Percent formatting is the dashboard's job.

### 2.5 Constants (module-level in `scanner/regime.py`, pinned by a test)

```python
START = date(2020, 1, 1)          # bucket floor; first breadth row once 200 prints exist (~Oct 2020)
DMA_LONG, DMA_SHORT, HIGH_LOW = 200, 50, 250
VOL_WINDOW, VOL_PCT_MIN = 20, 250
MAINBOARD = ("EQ", "BE", "BZ")
LOOKBACK_DAYS = 420               # daily run: calendar days of panel for 250 prints + slack
RECOMPUTE_SESSIONS = 10           # daily run rewrites the last 10 sessions (heals a late bhavcopy)
```

## 3. Module `scanner/regime.py` — public API

```python
def index_metrics(n500: pd.Series, n50: pd.Series) -> pd.DataFrame      # per index date: §2.1 columns
def vol_percentile(vol: pd.Series, min_n: int = VOL_PCT_MIN) -> pd.Series  # expanding, point-in-time
def adjust_segments(closes: pd.Series, actions: list[dict]) -> tuple[pd.Series, list[pd.Timestamp]]
def stock_states(bars: pd.DataFrame, actions: list[dict]) -> pd.DataFrame
    # per print date: eligible (series + prints + turnover + not excluded), excluded, above_200, above_50,
    # new_high, new_low, move (+1 / -1 / 0 / NaN) — one pass per symbol, vectorised rolling windows
def breadth(states: dict[str, pd.DataFrame]) -> pd.DataFrame           # per date: §2.4 columns
def regime_rows(index_df: pd.DataFrame, breadth_df: pd.DataFrame, since: date | None = None) -> list[dict]
    # DB boundary: join on date, NaN/inf/NaT -> None, floats rounded 4 dp, ints as int, ISO dates
def format_table(rows: list[dict]) -> str                               # CLI print, last N days
```

`stock_states` never raises on a bad symbol. It returns all-false `eligible` and lets `breadth` count the
exclusions. A `BadPriceData` from `clean_series` propagates (a corrupt store, not a bad stock), as in the
risk lens.

## 4. Schema — `db/schema.sql` (append; apply via the Supabase MCP, keep the file in sync)

```sql
-- Market regime v1 (docs/REGIME_VIEW_SPEC.md): one row per trading day, 2020 ->, written by
-- scripts/refresh_regime.py. Measurements, not a signal: no verdict, no risk-on / risk-off label.
create table if not exists market_regime (
  trade_date     date primary key,
  n500_close     real check (n500_close is null or n500_close > 0),
  n500_dd        real check (n500_dd is null or (n500_dd <= 0 and n500_dd >= -1)),
  n50_dd         real check (n50_dd is null or (n50_dd <= 0 and n50_dd >= -1)),
  n500_ret_1m    real, n500_ret_3m real,
  n500_vol_20    real check (n500_vol_20 is null or n500_vol_20 >= 0),
  n500_vol_pct   real check (n500_vol_pct is null or n500_vol_pct between 0 and 100),
  pct_above_200  real check (pct_above_200 is null or pct_above_200 between 0 and 1),
  pct_above_50   real check (pct_above_50 is null or pct_above_50 between 0 and 1),
  new_highs      integer check (new_highs is null or new_highs >= 0),
  new_lows       integer check (new_lows is null or new_lows >= 0),
  up_share       real check (up_share is null or up_share between 0 and 1),
  n_universe     integer check (n_universe is null or n_universe >= 0),
  n_excluded     integer check (n_excluded is null or n_excluded >= 0),
  updated_at     timestamptz not null default now()
);
alter table market_regime enable row level security;
create policy "anon read market_regime" on market_regime for select to anon using (true);
```

## 5. Loaders

### 5.1 Index history — `scripts/refresh_prices.py --indices-only --from A --to B`

Calls the existing `refresh_indices(frm, to)` and nothing else: no bhavcopy fetch, no bucket write.
`backfill.yml` gains `what=indices` → `refresh_prices.py --indices-only --from "${FROM:-2020-01-01}"
--to "${TO:-2022-07-31}"`. Run once. Then check that the hole rule's 2020-2022 counterpart is clean with a
one-off query: every bucket session date since 2020 has an ^CRSLDX row. Fill any Yahoo gap from NSE's
`content/indices/ind_close_all_DDMMYYYY.csv` (the 2026-01-01 precedent). A missing index day makes that
date's `n500_*` null, never interpolated.

### 5.2 `scripts/refresh_regime.py`

```
python scripts/refresh_regime.py                    # daily: recompute the last RECOMPUTE_SESSIONS sessions, upsert
python scripts/refresh_regime.py --from 2020-01-01  # full rebuild (backfill.yml what=regime), upsert
python scripts/refresh_regime.py --print            # compute + print the last 20 rows, no write
```

1. Panel: daily = `bar_panel(today − LOOKBACK_DAYS, today)`; rebuild = `bar_panel(START, today)`
   (~6.5 years, ~4-5 M rows; measure memory and time on the runner and record them in the PR).
2. Actions: `corporate_events` of type split / bonus / consolidation / demerger for panel symbols (all
   dates; `adjust_segments` ignores ones outside a series).
3. Index: `get_closes("^CRSLDX" | "^NSEI", START, today, source="db")`, always from START, because the
   drawdown's running max and the vol percentile need the full history.
4. `states = {sym: stock_states(...)}` → `breadth(states)`; `index_metrics(...)`; `regime_rows(...,
   since=first date to write)`.
5. **Guards that fail the run:** the last written date is not the benchmark's last date (a stale or
   missing index); `n_universe` on the last date < 800 (≈ 1,400 liquid mainboard names today, so this
   fires only on a broken panel); `n_excluded / (n_universe + n_excluded)` on the last date > 10%;
   `pct_above_200` null on the last date.
6. `db.upsert_resilient("market_regime", rows, on_conflict="trade_date")`; fail the run on any rejected
   row, as `refresh_risk.py` does.

**Scheduling:** `["refresh_regime.py"]` in `scheduled_refresh.py` `daily`, right after `refresh_risk.py`;
extend `tests/test_scheduled_refresh.py`. **Freshness:** `TRADING_QUERIES["market_regime"] =
("market_regime", "trade_date", {}, 1)`; floor `{"table": "market_regime", "col": None, "min": 1400}`
(the whole history; a rebuild that silently wrote a year would trip it).

First population: merge → `gh workflow run backfill.yml -f what=indices` → `-f what=regime -f
from=2020-01-01` → the next daily run takes over.

## 6. Dashboard

Read-only, anon key, hash-routed, **no new dependencies** (charts are inline SVG). Formatting only via
`src/lib/format.js`. **Load the `dataviz` skill before writing any chart code.**

1. **Desk strip** (`src/components/RegimeStrip.jsx`), one line under the freshness strip, reading the
   latest `market_regime` row:
   `NIFTY 500 −6.2% from high · vol 18% (72nd pct) · 38% above 200-DMA · 12 highs / 45 lows` + an
   `InfoPopover` ("measurements, not a signal") + a link "Market →" to `#/market`.
   **Tone** is a display convention, not a verdict, and is written down in `src/lib/regime.js`:
   drawdown ≤ −10% (a correction by the usual convention) or vol percentile ≥ 90 → warn tone on that part
   only. There are no other thresholds and no label.
2. **Route** `#/market` (`useHashRoute.js` + test) and a top-nav link "Market" after "Desk".
3. **Market page** (`src/views/Market.jsx`):
   - Three **small-multiple line charts**, shared x-axis (2020 → today), one per question: *How far below its
     high?* (`n500_dd`, and `n50_dd` as a second line), *How broad?* (`pct_above_200`, `pct_above_50`),
     *How volatile vs its own past?* (`n500_vol_pct`). Hover or keyboard focus shows date + value. Each chart
     has a text alternative (its latest value and range) for screen readers.
   - A table of the last 20 sessions (every column), newest first, through the shared `DataTable`.
   - Footer: "Breadth: liquid mainboard stocks (≥ ₹1 cr/day), split / bonus-adjusted; {n_excluded}
     excluded today for unadjustable breaks. Not a signal."
   - Loading / empty / error through `ui/States` and `ui/Skeleton`.
4. **Data helpers** `src/lib/regime.js`: `loadLatestRegime()`, `loadRegimeHistory()` (whole table,
   ~1,650 rows, paged past the 1,000-row cap), `regimeTone(row)`, `fmtVolPct(n)` ("72nd pct"; reuse the
   ordinal from `lib/risk.js`, moving it to `format.js` if both need it). Unit-test the pure ones.
5. **Accessibility:** strip parts carry text, not colour alone (the warn part also reads "(correction)" /
   "(high vol)" in the popover and a `title`); charts are keyboard-focusable with visible focus; AA
   contrast through the existing tokens in light and dark.

## 7. Tests (write first; each must fail for the right reason before its implementation)

`tests/test_regime.py`, synthetic data only, no network:

- `index_metrics`: a path 100 → 120 → 90 → 110 gives `n500_dd` −0.25 at 90 and 110/120 − 1 at the end;
  trailing returns exact at k = 21 / 63, None when shorter; vol_20 None before 20 returns.
- `vol_percentile`: expanding and point-in-time. Appending a later huge value must **not** change any
  earlier percentile; None for the first 249 values; the 250th value's percentile is computed against 250.
- `adjust_segments`: a confirmed split is applied (no break); an unconfirmed bonus is **not** applied and
  its ex-date is a break, while a confirmed split later in the same series is still applied; a −50% move
  with no action is a break; a demerger ex-date is a break; same-date split + bonus is one confirmed jump.
- `stock_states`: SME series → never eligible; 199 prints → not eligible, 200 → eligible; turnover
  median ₹0.9 cr → not eligible (as of *t*: a stock that becomes liquid later is eligible only from then);
  a break excludes dates within 250 prints after it and not after; `above_200` exact on a hand-built
  series; `new_high` / `new_low` need 250 prints; `move` NaN when the previous print is > 5 sessions back.
- `breadth`: three stocks with known states → exact shares and counts; `up_share` ignores unchanged; a date
  where the universe is empty → shares None, counts 0.
- `regime_rows`: NaN / inf / NaT → None; every value JSON-serialisable; ISO dates; `since` filters.
- Constants pinned (§2.5).
- `test_scheduled_refresh.py`: `refresh_regime.py` after `refresh_risk.py` / `refresh_prices.py` and before
  `check_freshness.py`. `test_freshness.py`: rule + floor present (the schema test enforces the rule).
- `test_pricestore.py`: `bar_panel` keeps `series` = the kept print's series (EQ preferred over BE on a shared
  day). Build a tiny month frame and monkeypatch `_bhav_month`.

Dashboard (`vitest`): `useHashRoute.test.js` (`#/market`), `src/lib/regime.test.js` (`regimeTone` at
exactly −10% / 90th pct and just inside, `fmtVolPct`, history paging stitched in order).

## 8. Docs and housekeeping (same PR, separate `docs:` commit)

- `CLAUDE.md`: Architecture gets a **Market regime (date)** bullet; the Dashboard views list gains
  `#/market`; the daily-run description and loader list are updated; the Decisions log gets one line: *market
  regime = measurements with history (tiny table), breadth over liquid mainboard stocks with break-aware
  adjustment, no label / score / alert gating.*
- `SUGGESTIONS.md`: "Market regime v2" with the §1 out-of-scope items.
- `CANDIDATE_SIGNALS.md`: **one** backlog line, "breadth / vol regime as a return predictor (drift; needs
  the drift bar; the data now exists)". It is not tested here.
- `learnings.json`: only if the build produces a lesson.

## 9. Touches to shipped code (owner confirms in review of this spec)

| Change | Why | Blast radius | Reversible |
|---|---|---|---|
| `bar_panel` gains a `series` column | drop SME series from breadth as of each date | consolidation scan + risk lens read named columns; an extra column is inert (a test pins that `scan_now` output is unchanged) | yes, drop the column |
| `refresh_prices.py --indices-only` + `backfill.yml what=indices` | 2020-22 index history | new flag and new option; the default path is unchanged | yes |

`adjust_for_actions` is **not** changed. `adjust_segments` is a new function with a different contract
(keep the series, record breaks). The shared factor logic (`_action_factor`, same-date grouping) is reused,
not copied.

## 10. Commits (conventional, atomic)

1. `test: market regime pure functions` → 2. `feat: scanner/regime.py` →
3. `feat: bar_panel series column` (with its test) → 4. `feat: index-only price backfill` →
5. `feat: market_regime table, refresh_regime loader, freshness rule, daily step` →
6. `feat: Desk regime strip and Market page` → 7. `docs: market regime v1`.

## 11. Definition of done

- `python -m pytest` green; dashboard `lint`, `test`, `build` green.
- `python scripts/refresh_regime.py --print` sane on known dates. **2020-03-23** (the COVID low): `n500_dd`
  near −0.38 and `pct_above_50` in single digits (the 200-DMA breadth isn't computable until ~Oct 2020).
  **Any date:** `n500_dd` matches a hand computation from niftyindices closes. **2026-09-30:**
  consistent with the risk run (3,157 listed; a universe of ~1,000-1,500 liquid mainboard names).
- Full rebuild on Actions: time and peak memory recorded; ≥ 1,400 rows; `check_freshness.py` passes.
- Golden path in the browser (headless Edge, plus a 390 px iframe measure for overflow): Desk strip renders
  with tone rules and its link; `#/market` renders three charts, the table and the footer; keyboard focus
  reaches every chart point; empty state when the table is empty.

## 12. Build notes (2026-09-30) — where the build departs from this spec

- **Universe gains two rules** (found by comparing the daily window with the full rebuild, which disagreed for 7
  stocks): a gap of more than **20 sessions** (a suspension) starts a new segment — prints are counted and every
  window measured inside it, and the jump across the gap is not a break; and a stock must have printed on
  **≥ 200 of the last 250 sessions** (80%, the risk lens's `sparse` line). `LOOKBACK_DAYS` 420 → **520** so 250
  prints of any regular stock fit. The last 10 sessions are now identical between the two; a test pins it.
- **§11 COVID check was wrong:** breadth needs 200 prints, so it starts 2020-10-16 — nothing exists for
  2020-03-23. The index block does: NIFTY 500 −38.3%, NIFTY 50 −38.4% (12,362 → 7,610). Breadth checks used
  instead: 2024-06-04 (election result) 4% of stocks up; 2022-06-17 10% above the 50-DMA, 160 new lows; 2025-02-28
  12% above the 200-DMA, 363 new lows.
- **Index history:** `--indices-only` loaded 1,283 rows 2020-01 → 2022-07. Yahoo lacked 20 index-days where NSE
  traded (Muhurat, Budget Saturdays / Sunday, 2024 Saturday sessions, several 1 Jan / 26 Dec); all filled from
  NSE `ind_close_all_DDMMYYYY.csv`, each checked against the previous stored close + NSE's change. 2021-11-04
  (Muhurat) has an index close but no stock bhavcopy (NSE serves the previous day's file) → breadth blank that day.
- `pricestore.action_groups` / `confirmed_factor` extracted from `adjust_for_actions` (behaviour unchanged) so
  `adjust_segments` reuses them; the ordinal formatter moved to `format.js`.
- Reference lines (−10%, 90th pct) are keyed in each chart's header, not labelled inside the plot (the label
  collided with the 2020 crash).
- Measured: full rebuild 213 s cold / 70 s warm on the runner, peak 2.2 GB; daily window ~30 s. 1,677 rows.

