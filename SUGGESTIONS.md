# Suggestions

A running list of actionable improvements surfaced during /update-docs runs.
Each item is outside the scope of the work that surfaced it. Strike through when done.

---

## 2026-06-24

### Calibrate the buyback acceptance prior from the outcomes feedback loop — **PARTIAL 2026-06-24**

Shipped the buildable parts (commit: issue-size feature in `estimate_acceptance` + `calibrate_from_outcomes`
harness + `scanner.calibrate` CLI). The actual *fit* is still gated on logging real tenders/outcomes
(0 rows). Once ~10–20 outcomes exist, run `scanner.calibrate` and copy the suggested per-bucket means
into `_MCAP_ACCEPTANCE_PRIOR`. Original entry kept open below for that step.

`estimate_acceptance()` is a hardcoded heuristic prior (small-cap → 90%, large-cap →
entitlement floor). The whole point of the P2 `outcomes` table is to replace those
constants with *your realized acceptance ratios* — but it has 0 rows because no real
tenders are logged yet.

**Why:** until it's calibrated, the ranking metric (`exp_return`) rests on guessed
acceptance; a wrong prior mis-ranks candidates. This is the single biggest lever on the
primary signal's usefulness.

**How to apply:** log a few real tenders via `scanner.track tender/outcome`; once there
are ~10–20 outcomes, fit acceptance vs (market-cap bucket, entitlement, premium, issue-size)
and replace the constants in `_MCAP_ACCEPTANCE_PRIOR`. Add issue-size and retail-shareholding-%
as features (scrape from chittorgarh / screener) for a sharper estimate.

### ~~Buyback refresh-from-UI (mirror the deals pattern)~~ — **DONE 2026-06-24**
Shipped: `refresh-buybacks` edge function (`supabase/functions/`, regex chittorgarh probe + Yahoo price)
+ a Refresh button on the dashboard Buyback panel. Original spec below.

Deals now refresh from the dashboard via the `refresh-deals` edge function. Buybacks only
refresh via the CLI (`scanner.run buyback_arb --save`).

**Why:** consistency + the buyback signal is the *primary* edge — it deserves the same
one-click refresh. The pattern is proven (chittorgarh reaches datacenter IPs).

**How to apply:** add a `refresh-buybacks` edge function (port `scan_current_buybacks`'s
discovery + scoring to Deno, or have it call out) writing to `buybacks`; add a Refresh
button on the Buyback panel. Note: it also needs prices (yfinance) + market cap (screener)
from the edge runtime — verify those reach datacenter IPs first (deals only needed NSE).

### ~~Automate the daily refresh~~ — **DONE 2026-06-24 (deals)**
Shipped: pg_cron job `refresh-deals-daily` (33 14 * * 1-5 UTC ≈ 20:03 IST) calls the refresh-deals
edge function via pg_net. Buyback refresh isn't scheduled yet (infrequent — manual button is fine);
add a weekly cron for `refresh-buybacks` if wanted. Original spec below.

Refresh is currently manual (button / CLI). The warehouse goes stale between clicks.

**Why:** a market-intel tool should wake up current. Bulk/block deals publish daily ~7pm IST.

**How to apply:** schedule `refresh-deals` via Supabase `pg_cron` + `pg_net` (call the edge
function on a cron), or a GitHub Action, or Windows Task Scheduler hitting the function URL.
~7:30pm IST on trading days.

### Default the buyback scan to OPEN-window buybacks only

`scan_current_buybacks` returns closed-window buybacks too (today it found 3, all closed).
There's an `only_open` flag but the CLI/dashboard show everything.

**Why:** the actionable set is buybacks whose tender window is still open; surfacing closed
ones is noise on the operational view.

**How to apply:** default `only_open=True` for the live `scanner.run buyback_arb` surface
(keep all for `--save`/history), or add an OPEN filter toggle in the dashboard Buyback panel.

### ~~Finish the Vercel cutover to `main` + delete stale `master`~~ — **DONE 2026-09-24**

Code was pushed to `main`; the remote still has an old `master` and Vercel's production
branch may still point at it.

**Why:** the deployed dashboard won't get new commits until production tracks `main`.

**How to apply:** GitHub → set default branch to `main`; Vercel → Settings → Git →
Production Branch = `main`, redeploy; then delete `master` once production is confirmed.

### ~~Rotate the credentials pasted in chat~~ — **DECLINED 2026-09-24** (user: ignore; don't raise again)

Five secrets were pasted into the assistant chat on 2026-06-23/24: GitHub PAT, Supabase
access token, anon key, service-role key.

**Why:** they live in the transcript. The service-role key = full DB access.

**How to apply:** revoke the GitHub PAT; regenerate the Supabase access token (update
`.mcp.json`); rotate the project JWT secret to kill the anon+service_role keys, then update
`.env` (service-role) + the Vercel `VITE_SUPABASE_ANON_KEY` + redeploy.

### ~~Add a Decisions log to CLAUDE.md~~ — **DONE 2026-06-24**
Shipped: `## Decisions log` in CLAUDE.md with 7 dated decisions + reasons. Original spec below.

The "why" behind key choices (structural-edge thesis, prices-as-cache, RLS read-only +
service-role writes, edge-functions-reach-datacenter-IPs) is currently scattered across
prose and `CONCLUSIONS.md`.

