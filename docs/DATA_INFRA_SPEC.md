# Data-infra gap closure — implementation spec

**Status:** ready to build · **Written:** 2026-09-24 · **Owner:** Vilas · **Builder:** coding agent
**Read first:** `CLAUDE.md` (conventions, the discipline, decisions log). This spec assumes it.

## 0. Why this exists

A gap audit on 2026-09-24 (live Supabase counts + source probes) found the platform's data spine
has one broken loader and seven structural holes. The broken loader is the primary signal:
**every 2026 tender buyback has been silently rejected since January** because chittorgarh changed
its page wording. Nothing alarmed. The rest of the holes are what make backtests non-reproducible,
segmentation lookahead-biased, and the laptop a hidden dependency.

Two hard constraints from the owner shape every package below:

1. **The laptop is never a bottleneck.** Every loader, scan, backfill and validation must run
   unattended on GitHub Actions (or a Supabase edge function). If a step only works on the laptop,
   it is not done. Local runs are a convenience for development, nothing more.
2. **Data lives in Supabase.** Tables for what the scanner and dashboard query; the project's
   Storage buckets for bulk/history that would blow the 500 MB Postgres free tier. Local parquet is
   a read-through cache only, never the source of truth.

Budget today: Postgres 157 MB of 500 MB (filings = 109 MB). Storage bucket quota is 1 GB.
Every package states its footprint; WP5 adds a size guard so growth can't surprise us.

### Ground rules for the builder

- **TDD is mandatory** (`CLAUDE.md`): for each package, write the failing tests first from the
  fixtures listed, then the implementation. Pure parsing/math must be tested without network.
- **No silent bad data**: every loader gets a minimum-row / rejection-rate guard that fails the run.
- **Schema changes** go through the Supabase MCP (`apply_migration`) *and* are appended to
  `db/schema.sql` in the same commit. New tables: RLS on, `anon` select policy, writes via service
  role only. New RPCs: `revoke execute ... from public, anon, authenticated; grant ... to service_role`.
- **Loaders are idempotent** (upsert on a natural key, or atomic per-date reload via RPC).
- **Workflows**: extend `scripts/scheduled_refresh.py steps()` (it is tested), not the YAML, for
  new daily/weekly steps. New one-off backfills get their own `workflow_dispatch` workflow.
- **Probe from a runner before trusting a source**: add every new URL to
  `scripts/probe_sources.py` and run the `probe-sources` workflow once; paste the result in the PR.
- **Conventional commits**, one package per PR (WP1 may be two: fix, then backfill).
- Update `CLAUDE.md` (Architecture + Run + Decisions log) and `SUGGESTIONS.md` as each package lands.
- **Definition of done per package**: `python -m pytest` green, `npm run lint --prefix dashboard` and
  `npm test --prefix dashboard` green, the relevant workflow run green on Actions with the new
  freshness rule passing, and the dashboard golden path checked in the browser where a view changed.

---

## Work packages (in build order)

| # | Package | Fixes | Size |
|---|---|---|---|
| WP1 | Buyback discovery: 2026 page format | primary signal blind all year | ½ day |
| WP2 | Freshness: coverage, volume floors, rejection rate, DB size, CI red | WP1 went unnoticed | ½ day |
| WP3 | Prices in Supabase (daily bhavcopy) | no cloud price/volume store | 1–2 days |
| WP4 | Company master: industry fallback, delisting-by-diff, orphans | 76 % unknown industry; delistings stop 2020 | ½ day |
| WP5 | Point-in-time: snapshot history, historical market cap, index membership | lookahead in calibration/segmentation | ½ day |
| WP6 | Calendar: trading holidays, board meetings/results, band changes | no results dates, 4-day staleness heuristic | ½ day |
| WP7 | Evidence + validations in the cloud | verdict evidence only on the laptop | ½ day |
| WP8 | Filings retention + extraction floor | 109 MB table, KPI floor undocumented | ¼ day |

Dependencies: WP2 before WP3 (size guard must exist before the biggest table lands). WP3 before
WP5-b (historical market cap needs unadjusted closes). WP6 before WP3's staleness rule is exact
(until then WP3 uses the 4-calendar-day heuristic). Everything else is independent.

---

## WP1 — Buyback discovery: 2026 chittorgarh page format

