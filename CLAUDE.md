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
falsified signal is never read as edge. Eleven signals validated this way; two actionable edges
(buyback tender; rights-entitlement discount), plus one real-but-unshortable effect (anchor unlocks). See `CONCLUSIONS.md` for the evidence; `CANDIDATE_SIGNALS.md` is the backlog
of untested ideas, ordered by the thesis.

| Signal | Type | Verdict | Role |
|---|---|---|---|
| `buyback_arb` | structural | **conditional edge** | **primary (actionable)** |
| `merger_arb` | spread | thin | watch |
| `mean_reversion` | drift | **null** | lens (informational only) |
| `smart_money_deals` | drift | **null** | lens (informational only) |
| `open_offer_arb` | spread | **null** | documented control |
| `index_rebalance` | structural | **null** | lens (informational only) |
| `lockin_expiry` | structural | **conditional** | lens (avoid/exit rule — real dip, unshortable) |
| `fno_ban` | structural | **null** | lens (informational only) |
| `rights_re` | spread | **conditional** | watch (buy RE instead of stock — ~3% discount) |
| `promoter_buying` | drift | **null** | lens (decayed after 2023) |
| `order_wins` | drift | **null** | lens (priced on announcement day) |

**The through-line:** edge survives only where a *structural barrier excludes competitors*
(the buyback 15% small-shareholder reservation institutions are legally barred from). A
*publicly pre-announced* forced flow (index rebalancing) is arbitraged away just like a
drift signal — being structural isn't enough if everyone can see and front-run it.
Efficiently-priced spreads (merger arb) get competed to ~risk-free. Do **not** restart
drift-signal chasing.

## Architecture
- **Signal registry** — `scanner/catalog.py`: every signal + its `SignalMeta`
  (type/verdict/role) and a `run()`. The honesty layer.
- **Runner** — `scanner/run.py`: `python -m scanner.run --list` (all verdicts) or
  `python -m scanner.run <name>` (run one, behind its verdict banner).
- **Signal logic** — `signals.py` (RSI/200-DMA/quality), `deals.py` (bulk/block
  smart-money), `buyback.py` (chittorgarh scrape + id-probe discovery + tender-arb math +
  acceptance-estimation model + Oct-2024 tax), `universe.py` (NIFTY 50 + financials rule).
- **Validation harness** — `scanner/eventstudy.py` + `scripts/validate_*.py`: the
  event-study engine. Any new signal gets validated here *before* it's trusted.
  `scanner/rebalance.py` = index-rebalance leg math + Next-50 event loader (events in
  `data/next50_rebalance_events.csv`, curated from primary niftyindices PDFs);
  `scripts/segment_index_rebalance.py` = the liquidity/era segmentation falsifier.
- **Persistence (P2)** — `scanner/db.py` (raw PostgREST, no ORM; `count`, `rpc_all`) + `db/schema.sql`
  (the P2 core: scan_runs, candidates, buybacks, tenders, outcomes, **market_deals**; infra tables
  below). LIVE on
  Supabase `vgyujznnyuqbhswszzjv`. **RLS is ON**: anon key = read-only; **writes need the
  service-role key** in `.env` as `SUPABASE_SERVICE_KEY`. `scanner/track.py` = feedback CLI.
  Supabase MCP configured in `.mcp.json` for schema/admin.
- **Data warehouse** — `market_deals` holds 45k+ bulk/block deals (2024→); backfilled via
  `scripts/backfill_deals.py`, refreshed by the **`refresh-deals` edge function**
  (`supabase/functions/`, deployed via MCP) which scrapes today's NSE CSV server-side. NSE
  static CSVs + chittorgarh reach datacenter IPs, so edge functions can ingest. Prices live in
  the cloud price store (I2 below): a 2-year table + the full raw history in a Storage bucket.