**Why:** a dated Decisions log makes the rationale recallable and prevents re-litigating
settled calls.

**How to apply:** add a `## Decisions log` section to CLAUDE.md with one dated line per
decision + a one-clause reason.

### ~~Commit the index-rebalance validation work~~ — **DONE 2026-09-23**

The signal #1 work is complete and tests pass (82) but is uncommitted: `CANDIDATE_SIGNALS.md`,
`scanner/rebalance.py`, `tests/test_rebalance.py`, `data/next50_rebalance_events.csv`,
`scripts/validate_index_rebalance.py`, `scripts/segment_index_rebalance.py`, plus the null
registration in `scanner/catalog.py` / `tests/test_catalog.py` / `CONCLUSIONS.md` / CLAUDE.md.

**Why:** a clean, atomic commit captures the null verdict + its evidence before the working
tree drifts; the curated Next-50 event set (151 events from primary niftyindices PDFs) is
expensive to reproduce and worth preserving in history.

**How to apply:** one `feat:`/`docs:` commit, e.g. `feat: validate index_rebalance (null, n=151 Next 50) + signal backlog`.
Note the Next-50 CSV is the auditable record — keep it in the commit.

### ~~Test candidate signal #2 — lock-in expiry overhang~~ — **DONE 2026-09-24** (conditional lens; CONCLUSIONS §6)

`CANDIDATE_SIGNALS.md` #2 (anchor / pre-IPO lock-in expiry → forced supply, short side) is the
recommended next test. Unlike index rebalancing, lock-in expiries aren't a 4-week-pre-announced
trade everyone front-runs, so the structural thesis doesn't pre-doom it.

**Why:** it's the next-highest-value 🟢 structural/forced-flow candidate, and the harness +
event-set curation pattern from signal #1 (primary-source dates, pure leg math, TDD, segment
before trusting) ports directly.

**How to apply:** build the event set (IPO listing date → 30/90-day anchor + 6-mo pre-IPO
lock-in dates, from chittorgarh/prospectuses), reuse `scanner.eventstudy` + the `rebalance.py`
date-to-date math, run short-side abnormal return around expiry, then segment before any verdict.

## 2026-09-24 (infra layer)

### ~~Backfill the market_deals gap (2026-09-12 → 2026-09-23) and keep the project awake~~ — **DONE 2026-09-24** (refilled Jan–Sep 2026 via `scripts/refill_deals.py`; daily GitHub Actions writes + 10-day refill keep it whole and the project awake)

The `refresh-deals-daily` pg_cron job's last run was 2026-09-11 although it is still active —
consistent with the free-tier project being paused for inactivity (pausing stops pg_cron).
NSE's static CSV only serves *today*, so those days are missing from `market_deals`.

**Why:** a warehouse with silent holes misleads any deals-based study.

**How to apply:** backfill the gap with nselib `bulk_deal_data` / `block_deals_data` for the date
range (same normaliser as `scripts/backfill_deals.py`); then either upgrade the plan or add a
keep-alive (e.g. a GitHub Action pinging the REST API a few times a week).

### ~~Schedule the infra refreshes~~ — **DONE 2026-09-24** (GitHub Actions `refresh-daily` / `refresh-weekly`; no laptop)

`refresh_companies.py`, `refresh_events.py actions|fo-ban|ipos` and `refresh_fundamentals.py`
are manual. nselib + screener need the residential IP, so cloud cron can't run them.

**Why:** the company page and events calendar go stale without a cadence.

**How to apply:** Windows Task Scheduler — events (actions + fo-ban + ipos) daily after 8pm IST;
companies + fundamentals weekly (fundamentals takes hours: default `--stale-days 7`).

### ~~ASM/GSM surveillance lists (backlog signal #5)~~ — **DONE 2026-09-24** (JSON `api/reportASM|GSM` works from runners — the static CSVs were the dead path; `surveillance_daily` snapshot captured every trading day since 2026-09-24; the study needs ~6-12 months of entries/exits)

Not ingested: NSE serves them only via JS-gated JSON. ~~**How to apply:** probe BSE's equivalents
or a headless-browser fetch before testing signal #5.~~ **Re-probed 2026-09-24** (DATA_INFRA_SPEC):
the static `asm_list.csv` / `gsm_list.csv` still 404 — parked; only a headless browser remains.

---

## 2026-09-24 (data-infra gap closure, DATA_INFRA_SPEC WP1-WP8)

### Surface upcoming tender buybacks before the record date

**Finding:** the scanner only accepts a buyback once chittorgarh publishes the entitlement ratio,
which typically appears with the letter of offer — *after* the record date, i.e. after the last
day to buy. On 2026-09-24, Global Pet Industries (id 248, record date 2026-09-25) and VRL
Logistics (id 241) were live tender offers the scan rejected for "no ratio". The Desk "Act" panel
therefore shows buybacks when it is already too late to enter.

**Why:** the edge is captured by buying before the record date; a ratio-less upcoming tender is
the most actionable row, not a reject.

**How to apply:** keep a `pending_ratio` row (price, record date, issue size, % of equity) with
an acceptance estimate from the size/mcap prior and a floor of the typical 15%-reservation ratio
(**2026-09-24:** `buyback.estimate_entitlement` now derives that floor from the `shareholding`
small-shareholder float — the pending-ratio row can carry a real estimate, not a typical value);
list it on the Desk as "upcoming — ratio not yet published". Needs a spec (it changes what the
primary signal surfaces).