### Evidence
Probed 2026-09-24. Ids 212–214 (2025 issues) parse; ids 215–240 (all 2026: Matrimony, Go Fashion,
Wipro ₹15,000 cr, Aurobindo, Cyient, Bajaj Auto, Kajaria, Garware, CMS Info …) exist (HTTP 200,
title "… Buyback 2026 Buyback Detail") and are all rejected by `parse_buyback` → `None`. Ids ≥ 250
307-redirect (frontier ≈ 240–249). `buybacks.max(chittorgarh_id) = 214`, zero 2026 rows, the daily
scan re-finds the same three closed 2025 buybacks and burns its 80-page hard cap every run.

Wording change (text after tag-stripping, `_text()`):

| Field | ≤ 2025 pages (id 213, Nectar) | 2026 pages (ids 219 Wipro, 225 Bajaj Auto) |
|---|---|---|
| entitlement | `Reserved Category for Small Shareholders 25 Equity Shares out of every 103 Fully paid-up Equity Shares held on the Record Date. 1,32,51,651 General Category …` | `Buyback Ratio Category Entitlement Ratio Shares Offered Small Shareholders 11 : 56 9,00,00,000 General Category 10 : 197 51,00,00,000 Note: …` |
| price | `buyback price of ₹27` (prose) and `Buyback Price 27 per share` | `Buyback Price 250 per share` only |
| record date | `record date … is December 24, 2025` and `Record Date December 24, 2025` | `Record Date June 5, 2026` and timetable `Record Date Fri, Jun 5, 2026` |
| closing | `Buyback Closing Date January 6, 2026` (2-col table) | `Buyback Closing Date June 17, 2026` (same) |
| type | `Issue Type Tender Offer` | `Issue Type Tender Offer` |
| size | `Issue Size (Amount) 81.00 Crores` | `Issue Size (Amount) 15,000.00 Crores` |

Semantics unchanged: "11 : 56" = 11 shares accepted per 56 held = 11/56, same as "11 out of every 56".

### Tests first (`tests/test_buyback.py`)
Save the raw HTML of ids 213, 219, 225 as fixtures under `tests/fixtures/buyback/<id>.html`
(fetch once with `allow_redirects=False`; ~200 KB each, fine). Then:

- `parse_entitlement`: `"Small Shareholders 11 : 56 9,00,00,000"` → `11/56`;
  `"Small Shareholders 17 : 61"` → `17/61`; old wording still → `25/103`;
  `"General Category 10 : 197"` must **not** match (anchor on "Small Shareholders");
  result must satisfy `0 < r <= 1` else `None`.
- `parse_buyback(fixture_219)` → symbol `WIPRO`, buyback_price `250`, record_date `2026-06-05`,
  close_date `2026-06-17`, entitlement `11/56`, issue_size_cr `15000.0`.
- `parse_buyback(fixture_225)` → `BAJAJ-AUTO`, `12000`, `2026-06-24`, `2026-07-07`, `17/61`, `5632.8`.
- `parse_buyback(fixture_213)` unchanged (regression).
- New `parse_issue_type(html) -> "tender" | "open_market" | None`; an open-market page (find one
  id in 215–249 without an entitlement table, or synthesise) → `None` from `parse_buyback`.
- Discovery accounting: `scan_current_buybacks` returns (or logs via a `stats` dict) `pages_seen`,
  `tender_parsed`, `rejected`; test with a stub session that serves the three fixtures.

### Implementation
- `scanner/buyback.py`
  - `parse_entitlement`: accept `Small Shareholders\s*(\d+)\s*:\s*(\d+)` **and** the old
    `(\d+)\s+Equity Shares out of every\s+(\d+)`; keep the table-scan in `parse_buyback` but also
    fall back to the flattened text when no table matches (2026 pages render the ratio table
    without the "Reserved Category" cell).
  - Price: `Buyback Price\s*₹?\s*([\d,]+(?:\.\d+)?)\s*per share` first, then the old prose regex.
  - Record date: add `Record Date\s+([A-Z][a-z]+ \d{1,2},\s*\d{4})` fallback.
  - Guard: reject if `Issue Type` is present and is not `Tender Offer`.
  - `scan_current_buybacks`: `hard_cap` 80 → 120 and `max_gap` 8 → 12 (frontier moved ~35 ids in
    nine months); return stats; log `pages_seen / tender_parsed / rejected` in `run.py` output.
- `supabase/functions/refresh-buybacks/index.ts`: same three regex changes (`ent`, `bpM`, `rdM`);
  redeploy via MCP; bump the version comment.
