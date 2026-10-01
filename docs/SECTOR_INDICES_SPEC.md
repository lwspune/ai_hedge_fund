# Sector indices v1 — sector-relative risk + sector table — implementation spec

**Status:** approved 2026-10-01 · **Written:** 2026-10-01 · **Owner:** Vilas · **Builder:** coding agent
**Read first:** `CLAUDE.md`, `docs/RISK_LENS_SPEC.md`, `docs/REGIME_VIEW_SPEC.md`. This spec extends both.

## 0. Why this exists

The risk lens measures every stock against NIFTY 500, so a bank's beta mostly says "banks moved". The
regime view can tell that the market is weak, but not whether the weakness is broad or sits in one or two
sectors. Both v2 backlogs deferred this work for lack of sector index closes.

The fallback we just built reads NSE's daily index-close file (`ind_close_all_DDMMYYYY.csv`). That file
carries **166 NSE indices, including every sector index**, back past 2020. So the data source is already
integrated, proven from runners, and checked by `confirm_close`.

**What it is:**
1. **Sector index history** in `index_prices`, about 25 indices, back to each index's first file.
2. **Sector-relative risk** on the company Risk tab: beta and correlation to the stock's sector index, and the
   sector's 3-month return next to the stock's.
3. **A sector table** on the Market page: each sector's distance below its high, 1m / 3m return, 3m return
   relative to NIFTY 500, and the share of its stocks above their 200-DMA.

**What it is not:** a sector-rotation signal. "Buy the strongest sector" is public momentum, a drift idea.
Nothing here ranks sectors as a recommendation, gates an alert or implies a trade.

Hard constraints (from `CLAUDE.md`): Actions not laptop · no silent bad data (every stored close passes
`confirm_close` against the previous close) · TDD · DB budget. The DB is at **281 MB** (warn 300). This build
adds **≈ 4 MB** (index rows ~3.5 MB; the sector table is one row per sector, overwritten daily). The size
follow-up is logged in §1 Out.

## 1. Scope

**In:**
- `data/sector_map.csv`: NSE industry → primary sector index + fallback index (§2.1, **owner reviews the
  table**).
- `data/sector_indices.csv`: the indices to load, with the exact NSE name(s) of each (aliases for renames).
- `scanner/bhavcopy.parse_index_closes(text, names=None)`: generalised from the two benchmarks to any
  name map. The default keeps today's behaviour.
- `scripts/refresh_prices.py`: daily sector closes for the run's sessions, from NSE files (Yahoo isn't used
  for sectors); `--sectors-only --from --to` for the backfill (`backfill.yml what=sector-indices`).
- `scanner/sectors.py`: pure helpers for loading the map, picking the index to use per stock (§2.2), and the
  sector table maths (§2.4).
- Risk lens: 4 new `risk_metrics` columns (§2.3), computed in `refresh_risk.py`.
- Regime: table `sector_regime` (one row per sector, overwritten daily), computed in `refresh_regime.py`
  from the panel it already reads.
- Freshness: the hole rule covers sector indices (§5). `sector_regime` gets an age rule and a floor.
- Dashboard: a Risk tab "Sector" group and a Market page "Sectors" table (§6).

**Out (log in SUGGESTIONS.md):**
- Sector *history* charts and breadth history per sector. This version shows the latest day only, which
  also avoids applying today's classification to the past.
- Sector-relative returns in validation studies (an industry control for the event studies). It's a natural
  next use but changes existing studies, so it goes through the backfill ledger.
- **DB size follow-up:** `filings` is 99 MB and grows ~9 MB/month, which puts the 300 MB warn line about two
  months out. Archive filings to the bucket sooner than 24 months, as its own piece of work.

## 2. Definitions

### 2.1 Mapping — `data/sector_map.csv` (proposed; the owner edits this table in review)

The key is `company_snapshot.industry`, NSE's own classification (~58 values). We don't key on
`companies.industry`, which mixes NSE macro-sectors and sectors and is too coarse. A stock with no snapshot
row gets no sector (NIFTY 500 only).