### Store RE series in the price store

`daily_prices` keeps equity series only; rights entitlements trade as their own symbols/series in
the same bhavcopy (`E1`, `RR`, `-RE` symbols). The raw month parquet in the `prices` bucket already
has them. **How to apply:** point `scanner/rights.fetch_re_frame` at the bucket/raw frame instead
of nselib, so `rights_re` has no per-symbol network fetch.

### Re-run every verdict on Actions to replace the laptop baselines

WP7 stored the 2026-09-24 laptop results as baselines; `validate.yml` can now re-run each study on
a runner with provenance. **How to apply:** dispatch `validate.yml` per script once the price
backfill is complete; update each CONCLUSIONS evidence line to the new path.

### ~~Shrink the database (327 MB of the 500 MB free tier; warn line is 300 MB)~~ — **DONE 2026-09-30** (options 1 + 2: `idx_events_symbol_type_date` dropped, `idx_filings_category_time` → partial on the extractor categories, `daily_prices` window 730 → 400 d + `VACUUM FULL`; the DB had reached 370 MB. After: `daily_prices` 169 → 80 MB (heap 56, pkey 24), database 370 → 274 MB (`db_size_bytes` 287 MB, under the 300 MB warn line). Decision logged in CLAUDE.md; test pins `KEEP_DAYS`.)

**Finding (2026-09-24, live `pg_total_relation_size`):** `daily_prices` 162 MB (98 heap + 65 pkey,
1.41 M rows, already at the full 730-day window so flat), `filings` 93 MB (67 + 26, 186 k rows,
+~19 k rows / ~27 MB a year), `corporate_events` 30 MB (15 heap + 15 index across five btrees),
`market_deals` 15 MB, everything else ~11 MB. Buckets are a separate quota (prices 148 MB).
Untouched, the 400 MB fail line arrives in ~2.5 years; filings is the only fast grower.

Where the bytes go: the price pkey on `(symbol text, trade_date)` is ~44 MB at 90% fill but 65 MB
live (daily inserts scatter across the key space, leaves ~65% full); SME series SM/ST/SZ are 203 k
rows (14%). In `filings`, `attachment_url` is 17 MB with a constant 43-byte
`https://nsearchives.nseindia.com/corporate/` prefix on 99% of rows (~8 MB), `company` + `isin`
duplicate `companies` (~7 MB), `category` text repeats 39 values (6.5 MB), the
`(category, disclosed_at)` index is 12 MB and has been scanned 8 times, and two categories nothing
reads ("Outcome of Board Meeting" 35 k rows, "Disclosure under SEBI Takeover Regulations" 12 k) are
a quarter of the table. `idx_events_symbol_type_date` (4.8 MB) duplicates the prefix of the
unique key on `corporate_events`.

**Options, by MB per unit of effort:**
1. **Index cleanup, ~30 MB, no policy change** — drop `idx_events_symbol_type_date`; replace
   `idx_filings_category_time` with a partial index on the four KPI categories (`extract_kpis`
   `KPI_FILTER` + `validate_order_wins`); `REINDEX INDEX CONCURRENTLY daily_prices_pkey` once
   (regrows slowly — add it to the weekly `--prune` step). Gets under the warn line on its own.
2. **Shrink the price table window, ~70 MB, one constant** — `pricestore.get_bars` already reads
   dates before `_table_floor()` from the bucket, so the table is a hot cache. `KEEP_DAYS` 730 →
   400 drops ~45% of the table; cost is a few more ~1.8 MB month parquets per validation on Actions.
   Alternative or addition: drop SME series from the table (~23 MB; the bucket keeps them).
   *Supersedes the 2026-09-24 "2-year table" decision — needs a go-ahead.*
3. **Normalise `filings`, ~30 MB, medium effort** — store only the URL suffix, drop `company` /
   `isin` (join `companies`), `category` → small lookup; compatibility view; edits in
   `CompanyPage.jsx`, `extract_kpis.py`, `validate_order_wins.py`, `archive_filings.py`. Only
   when filings becomes the constraint.
4. **Stop ingesting the two unread categories, ~25 MB now + ~7 MB/yr** — policy call; the
   company page's filings tab would list fewer rows.