- `scanner/db.py` nothing; `buybacks.status` semantics unchanged (dashboard "open" comes from
  `candidates.payload.is_open`).

### Backfill (once, from Actions)
`gh workflow run refresh-daily.yml` after merge runs `scanner.run buyback_arb --save` from
frontier 211 and now lands ids 215–249. Verify in SQL: `count(*) filter (where record_date >= '2026-01-01') >= 20`
and that Wipro/Bajaj Auto rows have `issue_size_cr`. If the daily run's hard cap stops short, run
it twice.

### Freshness (lands in WP2, but WP1 is not done without it)
Rule `buyback_frontier`: fail if `max(buybacks.chittorgarh_id)` has not advanced in 60 days **or**
the last `buyback_arb` scan_run's params show `tender_parsed == 0 and pages_seen >= 10`.
Persist `pages_seen/tender_parsed/rejected` in `scan_runs.params` so the rule can read them.

### Acceptance
- Tests above green; `python -m scanner.run buyback_arb` (no save) lists the 2026 tender offers with
  premium/entitlement filled and plausible (`-0.5 < premium < 1.5`).
- Dashboard Desk "Act" panel shows an open buyback when one exists (none may be open on merge day;
  check the Data → buybacks view shows 2026 rows).

---

## WP2 — Freshness monitoring: coverage, volume, rejection rate, size, CI

### Evidence
`scripts/check_freshness.py` watches six tables by "newest row" only. Uncovered: `buybacks`,
`fo_ban` events, `rights_issues`, `company_kpis`, `scan_runs`. A loader that writes one row and
drops the rest passes. The CI run for commit `4f552e3` is **red**: `dashboard/src/lib/signalLabels.test.js`
fails because `order_wins` has no label in `src/lib/signalLabels.js`.

### Tests first (`tests/test_check_freshness.py`)
- `stale()` unchanged behaviour for age rules.
- New `too_thin(counts, floors, today)` → list of `(name, n, floor)` for windows under their floor.
- New `frontier_stuck(latest_id, last_advance_date, today, max_days)`.
- Rule table is data; test that every table in `db/schema.sql` with a date column has a rule
  (parse `create table` names from the file; allowlist `tenders`, `outcomes`, `symbol_changes`).

### Implementation
Extend `QUERIES` with age rules and add a `FLOORS` table (rows in the last N trading days, using
calendar days until WP6 lands, then `trading_calendar`):

| name | table / filter | max age | floor |
|---|---|---|---|
| deals | market_deals | 6 d | ≥ 40 rows in last 3 trading days |
| corporate_actions | corporate_events nse_ca | 7 d | ≥ 20 rows / 7 d |
| fo_ban | corporate_events nse_fo | 6 d | none (can legitimately be empty) — age only, on `created_at` |
| ipo_listings | ipos listing_date ≤ today | 14 d | — |
| rights_issues | rights_issues updated_at | 10 d | — |
| companies | companies updated_at | 8 d | listed count ≥ 2,500 |
| fundamentals | company_snapshot fetched_at | 8 d | ≥ 2,000 rows fetched in last 8 d |
| filings | filings disclosed_at | 5 d | ≥ 200 rows / trading day (avg of last 3) |
| kpis | company_kpis created_at | 5 d | — |
| scans | scan_runs per signal in {buyback_arb, rights_re} | 3 d | — |
| buyback_frontier | see WP1 | 60 d | — |
| prices (WP3) | daily_prices trade_date | 4 d (calendar; 1 trading day after WP6) | ≥ 2,500 rows on latest date |
| db_size | `pg_database_size` via RPC `db_size_bytes()` (service role) | — | fail > 400 MB, warn > 300 MB |

Add RPC `db_size_bytes()` (security definer, service role only) since PostgREST can't run
`pg_database_size`. Print a one-line table each run; exit 1 on any failure.

Also in this package: add the `order_wins` entry to `dashboard/src/lib/signalLabels.js` so CI is
green again (label "Order wins", headline from `CONCLUSIONS.md` §11).

### Acceptance
`refresh-daily` and `refresh-weekly` green with the new rules; deliberately breaking one (e.g.
`FLOORS['filings']=10**6`) fails the run locally.

---

## WP3 — Prices in Supabase: daily NSE bhavcopy