`primary` is the closest sector index. `fallback` is used whenever the primary has fewer than 250 sessions of
history, so a new index (Capital Goods, Power, Cement…) takes over by itself once it is a year old. Neither
column may be NIFTY 500 except where both are, for Diversified. In the file, NIFTY 500 is written `^CRSLDX`,
its stored symbol.

| NSE industry (company_snapshot.industry) | primary | fallback |
|---|---|---|
| Banks | Nifty Bank | Nifty Financial Services |
| Finance; Financial Technology (Fintech) | Nifty Financial Services Ex-Bank | Nifty Financial Services |
| Capital Markets | Nifty Capital Markets | Nifty Financial Services |
| Insurance | Nifty Insurance | Nifty Financial Services |
| IT - Software; IT - Services; IT - Hardware | Nifty IT | Nifty IT |
| Pharmaceuticals & Biotechnology | Nifty Pharma | Nifty Healthcare Index |
| Healthcare Services; Healthcare Equipment & Supplies | Nifty Healthcare Index | Nifty Pharma |
| Agricultural Food & other Products; Food Products; Beverages; Household Products; Personal Products; Diversified FMCG; Cigarettes & Tobacco Products | Nifty FMCG | Nifty FMCG |
| Automobiles; Auto Components; Agricultural, Commercial & Construction Vehicles | Nifty Auto | Nifty Auto |
| Ferrous Metals; Non - Ferrous Metals; Minerals & Mining; Metals & Minerals Trading; Diversified Metals | Nifty Metal | Nifty Metal |
| Realty | Nifty Realty | Nifty Realty |
| Oil; Petroleum Products; Gas; Consumable Fuels | Nifty Oil & Gas | Nifty Energy |
| Power; Other Utilities | Nifty Power | Nifty Energy |
| Media; Entertainment; Printing & Publication | Nifty Media | Nifty Media |
| Consumer Durables | Nifty Consumer Durables | Nifty India Consumption |
| Textiles & Apparels; Leisure Services; Retailing; Other Consumer Services | Nifty Consumer Services | Nifty India Consumption |
| Chemicals & Petrochemicals; Fertilizers & Agrochemicals | Nifty Chemicals | Nifty Commodities |
| Cement & Cement Products; Other Construction Materials; Paper, Forest & Jute Products | Nifty Cement | Nifty Commodities |
| Industrial Products; Industrial Manufacturing; Electrical Equipment | Nifty Capital Goods | Nifty India Manufacturing |
| Aerospace & Defense | Nifty India Defence | Nifty India Manufacturing |
| Construction | Nifty Construction | Nifty Infrastructure |
| Transport Services; Transport Infrastructure | Nifty Transportation & Logistics | Nifty Infrastructure |
| Commercial Services & Supplies; Engineering Services | Nifty Services Sector | Nifty Services Sector |
| Telecom - Services; Telecom -  Equipment & Accessories | Nifty Telecommunications | Nifty Infrastructure |
| Diversified | NIFTY 500 | NIFTY 500 |

The file has one row per industry (the semicolons above are for reading only), and NSE's exact strings,
including the double space in "Telecom -  Equipment".

First-file probe (2026-10-01). Since 2020: Bank, IT, Pharma, FMCG, Auto, Metal, Realty, Energy, Media, Financial
Services, PSU Bank, Private Bank, Infrastructure, Commodities, India Consumption, Services Sector. From 2021:
Healthcare Index, Consumer Durables, Oil & Gas. From 2022: India Manufacturing. From 2023: India Defence,
Transportation & Logistics, Financial Services Ex-Bank. From 2025: Capital Markets (Jan), Chemicals (Jul).
From 2026: Cement (Apr). Not yet in the April 2026 file: Capital Goods, Consumer Services, Telecommunications,
Power, Construction, Insurance. The builder records each index's actual first stored date.

### 2.2 Which index a stock uses (`sectors.pick_index`)

`primary` if it has ≥ `MIN_SECTOR_SESSIONS = 250` closes inside the risk window, else `fallback` if that does,
else NIFTY 500. The stored `sector_index` names the one actually used, so a switch is visible. Same rule for
the sector table's stock grouping.

### 2.3 Risk lens additions (`risk_metrics`, 4 nullable columns)

