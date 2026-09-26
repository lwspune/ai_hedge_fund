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

### Shrink the database (327 MB of the 500 MB free tier; warn line is 300 MB)

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

## Backfill ledger

Learnings that may apply to already-shipped work. Each needs a 360 + explicit go-ahead
before touching the shipped artifact.

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