### Evidence / source facts (probed 2026-09-24 from the laptop; confirm from a runner via probe-sources)
- `https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_DDMMYYYY.csv` → HTTP 200,
  ~400 KB, 3,517 rows for 2026-09-23. Header (note the padded spaces):
  `SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, LAST_PRICE, CLOSE_PRICE, AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS, NO_OF_TRADES, DELIV_QTY, DELIV_PER`.
  Row: `20MICRONS, EQ, 23-Sep-2026, 216.45, 220.80, 223.95, 215.80, 219.00, 219.21, 220.06, 104573, 230.13, 3299, 43130, 41.24`.
  Series mix: EQ 2668 · SM 382 · BE 233 · ST 85 · GS 57 · GB 42 · BZ 27 · IV 14 (keep EQ/BE/BZ/SM/ST/SZ; drop the rest).
  `DELIV_QTY`/`DELIV_PER` are `-` for some series. Non-trading days → 404.
- Archive depth: 2021-01-04 → 200; 2024-01-02 → 200; 2019-01-02 and 2016-01-04 → 404. **Backfill
  floor = 2020-01-01** (verify the exact first available date by probing Jan 2020). Pre-2020 history
  stays on nselib per symbol (already in `pricestore._fetch_nse`).
- The same host already serves `bulk.csv` and the F&O ban CSVs from GitHub runners.
- Benchmarks (`^NSEI`, `^CRSLDX`): yfinance works from runners (probed earlier); store them too.
- Unadjusted closes are what every nominal-price comparison needs (buyback/open-offer/RE premiums);
  this store is **unadjusted by construction**. Split/bonus adjustment, if ever needed, is derived
  from `corporate_events` (bonus/split ratios) — a pure function, later.

### Storage design (footprint first)
- **Table `daily_prices`** — rolling **2 years**, EQ-family series only, one row per (symbol, date):
  ```sql
  create table daily_prices (
    symbol       text not null,
    trade_date   date not null,
    series       text not null check (series in ('EQ','BE','BZ','SM','ST','SZ')),
    close        real not null check (close > 0),
    prev_close   real,
    volume       bigint check (volume is null or volume >= 0),
    turnover_lakh real check (turnover_lakh is null or turnover_lakh >= 0),
    delivery_pct real check (delivery_pct is null or (delivery_pct >= 0 and delivery_pct <= 100)),
    primary key (symbol, trade_date)
  );
  create index idx_daily_prices_date on daily_prices(trade_date);
  ```
  ~3,400 rows/day × ~250 days ≈ 850 k rows/yr ≈ 85 MB/yr with the PK index (real, not numeric,
  on purpose). Two years ≈ 170 MB. With filings trimmed in WP8 the DB stays under ~350 MB.
  If a date prints a symbol in two kept series, keep the first by the `NSE_SERIES` rank (EQ first)
  — same rule as `pricestore.nse_frame_to_series`.
- **Table `index_prices`** — `(index_symbol text, trade_date date, close real, pk(index_symbol, trade_date))`,
  full history for `^NSEI`, `^CRSLDX` (NIFTY 500) and `^NSMIDCP` if used; tiny.
- **Bucket `prices`** (private) — the durable full history: one parquet per month
  `bhav/YYYY-MM.parquet` holding **all** columns and **all** series exactly as published
  (~1.5 MB/month, ~120 MB for 2020→2026). Written by the same loader; the table is derived from it.
- **RPC `reload_daily_prices(p_date date, p_rows jsonb) returns int`** — delete+insert for one
  date in one transaction (clone of `reload_market_deals`). Service role only.
- **RPC `prune_daily_prices(p_keep_days int) returns int`** — deletes rows older than the window;
  called weekly. Service role only.

### Code
- `scanner/bhavcopy.py` (new, pure parsers + thin fetcher):
  - `parse_bhavcopy(text) -> list[dict]` → rows for `daily_prices` (strip padded headers/values,
    `-` → None, filter series, dedupe by series rank, `DATE1` `%d-%b-%Y` → ISO). Guard: raise if
    < 1,000 EQ rows (a truncated or wrong file), or if any `close <= 0`.
  - `bhav_url(d)`; `fetch_bhavcopy(d, session) -> str | None` (404 → None; non-200 → raise).
  - `to_month_frame(rows_by_date) -> DataFrame` for the parquet.