| Column | Definition |
|---|---|
| `sector_index` | the index used (§2.2); null when the stock has no industry |
| `beta_sector_1y` | `risk.beta_stats` of the stock's adjusted log returns against the sector index's, on the stock's own print dates, last 250. Same gates as `beta_1y` (≥ 120 aligned, not sparse, no blanking flag) |
| `corr_sector_1y` | Pearson of the same aligned returns |
| `sector_ret_3m` | the sector index's 63-session return to the same last date, shown next to the stock's `ret_3m` |

Null whenever the same metric against NIFTY 500 is null (the same flags apply).

### 2.4 Sector table (`sector_regime`, one row per sector index, overwritten daily)

Computed in `refresh_regime.py` for the last session, for each index that some stock maps to (after §2.2):

| Column | Definition |
|---|---|
| `index_name`, `as_of` | the index; its last close date |
| `close`, `dd` | close; `close / max(close since its first stored date) − 1` |
| `ret_1m`, `ret_3m` | 21 / 63-session returns (null when shorter) |
| `rel_3m` | `ret_3m − NIFTY 500 ret_3m` (simple difference, stated as such) |
| `n_stocks`, `pct_above_200` | the regime breadth universe's stocks mapped to it on the last date, and the share above their 200-DMA. Null share when `n_stocks < 5` |

## 3. Code

```python
# scanner/bhavcopy.py
def parse_index_closes(text: str, names: dict[str, str] | None = None) -> dict
    # names: {lowercase NSE name: stored index_symbol}; default = NSE_INDEX_NAMES (today's two benchmarks)

# scanner/sectors.py
MIN_SECTOR_SESSIONS = 250
def load_sector_map(path=...) -> dict[str, tuple[str, str]]        # industry -> (primary, fallback)
def load_sector_indices(path=...) -> dict[str, str]                 # lowercase NSE name / alias -> index_symbol
def pick_index(industry, sessions_by_index: dict[str, int]) -> str | None
def sector_rows(closes: dict[str, pd.Series], n500: pd.Series, states_last: dict, symbol_index: dict) -> list[dict]
```

`index_symbol` for a sector is the NSE name as published ("Nifty Bank"). It is readable, cannot collide with
the `^` Yahoo tickers, and its aliases live in `data/sector_indices.csv`. The `index_prices` column comment is
updated to match.

## 4. Schema (append to `db/schema.sql`; apply via the Supabase MCP)

```sql
alter table risk_metrics add column if not exists sector_index text;
alter table risk_metrics add column if not exists beta_sector_1y real;
alter table risk_metrics add column if not exists corr_sector_1y real
  check (corr_sector_1y is null or corr_sector_1y between -1 and 1);
alter table risk_metrics add column if not exists sector_ret_3m real;

create table if not exists sector_regime (
  index_name     text primary key,
  as_of          date not null,
  close          real not null check (close > 0),
  dd             real check (dd is null or (dd <= 0 and dd >= -1)),
  ret_1m real, ret_3m real, rel_3m real,
  n_stocks       integer not null check (n_stocks >= 0),
  pct_above_200  real check (pct_above_200 is null or pct_above_200 between 0 and 1),
  updated_at     timestamptz not null default now()
);
alter table sector_regime enable row level security;
create policy "anon read sector_regime" on sector_regime for select to anon using (true);
```

## 5. Loaders, schedule, freshness

- **Daily** (`refresh_prices.py`, existing step): after the benchmarks, for each session in the run, read that
  day's NSE file (the fallback may already have fetched it, so reuse the text) and store every configured
  index that passes `confirm_close` against its previous stored close. The first-ever close of an index is
  stored without a previous close, but only when its file date matches.
- **Backfill** `refresh_prices.py --sectors-only --from 2020-01-01 --to <yesterday>`, via `backfill.yml
  what=sector-indices`: one NSE file per bucket session (~1,680 files at the polite rate, ~15 min), then the
  same check per index, chained day to day. It prints per index: first date, rows stored, rows skipped (why).
- `refresh_risk.py` / `refresh_regime.py` read the sector closes from `index_prices` (one select per index,
  window only). No new daily step.