**Recommendation:** 1 + 2 (400-day window). Small, reversible, data model unchanged; keeps the DB
flat near ~230 MB on current sources. Bump `check_freshness` thresholds only if the window changes
the `prices` row floor (it doesn't — the floor is per-day).

---

## 2026-09-27 (Learnings page)

### ~~Top bar overflows at phone width (every page)~~ — **DONE 2026-09-27** (≤ 640 px the nav scrolls sideways; measured page scroll width 415 → 375 px on a 375 px viewport, Signals / Learnings / Courses / company)

At 390 px the top bar (nav + company search + freshness dot) is wider than the screen, so every page
scrolls sideways and the search box and freshness dot sit off-screen. Seen on Signals before the
Learnings link was added (headless Edge, 390×700); the 2026-09-26 company-page overflow is probably
the same cause. Fix: collapse the search to an icon button below ~640 px, or let the nav scroll.

### CONCLUSIONS.md header and "Open / next" are stale — **header fixed 2026-09-27** (with the buyback downgrade); "Open / next" still to rewrite

The status line still says "Eleven signals validated" (the tally below says 21), and "Open / next"
lists P2 / P3, both built on 2026-06-24. Rewrite the header to the current tally and replace "Open /
next" with a pointer to `CANDIDATE_SIGNALS.md`. Docs only.

## 2026-09-30 (Risk lens v1 built — v2 backlog, docs/RISK_LENS_SPEC.md §1)

Out of scope for v1 by design; each is a separate piece of work. Measurements, not signals — none
of them may become a ranking.

### ~~Backfill the price-store hole 2026-09-01 → 09-09 (and index 2026-01-01)~~ — **DONE 2026-09-30** (`backfill.yml what=prices` run 36736724513: 7 sessions, ~3,400 rows each, bucket month 21 days; Yahoo has no ^CRSLDX 2026-01-01, so that one close — 23,909.55 — came from NSE's `content/indices/ind_close_all_01012026.csv`, consistent with both stored neighbours; `price_break` 64 → 36)

**Found building the risk lens:** seven trading sessions (Sep 1-4, 7-9) are missing from the bucket
month `bhav/2026-09.parquet`, from `daily_prices` and from `index_prices`; `index_prices ^CRSLDX` also
lacks 2026-01-01. Every consumer reads a move across the hole as one session (the risk lens flags a
>30% "day" as `price_break`; the consolidation scan's 40-session ranges straddle it).
**How to apply:** `gh workflow run backfill.yml -f what=prices -f from=2026-09-01 -f to=2026-09-09`
(and the index day), then re-run `refresh_risk.py`. `refresh_risk.py` prints a WARN listing the
missing sessions until it is filled.

### Basket / candidate-list risk

Concentration of the Act list by industry, cap bucket (`pointintime.mcap_bucket_at`) and shared
event week. Reads `risk_metrics` + `companies`; no new data.

### Stress test / scenario repricing

Reprice a basket over the worst historical NIFTY 500 weeks since 2020 using each name's beta and
realised moves. Needs the basket first.

### Market regime view

Index drawdown, breadth (share of the universe above its 200-DMA from `bar_panel`), volatility
regime. A Desk strip, not a signal.

### Industry-relative beta and correlation

Needs sector index closes; `index_prices` holds only ^NSEI and ^CRSLDX. Add the niftyindices sector
series to the index loader first.

### Implied volatility (F&O bhavcopy)

Shares the F&O bhavcopy ingestion with backlog #24 (results-day IV vs realised move).

### Risk history

A time series of the metrics (bucket parquet per month, not a table — the DB budget). Lets the
Risk tab show "vol now vs its own past".

## 2026-09-30 (Market regime v1 built — v2 backlog, docs/REGIME_VIEW_SPEC.md §1)

### Sector breadth / rotation

Needs sector index closes (niftyindices sector series) in `index_prices`; then breadth per sector and a
rotation view. `index_prices` holds ^NSEI and ^CRSLDX only.

### Breadth by cap bucket

Large / mid / small breadth via `pointintime.mcap_bucket_at` as of each date — heavy per date; cache the
bucket per stock per quarter first.

### FII / DII flows, India VIX, NSE advance-decline

New sources (NSE participant-wise OI / FII-DII provisional data, VIX history); probe runner reachability first.

## Backfill ledger

Learnings that may apply to already-shipped work. Each needs a 360 + explicit go-ahead
before touching the shipped artifact.

### `refresh_prices.refresh_indices` trusts Yahoo alone — it misses special sessions — **awaiting go-ahead**

**Learning (market regime, 2026-09-30):** Yahoo had no NIFTY 500 close for 13 NSE sessions since 2020 (Muhurat
2020-11-14 / 2023-11-12, Budget 2020-02-01 / 2025-02-01 / 2026-02-01, the 2024 Saturday DR sessions, several
1 Jan / 26 Dec days) and NIFTY 50 for 7. All were filled by hand from NSE `content/indices/ind_close_all_DDMMYYYY.csv`
(each checked: previous stored close + NSE's change = NSE's close). **360:** scope — `refresh_indices` (daily +
backfills) · blast radius — only fills days that are missing; Yahoo stays primary · really applies — yes, the
freshness hole rule will now fail the run on the next such session and someone fills it by hand · risk — low
(the archive is static, proven reachable; keep the neighbour check as the guard) · cost — ~30 lines + a parser
test on a fixture · **recommendation: do** — after Yahoo, fetch the NSE file for every bhavcopy session in the
window without an index row.

### ~~`pricestore.adjust_for_actions` rejects a split and a bonus on the same ex-date~~ — **DONE 2026-09-30** (owner go-ahead: same-date factors multiply, the guard checks the product; all 8 symbols now verified; `validate_investor_skill.py` may gain a few events on its next re-run — verdict null either way)

**Learning (risk lens, 2026-09-30):** each action is checked against the observed jump on its own,
so a combined split + bonus (AHCL, BESTAGRO, BHARATRAS, DELPHIFX, FCL, NAZARA, RNBDENIMS, SILVERTUC —
8 of 3,157 in the first run) fails both checks and returns None. **360:** scope — one function, used
by every study that spans an action and by the risk lens · blast radius — studies would *gain* events
they now drop; no number that exists today changes sign · really applies — yes, these are real
combined actions · risk — low, reversible; the guard stays (compare the product of same-date factors
to the jump) · cost — ~20 lines + tests · **recommendation: do** (then re-run any study whose n
changes).

### ~~`check_freshness.py` can't see holes inside a table~~ — **DONE 2026-09-30** (owner go-ahead, after the backfill: `HOLE_TABLES` — every trading day in the last 60 must have `daily_prices` rows (RPC `price_dates`) and ^CRSLDX / ^NSEI `index_prices` rows; live check 0 / 0 / 0. Yahoo's index gaps (it lacked ^CRSLDX 2026-01-01) will now fail the run — NSE's `ind_close_all_DDMMYYYY.csv` is the fallback source if that recurs)

**Learning:** the 2026-09-01..09 price hole passed every freshness rule (the newest row is fresh,
the 2-day floor is full). **360:** scope — one new rule (trading days in the last ~60 with no
`index_prices` / `daily_prices` rows) · blast radius — the daily run fails until the backfill above is
done · really applies — yes; the loader already guards "newest", not "complete" · risk — low ·
cost — small · **recommendation: do, after the backfill** (else it fails every run meanwhile).

### Studies assume every split / bonus / demerger is in `corporate_events` — **defer**

**Learning:** ~2% of symbols show a one-session move outside every NSE price band with no recorded
action (mostly SME boards, demerger parents); the risk lens blanks them (`price_break`).
`adjust_for_actions` only guards actions it is told about. **360:** scope — validation scripts on
`source="db"` closes across long windows · really applies — weakly: studies use medians over short
windows and most exclude SME, so a few fake jumps barely move a median; the lever is the same
`price_break` test as a drop rule · **recommendation: defer**; apply when a study is next re-run.

### ~~`estimate_acceptance` ignores the offer premium — the strongest pre-record predictor of acceptance~~ — **DONE 2026-09-30** (owner go-ahead: `PREMIUM_BAND_ACCEPTANCE` 100 / 83 / 38 / 33 / 12% is the live prior whenever the premium is known; flat 45% + size nudge kept only as the no-price fallback; `scanner.calibrate` prints realized vs prior by band — 101 tenders reproduce it; verdict unchanged, thin / watch)

**Study done 2026-09-30** (`scripts/validate_buyback_selection.py`, CONCLUSIONS §3 addendum, n=97): the
premium predicts acceptance (Spearman −0.62 vs +0.06 for the flat prior) but not the return — after-tax
medians by band ≤5% −0.2% (n=5) · 5–10% **+4.1%** (n=15, both eras, t_cl 4.2) · 10–20% +2.1% · 20–40%
+6.2% · >40% −0.7%; blind +2.9%. Not monotonic, one point over blind at best → **verdict stays thin**.
**Awaiting go-ahead:** swap the flat 45% prior for the band medians in `estimate_acceptance`
(100 / 83 / 38 / 33 / 12%), so the scan's `ACC~` and `EXP~` columns and the alert ranking reflect the
data. Ranking accuracy only; no promotion; ~2 h with tests + `scanner.calibrate` by band.

**Learning (hand-entry of the 65 scanned response tables + 13 missing ones, 2026-09-27):** with 101
realized small-shareholder acceptances (was 24), market cap barely separates them (small 49%, small-mid
43%, mid 47%, large 61% on n=13). The buyback price over the **last cum-entitlement close** does
(Spearman −0.63, n=100): premium ≤ 5% → median 100%, 5-10% → 83%, 10-20% → 38%, 20-40% → 34%,
> 40% → 12%. Same direction before and after Oct-2024. It is known before the record date, unlike
chittorgarh's entitlement ratio (ρ 0.67, but published after it). Scratch analysis only — no study yet.

**360:**
- *Scope:* `buyback.estimate_acceptance` (mcap + size heuristic, flat 45% prior), `scanner.calibrate`
  (buckets by mcap), the live scan's `exp_return` ranking, CONCLUSIONS §3 "choosing them in advance
  isn't proven yet" — the re-promotion condition of the 2026-09-27 downgrade.
- *Blast radius:* ranking + alert text of the live scan; possibly the signal's verdict.
- *Does it really apply?* Only half-proven: high acceptance comes **with** a small premium, so it may
  not raise expected return (acceptance × premium). Needs the selection-rule test (premium band at the
  last cum close → after-tax return, by era, clustered) before any model change.
- *Risk / reversibility:* study is read-only; a model change is a small, reversible commit with tests.
- *Cost:* study ~half a day; model + calibrate change ~2 h after it.
- *Recommendation:* **do the study first**; change the model only if a premium band shows positive
  after-tax return in both eras.

### ~~`refresh_buyback_results` stores the wrong filing for ~1 in 7 tenders~~ — **DONE 2026-09-30** (every newspaper copy in the window is tried, post-buyback-subject copies first, closure letters last; window 45 → 75 d; tokenizer reads `211 .04`; tests in `test_buyback_results.py`; historical rows untouched)

**Learning (same session):** 9 of 65 `needs_manual` pointers were extinguishment certificates
("Closure of Buy Back"), not the response table. `is_result_announcement` accepts a "Copy of Newspaper
Publication" only when its *subject* says post-buyback, but most companies file it with the generic
subject — so the closure letter wins. Two tenders (Dhampur 2025, HGS 2023) also had the announcement
outside the close→+45 d window; 17 tenders had no row at all (13 found by hand). About 10 of the 65
"scans" had a text layer the parser failed on (e.g. `211 .04` with a stray space, columnar layouts).

**360:**
- *Scope:* `buyback_results.is_result_announcement` / `pick_result`, the loader window, `_solve`
  tokenizer.
- *Blast radius:* future tenders only — all 101 historical rows are now filled (64 by hand,
  `parsed_by='manual'`, never retried).
- *Does it really apply?* Yes for new tenders: ~1 in 7 will land on a closure letter and stay
  `needs_manual` though a readable table exists.
- *Risk / reversibility:* low; parser fixtures from the PDFs read today.
- *Cost:* ~1-2 h with tests.
- *Recommendation:* **do** — try every newspaper copy in the window (the arithmetic check already
  rejects non-tables), rank closure letters last, tolerate a space before a decimal.

### ~~`buyback_arb` taxes 2026 tenders under the retired deemed-dividend rule (Finance Act 2026)~~ — **DONE 2026-09-27** (`tax_regime` + `post_apr2026`, payment proxied from the close; study re-run n=101: 3× +2.4% after tax, floor −2.3%; verdict text updated in catalog / alerts / dashboard / CONCLUSIONS §3; verdict label left for the owner)

**Learning (course research, 2026-09-27):** for any buyback on or after **1 Apr 2026**, a non-promoter's
proceeds are taxed as **capital gains** (buyback price − cost; STCG 20% under 12 months), not as a deemed
dividend at slab rate with the cost as a capital loss (the Oct-2024 rule). Promoters pay extra (22% / 30%
effective). Source: Vinod Kothari Consultants, Feb 2026; Finance Act 2026.

**360.**
- *Scope:* `buyback.after_tax_return` has only `pre_oct2024` / `post_oct2024`; `expected_after_tax` picks
  `post_oct2024` for every record date ≥ 2024-10-01, so the live scan's `exp_return` for every 2026 tender
  is computed under the wrong law. Also CONCLUSIONS §3's tax-slab tables, the catalog verdict text
  ("actionable only from a ≤5%-slab account"), `signalLabels.js`, the Learnings / course copy, and the
  Telegram alert text if it quotes a slab.
- *Blast radius:* the primary signal's verdict. Under the new rule the arb gain on the accepted shares is
  taxed at a flat 20% and the unaccepted remainder's loss is a normal short-term loss — no slab
  dependence. The "≤5% slab only" condition may simply disappear (both better for high-slab accounts and
  worse for ≤5%-slab ones than before). Nothing breaks; the numbers shown are wrong.
- *Does it really apply?* Yes for live tenders (record dates since Apr 2026). The historical study
  (2020 → Mar 2026) is right to use the old regimes for past events; only the forward-looking verdict and
  live `exp_return` need the third regime. Open point: whether "on or after 1 Apr 2026" keys on the offer,
  record or payment date — check the Act's text before coding the cut-over.
- *Risk / reversibility:* low. A third regime `post_apr2026` + cut-over date, tests first; revert by
  reverting the commit. Re-run §3 on Actions to restate the after-tax table per regime.
- *Cost:* ~half a day incl. tests, re-validation and verdict text.
- *Recommendation:* **do**, soon: it is the one signal we act on, and alerts fire on it.

### ~~`parse_shp_xbrl` reads pre-Oct-2025 SHP filings 100x too high (and misses MF %)~~ — **DONE 2026-09-27** (unit read per filing from the whole-pattern row; 2020/2022 member aliases; 2020 DII = Institutions − FPI − FVCI; old "pledged or otherwise encumbered" not stored as pledge, only its `false` → 0; fixtures `shp_2020_taxonomy.xml` / `shp_2022_taxonomy.xml`; live check 4 companies × 3 taxonomies = master promoter %)

**Learning (investor_skill, 2026-09-26):** the SHP XBRL taxonomy changed units. Filings on the 2025-10-31
taxonomy carry fractions (0.7448 = 74.48%); the 2020-09-30 and 2022-09-30 taxonomies carry percent
(74.99 = 74.99%). `parse_shp_xbrl` always multiplies by 100, so an old filing reads promoter 7499%, public
2501%, small-holder 361%, FPI 796%, pledge likewise; and the old taxonomy's MF member
(`MutualFundsOrUti…`) is not in `_PCT_MEMBERS`, so `mf_pct` is None. Verified on 13 companies × 3
taxonomies (scratch run). The new holder parser avoids it by computing % = shares / total shares.
**Impact today:** small — `shareholding` holds 4,465 rows, all 2025+ except ~34, and those 34 read
sane (they were revised filings on the new taxonomy). **The trap:** `backfill.yml what=shareholding
from=2020-01-01` would write thousands of 100x rows, and `buyback.estimate_entitlement` reads
`small_holder_pct` (only the latest quarter, so live buyback math is safe today). **360:** scope = two
lines in `_pct` (unit from the total-shares context: ≈100 → percent, ≈1 → fraction) + one member alias;
blast radius = `shareholding` rows written from then on + the dashboard shareholding chart;
does-it-apply = yes, reproduced; risk = low, reversible (re-run the backfill); cost ≈ 30 min with a
2021-taxonomy fixture test. **Recommendation: do**, before anyone runs the shareholding backfill; add a
freshness/sanity rule `promoter_pct <= 100`. *(At fix time: the live table already had `check (… between 0 and
100)` on every % column, so the backfill would have failed its batches, not stored 100x rows — no new rule
needed. The 2020 taxonomy also lacked small-holder / DII / FPI under the new member names, and pledge was a
different quantity — both handled.)*

### ~~`extract_kpis.py --limit 1500` silently gets 1000 (PostgREST row cap)~~ — **DONE 2026-09-26** (`db.select_all(..., max_rows=)` stops paging at the limit; both extractors use it; tests `test_extract_kpis.py`, `test_db.py`; live work list 1500)

**Learning (credit-ratings backfill, 2026-09-26):** a single `db.select(..., limit=N)` returns at
most 1000 rows whatever N is; the ratings backfill asked for 15000 and processed 1000. Fixed there by
`db.select_all(...)[:limit]` (test `tests/test_extract_ratings.py`). `extract_kpis.pending` has the
same shape: the daily `--limit 1500` step reads 1000. **Impact:** throughput only — 37,457 KPI filings
pending on 2026-09-26 clear in ~37 weekdays instead of ~25; nothing is wrong or lost. **360:** scope =
one function; blast radius = the daily job's runtime (+~50% PDFs/day, still well inside the timeout);
reversible; cost minutes. **Recommendation:** do — same one-line fix + the same test.

### ~~`buyback_arb` study entered at the record-day close (= ex-entitlement price)~~ — **DONE 2026-09-24** (entry moved to the last cum close via `buyback.last_buy_close`; CONCLUSIONS §3 re-tabled; verdict narrowed)

**Learning (backtest review, 2026-09-24):** under T+1 settlement the record date is the ex-date;
a buyer must own the shares the session before. `validate_buyback_arb.py` entered at the
record-day close, and stocks drop a median ~2.5% that day (n=105), so the study booked the
entitlement's own value as premium. Any record-date study (demerger, rights, dividend) has the
same trap — the convention now lives in `last_buy_close` / `last_buy_date` and is what the
demerger study must use.

**360:**
- *Scope:* the study script; CONCLUSIONS §3; the catalog verdict/summary; the live scan's
  `is_open` (kept a tender in Act after its record date) + the alert text (no last buy day).
- *Blast radius:* the primary signal's evidence; the Desk "Act" list; Telegram alerts.
- *Does it really apply:* yes to every event (T+1 from 2023-01-27; T+2 two sessions before).
- *Risk / reversibility:* re-run is read-only; text + verdict change; reversible.
- *Cost:* small (pure helper + tests, one script line, scan flag, alert line).
- *Recommendation:* **do** — done.

### ~~`index_rebalance` study had no corporate-action guard (BEL 2:1 bonus inside its Sep-2022 window = −66%)~~ — **DONE 2026-09-24** (`rebalance.drop_blocked` in both scripts; CONCLUSIONS §5 re-tabled)

**Learning:** the rebalance scripts read unadjusted nselib closes but, unlike every 2020+ study,
never applied `blocking_action`. One bonus inside a wide window moved the adds mean by ~0.9pp.
The tight (forced-flow) window was clean, so the null verdict stood; the published wide-window
number was wrong. Also: events of one review share dates, so the iid t was overstated — the
summary now carries a cluster-robust t (`summarize(..., clusters=)`).

### ~~`buyback_arb` validation compares a nominal buyback price to split-adjusted entry prices~~ — **DONE 2026-09-24** (re-run on unadjusted NSE closes, n=81; verdict holds, new tax-slab condition — CONCLUSIONS §3)

**Learning:** yfinance closes are split/bonus-adjusted backwards, so any "premium vs a nominal
price" (buyback price, open-offer price, delisting floor) is wrong for stocks that later split or
issued bonuses. Re-running `scripts/validate_buyback_arb.py` through the new price store shows
it: SPORTKING premium +1282% (1:10 split), GPIL +568%, GARFIBRES +477%, WIPRO/BSE bonuses; mean
premium +76% vs median +28%. The old run *also* lost 29 of 77 events to cached-empty Yahoo
fetches (n=48 recorded vs 77 now).

**360:**
- *Scope:* `scripts/validate_buyback_arb.py` (entry/post prices), CONCLUSIONS §buyback table,
  possibly `validate_merger_arb.py` / open-offer (nselib = unadjusted → likely fine; verify).
- *Blast radius:* the evidence behind the platform's **only** "conditional edge" verdict; the
  live scanner's current-price premium is unaffected (no split between price and record date).
- *Does it really apply:* yes for every event with a later split/bonus (≥5 of 77 visibly).
  Direction: inflates gross mean; median much less; after-tax post-Oct-2024 already negative.
- *Risk / reversibility:* re-running is read-only; only CONCLUSIONS text changes. Reversible.
- *Cost:* small — switch entry/post prices to `get_closes(sym, source="nse")` (unadjusted EQ),
  add a premium sanity guard (e.g. drop |premium| > 150%, as the edge function already does),
  re-run, update the table.
- *Recommendation:* **do** — the primary signal's evidence should be reproducible; expect the
  verdict ("conditional edge on high-acceptance small-caps, post-Oct-2024 tax kills the floor")
  to survive, with smaller gross numbers.

### ~~`buyback_arb` verdict: re-run on the cloud store with 2026 events and as-of market caps~~ — **DONE 2026-09-24** (CONCLUSIONS §3 table updated to n=101; readings hold)

**Learning (WP1/WP3/WP5):** the study's event list was a laptop scrape of ids 90-225 under the old
page format, and it had no market-cap cut. The `buybacks` table now holds 106 tenders incl. 23 from
2026 (the format fix), prices come from the unadjusted cloud store, and `mcap_bucket_at` gives the
cap as of the record date. `scripts/validate_buyback_arb.py` was switched to all three.

**360:**
- *Scope:* CONCLUSIONS §3 table (n=81) and the acceptance-prior discussion.
- *Blast radius:* the primary signal's evidence; the live scanner is unaffected.
- *Does it really apply:* yes — n grows by the 2026 events; the new as-of mcap cut is the first
  direct test of the prior's buckets (was lookahead-free only by omission).
- *Risk / reversibility:* read-only re-run; CONCLUSIONS text only. Reversible.
- *Cost:* one `validate.yml` dispatch (script=validate_buyback_arb.py) after the price backfill.
- *Recommendation:* **do**, then decide whether §3's numbers change; the verdict is expected to
  hold (the thesis is structural, not sample-dependent).

**Re-run done 2026-09-24 on Actions** (`evidence/buyback_arb/2026-09-24T073004Z`), n=101 (was 81):
gross floor median **−0.21%** (was +0.4%), 3× entitlement median **+4.94%** (was +5.4%), 30%-slab
after-tax 3× median −0.84% (was −1.5%); post-Oct-2024 floor median −0.27% (n=35). By as-of mcap
at *floor* acceptance: small −1.41% (n=26), small_mid −0.58%, mid +1.66%, large +6.14% (n=14) —
floor acceptance is not how small-caps earn (their edge is near-100% acceptance), so this cut does
not test the prior; outcome data still does. **Decided:** §3 updated to n=101 (user, 2026-09-24).
Verdict reading unchanged (blind ≈ break-even; selection + low slab).

### ~~`buybacks.status` is wrong for scan-discovered rows~~ — **DONE 2026-09-24** (RPC `upsert_buybacks` derives open/settled, keeps tendered/skipped, settles closed windows; both writers use it; `record_tender` marks `tendered`; 23 rows corrected; status check constraint)

**Learning (WP1 browser check):** the Python scan upserts buybacks without `status`, so every row it
creates keeps the default `'open'` — the Data → Buybacks view lists all 23 closed 2026 tenders as
"Open". The `refresh-buybacks` edge function does set `open`/`settled` from `close_date`, but it
upserts that over any `tendered`/`skipped` you set by hand via `scanner.track`.

**360:**
- *Scope:* `scanner/db.buyback_row` (no status), edge fn `refresh-buybacks` (status clobber), the
  Data view's status filter. The Desk "Act" panel is unaffected (it reads `payload.is_open`).
- *Blast radius:* display + the manual tender log; no signal math.
- *Does it really apply:* yes — seen live (PVRINOX closed 17 Sep, shown Open).
- *Risk / reversibility:* low; a status derived only when the stored one is `open`/`settled`.
- *Cost:* small — derive status in both writers but never overwrite `tendered`/`skipped` (an
  RPC or a conditional update, since a plain upsert can't express "keep if manual"); one-off
  SQL to settle rows with `close_date < today`.
- *Recommendation:* **do**, with your go-ahead (touches the manual tender log's semantics).

### Company renames broke the `companies` upsert (unique ISIN) — **FIXED in WP4**, check history

A renamed symbol's new row carries the old row's ISIN; the weekly upsert would 409 on it. WP4 frees
the ISIN on the old row. **Open question:** did any past weekly run fail or skip rows on this? The
Actions history showed green runs, so likely no rename landed since the first load — no backfill
needed unless a rename is found missing from `companies`.

### ~~Buyback id probe follows chittorgarh redirects~~ — **DONE 2026-09-24** (CLI + edge fn v4; scan now stops after 46 pages)

**Learning:** chittorgarh 307-redirects unknown ids to a listing page; `requests` follows it and
the page contains the marker text, so a missing id looks real. Fixed for IPOs
(`fetch_ipo(..., allow_redirects=False)`) after the scheduled IPO probe never stopped.

**360:**
- *Scope:* `scanner/buyback._fetch_page` (CLI discovery) and the `refresh-buybacks` edge
  function's `fetchPage` (Deno `fetch` also follows redirects).
- *Blast radius:* discovery only; results are correct because parsing rejects the listing page.
- *Does it really apply:* yes — `/buyback/x/9999/` → 307 → `/report/buyback/80/`.
- *Risk / reversibility:* one-line change each (`allow_redirects=False` / `redirect: "manual"`).
- *Cost:* the gap-stop (8) never fires, so every scan burns its hard cap (80 CLI / 60 edge-fn
  page fetches) — slower and less polite, not wrong.
- *Recommendation:* **do** (small, safe); redeploy the edge function.