- `scanner/pricestore.py`:
  - New source `"db"`: `get_closes(sym, start, end, source="db")` reads `daily_prices` via
    PostgREST (`select_all`, 1,000/page; a 2-year single-symbol pull is one page) for the part of
    the range inside the retention window, and `bhav/YYYY-MM.parquet` from the bucket for the
    older part (download once per run into `cache/px/bhav/`; that directory is a cache).
  - New `get_bars(sym, start, end)` returning close/volume/turnover/delivery (same sources).
  - **Make `source` a required keyword** on `get_closes` (no default) so no caller silently gets
    adjusted Yahoo closes for a nominal-price comparison. Update every caller listed in
    `grep -rn "get_closes(" scanner scripts`: validations that compare to nominal prices use
    `"db"` (or `"nse"` for pre-2020); pure abnormal-return studies may keep `"yf"`.
  - Benchmarks: `get_closes("^NSEI", …, source="db")` reads `index_prices`.
- `scanner/buyback.scan_current_buybacks`: replace the inline `yf.Ticker(...).history` with
  `get_closes(sym, today-15d, today, source="db")` (last close). Same in
  `scanner/rights.py` (currently `source="nse"`, fine to switch).
- Retire `scanner/prices.py` (`fetch_closes_yf/jugaad`); `scanner/scan.py` (mean_reversion) uses
  `get_closes(..., source="yf")` — adjusted is correct for RSI/200-DMA.
- Loaders:
  - `scripts/refresh_prices.py [--date D | --from A --to B]` — per date: fetch → parse →
    `reload_daily_prices` → append to that month's parquet in the bucket (read-modify-write the
    month file; months are small). Default: last 5 calendar days (heals a missed run). Also
    refreshes `index_prices` from yfinance for the same window.
  - Daily step in `scheduled_refresh.steps("daily")` **right after** `fo-ban` and **before** the
    buyback/rights scans (they now read prices from the table).
  - Weekly step: `prune_daily_prices(730)`.
  - Backfill workflow `.github/workflows/backfill-prices.yml` (`workflow_dispatch`, input `year`):
    runs `refresh_prices.py --from YYYY-01-01 --to YYYY-12-31` with 0.3 s politeness; ~250 files ≈
    5 min/year; run 2020…2026 one at a time (concurrency group `refresh` so it never overlaps the
    daily). Table rows older than 2 years are pruned afterwards; the bucket keeps them.
- `scripts/probe_sources.py`: add the bhavcopy URL; run `probe-sources` before merging.

### Tests first (`tests/test_bhavcopy.py`, `tests/test_pricestore.py`)
- Fixture: the first ~60 lines of a real `sec_bhavdata_full` file (include GS/GB/IV rows, a `-`
  delivery, a symbol printing in EQ and BE on the same day).
- `parse_bhavcopy`: header padding stripped; series filter; dedupe keeps EQ; `-` → None;
  date parsed; the < 1,000-row guard raises; `close <= 0` raises.
- `pricestore.get_closes(source="db")` with a stubbed `db.select_all` and a stubbed bucket reader:
  window split (recent from table, older from parquet), inclusive bounds, `None` on empty.
- Calling `get_closes` without `source` raises `TypeError` (compile-time guard for the footgun).

### Freshness
`prices`: newest `trade_date` ≤ 4 calendar days old (1 trading day after WP6) **and** ≥ 2,500 rows
on that date; `index_prices` newest ≤ 4 days.

### Acceptance
- `backfill-prices` green for 2024–2026 (older years may follow); `select count(distinct trade_date)`
  ≈ 250/yr; spot-check `WIPRO` close on 2026-06-04 against the buyback fixture's "Last Date to buy".
- `scanner.run buyback_arb` and `rights_re` on Actions no longer import yfinance for prices.
- DB size after backfill and prune < 350 MB (WP2 guard passes).

---

## WP4 — Company master: industry fallback, delisting-by-diff, orphans

### Evidence
`companies`: 3,155 listed; 2,405 have `industry is null` (niftyindices lists cover ~750 names) and
therefore `is_financial is null`. 2,397 of those have a screener `sector` in `company_snapshot`;
8 have neither. Financials: master flags 121, screener 305. `delisted.csv` last date 2020-11-09 →
327 delisted rows; anything delisted 2021→ vanishes from `companies` (EQUITY_L is current-only).
Orphans (symbol absent from `companies`): 132 symbols — filings 3,966 rows, market_deals 4,096,
corporate_events 3,229 (LEEL, RELCAPITAL, IDFC, JPINFRATEC, PUNJLLOYD, ROLTA, …); none resolve
through `symbol_changes`.