- **Freshness:** `HOLE_TABLES` gains `"sector_indices"`: every configured index with a stored row before the
  window must have a row on every session of the last 60. An index launched inside the window is checked from
  its first row. `sector_regime`: `TRADING_QUERIES` age 1, floor `min 15` rows.

## 6. Dashboard

- **Risk tab:** a fourth group, *Sector*: "Sector index" (name, plus "(fallback)" when §2.2 fell back), "Beta to
  sector", "Correlation to sector", "Sector 3m" with the stock's 3m as `sub`. The footer adds "sector:
  {index}".
- **Market page:** a "Sectors" section under the charts. A `DataTable` (sortable) with sector, off high, 1m,
  3m, vs NIFTY 500 (3m), % above 200-DMA, stocks, as of. Default sort is by name, **not** by return, so the
  page never presents a ranking. An `InfoPopover` says "Latest day only; sector membership is today's NSE
  classification; not a signal". A sector with `n_stocks < 5` shows its breadth as "—".
- No new dependencies; formatting via `format.js`; vitest for the pure helpers (a fallback label, the
  sector row shaping).

## 7. Tests (write first)

- `parse_index_closes` with a custom name map on the real fixture (adds e.g. "Nifty Bank" to the fixture);
  the default map unchanged; an alias resolves to the one symbol.
- `load_sector_map` / `load_sector_indices`: **every industry in the pinned list of 58 (§2.1) has a row**;
  every index named in the map is in `sector_indices.csv`; no duplicate aliases. A new NSE industry fails the
  test until it is mapped. The loader also prints any live industry with no row.
- `pick_index`: primary at ≥ 250 sessions; fallback below; NIFTY 500 when both are short; unknown industry →
  None.
- Sector closes in `refresh_prices`: the first close of an index needs only a matching date; later ones need
  `confirm_close`; a holiday copy is skipped; chained missing days (reuses `plan_fallback`).
- Risk: `beta_sector_1y` = 1.5 on a synthetic stock built as 1.5 × the sector; null under the same flags as
  `beta_1y`; `sector_index` records the fallback when the primary is short.
- `sector_rows`: dd / returns exact on a hand path; `rel_3m` = difference; `n_stocks < 5` → null share.
- Freshness: the sector hole rule ignores an index before its first row and fails on a gap after it.
- Schema rule test (dated tables have a rule) passes with `sector_regime`.

## 8. Docs

`CLAUDE.md`: a Sector indices bullet (source, map, fallback rule, where it shows), the data-sources line, a
decisions-log line (*sector = NSE industry → sector index via a reviewed map; latest-day sector table only; not
a rotation signal*). `SUGGESTIONS.md`: the §1 Out items, including the DB-size follow-up. `CANDIDATE_SIGNALS.md`:
one line, "sector momentum / rotation (drift; data now exists)", untested. A `learnings.json` entry only if the
build produces a lesson.

## 9. Commits

1. `test: sector map, index picking, sector rows` → 2. `feat: scanner/sectors.py + data/sector_*.csv` →
3. `feat: parse_index_closes takes a name map; sector closes in refresh_prices (+ backfill)` →
4. `feat: sector-relative risk columns` → 5. `feat: sector_regime table + freshness` →
6. `feat: Risk tab sector group, Market page sectors table` → 7. `docs: sector indices v1`.

## 10. Definition of done

- pytest green; dashboard lint / test / build green.
- Backfill on Actions: per-index first date and row count recorded; every stored close passed the check; the
  skipped list is reviewed (expected: none, or special sessions with an explained reason).
- Sanity: HDFCBANK → Nifty Bank, β ≈ 1 and correlation ≥ 0.7. TCS → Nifty IT, correlation ≥ 0.7. A Capital
  Goods name shows "Nifty India Manufacturing (fallback)". Nifty Bank `dd` matches a hand computation from NSE
  closes.
- The `refresh-daily` run passes `check_freshness.py` with the sector hole rule. DB size recorded before and
  after (expect +≈ 4 MB).
- Browser (headless Edge + 390 px iframe measure): the Risk tab sector group for HDFCBANK, the Market page
  sectors table, sorting by keyboard, no page-level horizontal scroll.