- **Dashboard (P3)** — `dashboard/` (Vite + React + supabase-js, read-only, hash-routed, no
  router/UI kit). Views: **Desk** `#/` (freshness strip · Act: open buybacks from the latest scan's
  `payload.is_open` + rights entitlements · Avoid: anchor unlocks, 14 d), **Signals** `#/signals`
  (verdict table, expandable summary + latest published evidence path + recent runs), **Data** `#/data/deals|buybacks|positions|scans`
  (filterable; Refresh buttons call the edge functions), **Company** `#/company/:symbol/:tab`
  (sticky header; overview/financials/events/filings/deals tabs, each fetches only its data).
  Design tokens in `src/styles/tokens.css`, shared components in `src/components/ui/`, all
  formatting via `src/lib/format.js` (IST, en-IN). Spec: `docs/DASHBOARD_REDESIGN_SPEC.md`.
  `signals.json` generated from `catalog.py` via `scripts/emit_signals_json.py`; display copy in
  `src/lib/signalLabels.js` (a test fails if a signal lacks a label). Deployed on Vercel
  (https://ai-hedge-fund-gamma.vercel.app/). `npm run dev|test|lint --prefix dashboard`.
- **Infra layer (I1–I5)** — the shared data spine every signal/backtest reads from:
  - **I1 company master** — `scanner/master.py` → `companies` (every NSE equity + historical
    delistings, industry, index membership, `is_financial`) + `symbol_changes`.
    `scripts/refresh_companies.py`. Industry falls back to the screener sector
    (`industry_source`; 99.7% known). **Delisting by diff**: last week's listed symbols absent
    from EQUITY_L+SME become `delisted` (`delist_source='equity_l_diff'`), never deleted; a renamed
    symbol's old row gives up its (unique) ISIN first. Guards: truncated lists / > 50 delistings
    fail the run. `scripts/backfill_orphans.py` (RPC `orphan_symbols()`) gives symbols seen in
    filings/deals/events a delisted `manual` row.
  - **I2 price store** — `scanner/pricestore.get_closes(sym, start, end, *, source=...)`:
    **`source` is required.** `"db"` = the cloud store, UNADJUSTED: `daily_prices` (rolling 730 days
    of NSE bhavcopy, equity series, BRIN on date) + bucket `prices` `bhav/YYYY-MM.parquet` (every
    series/column, 2020→) + `index_prices` (^NSEI, ^CRSLDX); `get_bars` adds volume/turnover/
    delivery %. Loader `scanner/bhavcopy.py` + `scripts/refresh_prices.py` (daily, `--prune` weekly,
    backfill via `backfill.yml`). `"nse"` (nselib, unadjusted, pre-2020) and `"yf"` (adjusted — return
    studies only) keep the local cache `cache/px/`. **Never a premium vs a nominal price on "yf".**
    NSE quirks the loader handles: a holiday serves the previous session's file under the holiday's
    name (skipped via DATE1 check); some days are an .xlsx under the .csv name (2022-08-08).
  - **Calendar (WP6)** — `trading_calendar` (NSE holiday master for this + next year, weekly; past
    years derived from bhavcopy presence) + `scanner/trading_calendar.py` (trading-day math; not
    `calendar.py`, which would shadow the stdlib). `corporate_events` gains `results` /
    `board_meeting` (`nse_bm`, NSE `api/corporate-board-meetings`, 2020→) and `band_change`
    (`nse_band`). Every `validate_*.py` takes `--exclude-results-window N`.
  - **Point-in-time (WP5)** — `company_snapshot_history` (weekly copy of the snapshot's
    point-in-time fields) + `index_membership` intervals (weekly niftyindices diff + the curated
    Next-50 record); `scanner/pointintime.mcap_bucket_at(sym, date)` (history, else
    `fundamentals.historical_market_cap` from Equity Capital / face value × unadjusted close).
    Use it for any market-cap cut — today's cap is lookahead.
  - **Evidence (WP7)** — every `validate_*.py` runs through `scanner/validation.run`; `--publish`
    stores results + the printed report in the private `evidence` bucket
    (`<signal>/<UTC stamp>/`) + a `validation_runs` row (git SHA, args, summary). Run on Actions:
    `validate.yml`. The 2026-09-24 laptop results are each signal's baseline.
  - **I3 events calendar** — `scanner/events.py` → `corporate_events` (bonus/split/rights/
    dividend/buyback/demerger via nselib; F&O ban days; IPO listing + 30/90-day anchor
    lock-in expiries) + `ipos` + **`rights_issues`** (chittorgarh offer data: exact issue price,
    RE symbol — NSE RE symbols vary, e.g. `NDTVR`/`TILRR`/`SATIN-RE` — timetable incl. renunciation
    + application deadline, partly-paid flag). `scripts/refresh_events.py actions|fo-ban|ipos|rights`.
  - **I4 fundamentals** — `scanner/fundamentals.py` (`parse_company_page`, `pick_view`) → full
    statement history in `cache/fundamentals/<SYM>.parquet` (`load_statements`) + one
    `company_snapshot` row/company (ratios, D/E, shareholding, `history` jsonb). Statement
    parquet is also kept in the private Storage bucket `fundamentals` (the durable copy).
    `scripts/refresh_fundamentals.py` (~polite, hours for the full market; run weekly).
  - **I5** — the dashboard company page above.
  - **Filings (F1-F3)** — `scanner/filings.py` → `filings` (NSE corporate announcements, material
    categories only, PDF link; `scripts/refresh_filings.py`, daily). F2 analysis
    (`docs/FILINGS_KPI_ANALYSIS.md`) chose what to extract; `scanner/kpis.py` rule_v1 extracts
    order book, order-win value, current capacity utilisation and guidance *quotes* from filing
    PDFs (PyMuPDF text; every value keeps its exact quote + source filing) → `company_kpis`
    (`scripts/extract_kpis.py`, ≤1500 PDFs per daily run, floor 2024-01-01 — the backlog clears
    itself). Sector packs (financials, commodities) are the next extractors. Precision over recall:
    every false positive found by hand review becomes a regression test in `tests/test_kpis.py`.
    **Retention (WP8):** `scripts/archive_filings.py` (weekly) copies months older than 24 to bucket
    `filings` (YYYY-MM.parquet) then nulls `subject` — except rows extraction may still need.

## Data sources (free, proven)
**Every source below works from datacenter IPs** — verified from a GitHub Actions runner
(`scripts/probe_sources.py`, workflow `probe-sources`), incl. nselib and screener.in. Only NSE's
JS-gated JSON endpoints (PIT/insider, ASM/GSM) block.
- **Prices** — **NSE bhavcopy** `nsearchives.../products/content/sec_bhavdata_full_DDMMYYYY.csv`
  (all symbols, unadjusted, delivery %, archive back past 2019; the cloud store's source);
  yfinance (`.NS`, split-adjusted) for return studies + benchmarks; **nselib** for pre-2020 /
  per-symbol unadjusted closes (filter `Series=='EQ'`!).
- **Calendar** — NSE `api/holiday-master?type=trading` (CM segment, current year only),
  `api/corporate-board-meetings?index=equities&from_date=&to_date=` (results dates, 2020→),
  static `content/equities/eq_band_changes.csv`. Same Referer-session family as filings.
- **Fundamentals** — screener.in company pages (consolidated vs standalone: take the one with
  the later quarter — consolidated sometimes silently stops updating).
- **Company master** — NSE static `EQUITY_L.csv` (mainboard) + Emerge `SME_EQUITY_L.csv`
  (underscored headers, 2-digit years), `symbolchange.csv` (headerless),
  `delisted.csv` (stale, ~2020); niftyindices `ind_*list.csv` for industry + membership.
- **Corporate actions** — nselib `corporate_actions_for_equity`. **F&O ban** —
  `nsearchives.../archives/fo/sec_ban/fo_secban_DDMMYYYY.csv`. **IPOs** — chittorgarh
  `/ipo/x/<id>/` (Next.js payload keys, e.g. `timetable_anchor_lockin_end_dt_1`).
  **ASM/GSM** — JSON-gated, not available.
- **NSE JSON APIs that DO answer a plain session with a `Referer: https://www.nseindia.com/`**
  (even from GitHub runners): `api/corporate-announcements` (filings) and
  `api/corporate-sast-reg29` (promoter/insider acquisitions). `api/corporates-pit` returns empty.
- **Bulk/block deals** — NSE **static archive CSVs** (`nsearchives.../bulk.csv`,
  `block.csv`). NSE's JSON APIs (PIT/insider/historical) are JS-gated → empty/503; the
  static CSVs are the way in.
- **Buybacks** — chittorgarh detail pages by id (`/buyback/x/<id>/`); list page is
  JS-rendered (not scrapable), so enumerate ids. Symbol is in `nseCode` (double-escaped).
  **chittorgarh 307-redirects unknown ids** to a listing page that contains the marker text —
  always fetch with `allow_redirects=False` / `redirect: "manual"` or the gap-stop never fires.

## Run
`python -m pytest` (385 tests) · `python -m scanner.run --list` ·
`python -m scanner.run buyback_arb [--save]` · `python -m scanner.track buybacks|tender|outcome` ·
`npm run dev --prefix dashboard` · `npm test --prefix dashboard` (vitest). One-offs: `scripts/backfill_deals.py`,
`scripts/seed_buybacks.py`, `scripts/emit_signals_json.py`,
`scripts/validate_index_rebalance.py [--nifty50]`, `scripts/segment_index_rebalance.py`.
**Scheduled refresh runs on GitHub Actions — no laptop needed** (`.github/workflows/`):
`refresh-daily` (weekdays 20:30 IST: corporate actions, F&O bans, **bhavcopy prices**, IPOs +
120-day re-check, rights, board meetings/results, band changes, filings + KPIs, 10-day deals
refill, buyback + rights scans) and `refresh-weekly` (Sun 10:00 IST: trading calendar, price
prune, company master + index membership, fundamentals + snapshot history, filings archive;
`smoke` input for a 5-company test). Both call `scripts/scheduled_refresh.py`;
secrets `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` live in repo Actions secrets; a failed step
fails the run → GitHub emails the owner; the last step `scripts/check_freshness.py` also fails
the run on any **age** rule (calendar or trading days), **row-volume floor**, **ratio**
(industry known ≥ 95%), a stuck **buyback frontier** (no new id in 60 d, or a scan that saw ≥ 10
pages and parsed 0 tenders — the 2026 format change), or **DB size** (warn 300 MB, fail 400 MB via
RPC `db_size_bytes`). A test forces every dated table in `db/schema.sql` to carry a rule.
**CI** (`ci.yml`): pytest + dashboard lint/build on every push.
On demand (Actions, never the laptop): `backfill.yml` (`what=board-meetings|prices|orphans`,
`from`/`to`) · `validate.yml` (`script=validate_*.py`, `args`; publishes evidence) ·
`probe-sources.yml`. Manual: `gh workflow run refresh-daily.yml`.
Individual loaders: `scripts/refresh_companies.py` · `scripts/refresh_events.py
actions|fo-ban|ipos|rights|holidays|board-meetings|bands` · `scripts/refresh_prices.py [--date D |
--from A --to B | --prune]` · `scripts/refresh_fundamentals.py [--symbols A,B] [--stale-days 7]` ·
`scripts/refill_deals.py --from` · `scripts/archive_filings.py` · `scripts/backfill_orphans.py` ·
`scripts/rebuild_snapshot_history.py` (no re-scrape). Validations: `scripts/validate_*.py
[--exclude-results-window N] [--publish]`.

## Stack
Python · pandas · yfinance · nselib · jugaad-data · requests/bs4 · html5lib · pytest ·
Supabase (raw PostgREST, no ORM/SDK) · React + Vite + supabase-js (dashboard). P0–P3 built +
deployed (https://ai-hedge-fund-gamma.vercel.app/). `buyback_arb` now self-discovers current
buybacks (upward id probe from `db.max_buyback_id`) + ranks by an acceptance-estimation model
(`estimate_acceptance` heuristic prior → after-tax `exp_return`). Next: calibrate the acceptance
prior from the `outcomes` feedback loop; add issue-size / retail-% features.

## Decisions log
One dated line per non-obvious decision + the reason. Don't re-litigate without a new reason.
- **2026-06-23** — Repurposed the concluded `AI_Hedge_Fund` repo (old code deleted, snapshot
  `30f1f1e`) into this platform, rather than a fresh repo. *Reason:* clean slate, history kept.
- **2026-06-24** — Structural-edge thesis: only `buyback_arb` survived; drift signals are null,
  spreads thin. *Reason:* edge needs a barrier retail uniquely sits inside; everything else is
  arbitraged/competed away. → don't chase drift.
- **2026-06-24** — Free data stack, not Kite Connect. *Reason:* yfinance/nselib/screener/NSE-static
  CSVs/chittorgarh cover an EOD scanner; Kite's daily-TOTP + ₹500/mo buys nothing we need.
- **2026-06-24** — Supabase persistence, RLS **on** (anon read-only, service-role writes), raw
  PostgREST (no ORM). *Reason:* lets the public Vercel dashboard read safely while CLIs/edge
  functions write.
- **2026-06-24** — ~~Prices stay as parquet cache~~ (superseded 2026-09-24, see below); deals
  warehoused in Supabase. *Reason:* persist what's hard to re-acquire (NSE serves only today's
  deal CSV); cache the regenerable (prices, ~100MB+ would blow the 500MB free tier).
- **2026-06-24** — Refresh runs in Supabase **Edge Functions**. *Reason:* NSE static CSVs +
  chittorgarh serve datacenter IPs (probed), so cloud refresh works; only NSE's JSON APIs block.
- **2026-06-24** — Repo under `lwspune` (the machine's GitHub auth), not `vilasvshinde`.
  *Reason:* avoids a cross-account push 403; plain `git push` works.
- **2026-06-24** — `index_rebalance` front-run validated **null** (n=151 Next-50 events). The
  reconstitution is publicly pre-announced ~4wks out, so the forced flow is arbitraged before
  a follower can act; the lone deletion-rebound was a 2021-22 regime artifact (segmentation
  killed it). *Reason:* sharpens the thesis — a barrier must *exclude competitors*, not just
  exist; a known flow doesn't. Event sets curated from **primary niftyindices PDFs** (secondary
  aggregators garbled 2023); promotion/relegation excluded from Next-50 legs as confounded
  (net opposite-direction Nifty-50 flow).

- **2026-09-24** — Infra layer (company master, price store, events calendar, fundamentals,
  company page), screener-style not Tijori-style. *Reason:* makes each backlog signal cheap to
  test; Tijori's value is hand-extracted segment/KPI data no free source provides.
- **2026-09-24** — Full statement history stays local parquet; Supabase gets one
  `company_snapshot` row + compact `history` jsonb per company. *Reason:* ~2.5k companies ×
  every line item would eat the 500MB free tier; the dashboard only needs headline series.
- **2026-09-24** — Old `cache/prices/` abandoned for `cache/px/`. *Reason:* its MILLIS
  timestamps read back as 1970 under pandas 3 + fastparquet, and it cached failed fetches as
  empty forever (29 of 77 buyback events silently lost).

- **2026-09-24** — `lockin_expiry` = **conditional lens**, not a trade: the anchor-unlock dip is
  real (90d −1.25% T-1→T+2, t=−4.6; same-stock placebo ~0; holds 2022-26) but fresh IPOs are not in
  F&O, so retail can't short it. *Reason:* short-sale constraints keep arbitrageurs out *and* retail
  out → use it to avoid buying into / exit ahead of unlocks.
- **2026-09-24** — buyback_arb verdict now tax-slab conditional. *Reason:* re-validated on unadjusted
  prices (n=81): at a 30% slab the high-acceptance case is ~0 after tax; works at ≤20%.

- **2026-09-24** — Scheduled refresh on **GitHub Actions**, not the laptop or edge functions.
  *Reason:* every source (incl. nselib + screener) works from GitHub runners; Actions reuses the
  Python unchanged (edge functions would mean re-porting parsers to TS, with minutes-long caps);
  the public repo gets free minutes; failure emails come free; daily writes keep the free-tier
  Supabase project from pausing. Keepalive step defeats the 60-day idle schedule disable.

- **2026-09-24** — `fno_ban` reversal validated **null** (n=920 episodes, same-stock control).
  *Reason:* the ban only blocks fresh derivatives; the cash market stays open to all, so no one is
  fenced out — consistent with the thesis. Next structural candidate: delisting RBB (#3).

- **2026-09-24** — `rights_re` = **conditional / watch**: REs trade ~3.4% below S − issue price
  (non-penny liquid days, every era 2020-26). *Reason:* capturable without shorting only when you
  want or hold the stock; tiny capacity; friction barrier (institutions ignore REs, retail dumps).
- **2026-09-24** — Delisting RBB (#3) **parked**: no reachable free source of offers/outcomes
  (chittorgarh none, BSE 403, NSE gated). Revisit only as a manual-curation project.

- **2026-09-24** — Filing KPIs by **deterministic rules**, not an LLM API. *Reason:* the chosen
  metrics are formulaic; rules are free, testable and run unattended in CI; hard cases get
  in-session batches (Question_Bank's ingestion pattern). An API key only if measured recall fails.
- **2026-09-24** — `promoter_buying` (#7) validated **null (decayed)**: +60d median ~+5% in 2020-23,
  negative in 2024-26. *Reason:* public drift signal, same fate as deals/index rebalance.

- **2026-09-24** — Data-infra gap closure (`docs/DATA_INFRA_SPEC.md` WP1-8). **Prices now live in
  Supabase** (`daily_prices` 730 days + bucket `prices` full raw bhavcopy history 2020→), not a laptop
  parquet. *Reason:* the laptop must never be a dependency — every scan and validation runs on
  Actions; the 2-year table (~170 MB, BRIN not btree) fits the free tier next to the WP2 size guard.
- **2026-09-24** — Bhavcopy backfill floor **2020-01-01** (archive goes deeper); pre-2020 stays on
  nselib per symbol. *Reason:* bucket budget; every validated study starts 2020 or uses nselib.
- **2026-09-24** — `get_closes(..., source=)` is **required**. *Reason:* adjusted Yahoo closes
  silently used for a nominal-price premium already produced a "+1282%" buyback premium once.
- **2026-09-24** — Freshness = age + volume floors + ratios + buyback frontier + DB size, and every
  dated table must have a rule (test). *Reason:* the primary signal was silently blind for nine
  months (chittorgarh 2026 wording) while "newest row" checks stayed green.
- **2026-09-24** — `buyback_arb` §3 re-run on Actions at **n=101** (2026 tenders + cloud prices):
  floor median −0.2%, 3× +4.9%, 30%-slab 3× −0.8%, 20%-slab 3× +3.8%. *Reason:* reproducible evidence
  for the primary signal; verdict (selection + ≤20% slab) unchanged.
- **2026-09-24** — Evidence dirs are per run (`<signal>/<UTC stamp>/`), not per date. *Reason:* a
  same-day rerun must never overwrite evidence an earlier `validation_runs` row points at.
- **2026-09-24** — Old filings keep their row; only `subject` moves to the bucket after 24 months, and
  not while KPI extraction may still need it. *Reason:* `extract_kpis` selects call transcripts by
  subject; KPI FKs and dashboard counts need the rows.

## Conventions / Don'ts
- **TDD**: pure logic (signal math, arb math, parsers) is tested before implementation.
- **No silent bad data**: every scrape/price path needs sanity guards (we hit warrant
  series mis-picks, delisted-ticker garbage, 246% "premiums"). Guard, don't surface.
- Don't trade a `null`/`thin` signal as if it were edge. Don't restart drift signals.
- Schema + edge-function changes go through the Supabase MCP; keep `db/schema.sql` and
  `supabase/functions/` in sync with the live project. Anon key is read-only (RLS) — never
  put the service-role key in any `VITE_` var / client bundle.
- Persist data that's hard to re-acquire (deals → Supabase); bulk history goes to Storage buckets
  (prices, statements, filings archive, evidence); local parquet is a read-through cache only.
- Any market-cap cut in a study uses `pointintime.mcap_bucket_at` (as of the event date), and any
  premium vs a nominal price uses unadjusted closes (`source="db"` / `"nse"`).