### Schema
```sql
alter table companies add column industry_source text
  check (industry_source is null or industry_source in ('niftyindices','screener'));
alter table companies add column last_seen_listed date;      -- date of the last EQUITY_L that had it
alter table companies add column delist_source text
  check (delist_source is null or delist_source in ('nse_delisted_csv','equity_l_diff','manual'));
```
(`delisted_on` + status check already exist.)

### Code + tests first (`tests/test_master.py`)
- `build_companies(equities, indices, delisted, screener_sectors, previous_listed, today)`:
  - industry: niftyindices first (`industry_source='niftyindices'`), else screener `sector` mapped
    to the niftyindices vocabulary (`Financial Services` ↔ `Financial Services`; keep others
    verbatim, `industry_source='screener'`); `is_financial` from whichever source filled it.
  - **delisting by diff**: every symbol in `previous_listed` (current `companies` rows with
    `status='listed'`) that is absent from today's EQUITY_L+SME lists and not renamed (per
    `symbol_changes`) → `status='delisted', delisted_on=today, delist_source='equity_l_diff'`.
    Never delete rows. Renamed symbols: keep the old row as `delisted` with `delist_source`
    `'equity_l_diff'` and `name` unchanged (joins on old filings keep working), or resolve via
    `resolve_symbol` — test both paths.
  - `last_seen_listed = today` for every symbol present.
  - Guard: raise if EQUITY_L parses to < 1,800 rows or SME < 300 (a truncated download must not
    mass-delist the market).
- `scripts/refresh_companies.py`: load `previous_listed` and screener sectors from Supabase before
  building; upsert; print `listed / newly_delisted / industry_filled` counts; fail if
  `newly_delisted > 50` in one run (sanity).
- One-off `scripts/backfill_orphans.py` (run from Actions via `workflow_dispatch` input on the
  weekly workflow, or a tiny dedicated workflow): for each orphan symbol across filings/deals/events,
  insert `companies(symbol, name from filings.company, status='delisted', delisted_on = last
  trade_date from daily_prices/nselib, delist_source='manual')`. Print the list; expect ~132.

### Freshness
`companies`: listed ≥ 2,500 (WP2); add `industry_null_pct < 5 %` of listed.

### Acceptance
`is_financial` known for > 99 % of listed; orphan counts → 0; `refresh_fundamentals` still selects
the same universe (it filters on `status='listed'`).

---

## WP5 — Point-in-time data

### Evidence
`company_snapshot` is overwritten weekly (market cap, price, shareholding as of now). The buyback
acceptance prior and any size segmentation in validations bucket on *today's* cap. Index membership
is current-only (`companies.indices`); "was X in Nifty Next 50 on date D" is unanswerable except via
the hand-curated `data/next50_rebalance_events.csv`.

### Schema
```sql
create table company_snapshot_history (
  symbol         text not null references companies(symbol) on update cascade,
  as_of          date not null,                       -- run date (weekly)
  market_cap_cr  numeric, price numeric, pe numeric,
  promoter_pct   numeric, fii_pct numeric, dii_pct numeric, public_pct numeric,
  n_shareholders bigint, shp_period date,
  primary key (symbol, as_of)
);
create table index_membership (
  symbol text not null, index_key text not null,      -- nifty50, niftynext50, midcap150, ...
  from_date date not null, to_date date,              -- null = current
  source text not null check (source in ('niftyindices_list','niftyindices_pdf','curated')),
  primary key (symbol, index_key, from_date)
);
```
Footprint: ~3,100 rows/week ≈ 160 k rows/yr ≈ 15 MB/yr. Fine.

### Code + tests first
- `refresh_fundamentals.py`: after each snapshot batch upsert, insert the same rows into
  `company_snapshot_history` with `as_of = run date` (upsert on pk so re-runs are idempotent).
- `scanner/fundamentals.historical_market_cap(statements_df, closes) -> Series`: shares outstanding
  per balance-sheet period = `Equity Capital / face_value` (both already in the parquet/statements;
  face value from ratios), forward-filled between periods × unadjusted close (WP3). Pure, tested
  with a synthetic statements frame (a split changes face value and equity-capital share count
  consistently; assert mcap is continuous across it).
- `scanner/master.py`: `membership_diff(previous_current, todays_lists, today)` → close
  intervals for symbols dropped, open new ones for symbols added; weekly loader writes
  `index_membership` (`source='niftyindices_list'`). Seed `from_date` for the initial load as
  the first run date; load the Next-50 curated CSV as `'curated'` intervals (it already has dates).
- Validations/segmentation helpers get `mcap_bucket_at(symbol, date)` using history when the
  date is after the first `as_of`, else `historical_market_cap`.

### Acceptance
Weekly run adds history rows; `calibrate.py` and `validate_buyback_arb.py` bucket on the as-of cap
(document in `CONCLUSIONS.md` if numbers move).

---

## WP6 — Calendar: trading holidays, board meetings/results, band changes

### Evidence (probed 2026-09-24, plain session + `Referer: https://www.nseindia.com/`)
- `https://www.nseindia.com/api/holiday-master?type=trading` → 200 JSON, keys `CM`, `FO`, … each
  a list of `{tradingDate: "15-Jan-2026", weekDay, description}`.
- `https://www.nseindia.com/api/corporate-board-meetings?index=equities` → 200 JSON rows
  `{bm_symbol, bm_date: "05-Nov-2026", bm_purpose, bm_desc, …}` (upcoming + recent).
- `https://www.nseindia.com/api/event-calendar` → 200 JSON `{symbol, company, purpose, bm_desc, date…}`.
- `https://nsearchives.nseindia.com/content/equities/eq_band_changes.csv` → 200
  (`Sr. No.,Symbol,Series,Security,From,To`).
- ASM/GSM static lists (`asm_list.csv`, `gsm_list.csv`) → 404. **Still parked.**
These are the same API family as `api/corporate-announcements`, which already works from runners;
confirm with `probe-sources` before merging.

### Schema
```sql
create table trading_calendar (
  trade_date date primary key, is_trading boolean not null,
  description text, source text not null default 'nse_holiday_master'
);
-- corporate_events.event_type gains: 'board_meeting', 'results', 'band_change'
-- corporate_events.source gains: 'nse_bm', 'nse_band'
```
Generate `trading_calendar` rows for every weekday of the current and next year, `is_trading=false`
on holidays (CM segment) — a pure function `calendar_rows(holidays, year)`.

### Code + tests first (`tests/test_events.py`)
- `parse_holiday_master(json) -> list[date]` (CM segment only).
- `parse_board_meetings(json) -> events`: `event_type='results'` when `bm_purpose`/`bm_desc`
  matches `financial results|results` (case-insensitive), else `'board_meeting'`; `details`
  keeps the purpose text; `event_date = bm_date`.
- `parse_band_changes(csv) -> events` with `details={'from':..,'to':..}`.
- `scanner/calendar.py`: `next_trading_day(d)`, `trading_days_between(a, b)`, `age_in_trading_days`;
  `pricestore` and `check_freshness` switch to trading-day staleness.
- Loaders: `refresh_events.py holidays|board-meetings|bands` and daily steps for the last two;
  holidays weekly.
- Every `validate_*.py` gains an optional `--exclude-results-window N` that drops events within
  N trading days of a `results` event for the same symbol (contamination control); document usage.

### Acceptance
`trading_calendar` covers this and next year; freshness rules use it; `corporate_events` gains
`results` rows daily.

---

## WP7 — Evidence in the cloud + validations on Actions

### Evidence
Every result set behind a `CONCLUSIONS.md` verdict lives in the gitignored `cache/` on the laptop:
`lockin_results.csv` (324 KB), `fnoban_results.csv`, `promoter_buys_results.csv`,
`order_wins_results.csv`, `rights_re_results.csv`, `cache/re/*.csv` (RE closes+turnover, 593 KB),
`cache/reg29/*.json` (23 MB). Only `data/next50_rebalance_events.csv` is committed. Sources drift
(WP1 is the proof), so a re-run may not reproduce the numbers.

### Design
- **Bucket `evidence`** (private): `<signal>/<run-date>/{events.csv,results.csv,summary.json,meta.json}`;
  `meta.json` = git SHA, script, args, source floors, row counts.
- **Table `validation_runs`** `(id, signal_name, run_at, git_sha, script, params jsonb,
  summary jsonb, evidence_path text)` — the queryable index; the dashboard Signals view links the
  latest evidence path per signal.
- **Workflow `validate.yml`** (`workflow_dispatch`, inputs `script` = one of `scripts/validate_*.py`,
  `args`): runs the script on a runner with prices from WP3 (+ nselib for pre-2020), uploads the
  artefacts to the bucket, inserts `validation_runs`. Runners have no persistent disk, so every
  validation must build its event set from Supabase tables or reachable sources (they already do)
  and read prices through `pricestore` (WP3 makes that cloud-backed).
- One-off: upload the existing laptop result files as the `2026-09-24` baseline for each signal
  (from the laptop, once — the last time it is needed), so the current `CONCLUSIONS.md` numbers
  have a stored artefact.

### Code + tests first
- `scanner/evidence.py`: `evidence_paths(signal, run_date)`, `meta(signal, script, args, counts)`
  (pure); `publish(signal, files, summary)` (thin, uses `db.storage_put` + `db.insert`).
- Each `validate_*.py`: replace `cache/*.csv` writes with `evidence.publish(...)`; keep a local
  copy under `cache/` as a convenience.
- `CONCLUSIONS.md`: each section gets `evidence: <bucket path> · sha <short>`.

### Acceptance
`validate.yml` runs `validate_rights_re.py` green on Actions and the artefacts appear in the
bucket and in `validation_runs`; the Signals view shows the evidence link.

---

## WP8 — Filings retention and the KPI extraction floor

### Evidence
`filings` = 185,563 rows / 109 MB (subject up to 600 chars), growing ~5–10 k rows/month.
`extract_kpis.py --since 2025-07-01` → ~17 k KPI-bearing filings since then, ~4.6 k extracted;
the 2024-01 → 2025-06 range (~15 k KPI-bearing) is never extracted by design but undocumented.
2,215 filings have no attachment; `company_kpis` covers 399 symbols.

### Decisions (owner to confirm; defaults below)
- **Extraction floor:** extend `--since` to **2024-01-01** and let the daily cap (1,500 PDFs) chew
  the backlog (~10 more runs). Rationale: order-win and KPI history back to the category's start
  makes the `order_wins` and future sector-pack studies use their full n.
- **Retention:** keep all rows, but move `subject` for filings older than 24 months into the
  bucket (`filings/YYYY-MM.parquet`, full rows) and set `subject = null` in the table (saves ~40 %).
  Never delete `seq_id` rows (KPI FK + dashboard counts).

### Code + tests first
- `scripts/archive_filings.py --older-than 24m`: monthly parquet to bucket `filings` (private) then
  null the `subject` column via one `update` per month; idempotent. Weekly step.
- `extract_kpis.py`: default `--since 2024-01-01`; the freshness `kpis` rule from WP2 covers it.
- `scanner/filings.parse_announcements`: cap `subject` at 300 chars (test).

### Acceptance
Table size drops below ~80 MB after the first archive; backlog reaches zero (`pending()` returns
0 for `--since 2024-01-01`) within two weeks of daily runs.

---

## Cross-cutting

### New buckets / RPCs summary
| Object | Package | Access |
|---|---|---|
| bucket `prices` | WP3 | private; service role |
| bucket `evidence` | WP7 | private; service role (dashboard links go through a signed-URL RPC later; out of scope) |
| bucket `filings` | WP8 | private |
| RPC `reload_daily_prices`, `prune_daily_prices` | WP3 | service_role |
| RPC `db_size_bytes` | WP2 | service_role |

### Workflow changes
- `refresh-daily`: + `refresh_prices.py` (after fo-ban), + `refresh_events.py board-meetings|bands`
  (WP6); timeout stays 150 min (bhavcopy ≈ 1 min).
- `refresh-weekly`: + `prune_daily_prices`, + `index_membership` diff, + `refresh_events.py holidays`,
  + `archive_filings.py`.
- New: `backfill-prices.yml`, `validate.yml`; `probe-sources` gains the new URLs.
- Secrets unchanged (`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`).

### Docs to update as you go
- `CLAUDE.md`: Architecture (I2 price store → Supabase-backed; new tables; calendar; evidence),
  Run (new scripts/workflows), Decisions log (one dated line each: prices in Supabase not parquet
  — *reason:* laptop must not be a dependency and every scan runs on Actions; bhavcopy floor 2020;
  `source` required on `get_closes`).
- `db/schema.sql`: every DDL above.
- `SUGGESTIONS.md`: strike the ASM/GSM entry's "probe BSE" note as re-probed (still 404).
- `CONCLUSIONS.md`: evidence links (WP7); any number that moves under as-of market caps (WP5).

### Out of scope (explicitly)
ASM/GSM (gated, re-probed 404), delisting RBB (parked), F&O bhavcopy (zip probed 200 — cheap to add
later for candidate #12, not now), Kite Connect.
