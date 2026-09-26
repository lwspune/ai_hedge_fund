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
falsified signal is never read as edge. Twenty-one signals validated this way; two actionable edges
(buyback tender; rights-entitlement discount), plus one real-but-unshortable effect (anchor unlocks). See `CONCLUSIONS.md` for the evidence; `CANDIDATE_SIGNALS.md` is the backlog
of untested ideas, ordered by the thesis.

| Signal | Type | Verdict | Role |
|---|---|---|---|
| `buyback_arb` | structural | **conditional edge (narrow)** | **primary (actionable only from a ≤5%-slab account, on selected tenders; thin at 20%, negative at 30%)** |
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
| `turn_of_month` | drift | **null** | documented control (2022-23 flicker, ~0 since) |
| `promoter_sells` | drift | **null** | lens (sign flips every era) |
| `pref_lockin` | structural | **null** | documented control (allottees aren't forced sellers) |
| `ofs_retail` | structural | **thin** | watch (OFS 10% retail quota: ~+2% by T+1 at the floor, n=26, one era; cut-off unrecorded) |
| `demerger_listing` | structural | **conditional** | lens (newly listed child −5.9% median in its first 5 sessions, n=64; holder dumping not index flow; unshortable; no recovery trade — don't buy a child in week 1) |
| `rating_change` | drift | **null** | lens (downgrades −0.3% on the filing, n=456, no drift; the fall came before — agencies follow the price; upgrade bump ≈ one round-trip cost) |
| `ipo_listing` | structural | **thin** | watch (retail-quota lottery: +1.6% per application pooled, ≈ ₹34 in 2025-26; skip ≤ 2× retail; pre-listing GMP predicts the open; don't buy after listing) |
| `ipo_unlock` | structural | **null** | lens (entry after the 6-month pre-IPO unlock: −13% median vs NIFTY 500 over 12 months, same as month 3 / 9; no unlock dip; below-issue stocks worst — don't buy new listings on weakness) |
| `consolidation` | drift | **null** | lens (tight 40-session range breakouts: +60d median −1.7% vs NIFTY 500, n=938, no better than any 40-day high; daily informational scan) |
| `customer_momentum` | drift | **null** | documented (pilot: suppliers co-move +1.0% on the customer's ≥5% day; next-day entry ~0 at +1/+5, +20d = placebo customer; 301 order-win links 2024-26) |

**The through-line:** edge survives only where a *structural barrier excludes competitors*
(the buyback 15% small-shareholder reservation institutions are legally barred from). A
*publicly pre-announced* forced flow (index rebalancing) is arbitraged away just like a
drift signal — being structural isn't enough if everyone can see and front-run it.
Efficiently-priced spreads (merger arb) get competed to ~risk-free.

**Signal types — each is judged by its own bar** (`catalog.TYPES`):
- **structural** — a rule forces a flow or reserves an allocation (buyback quota, lock-in, index
  add). Bar: is the flow really forced, and who else can take the other side?
- **spread** — two prices a contract ties together converge (merger, open offer, RE vs stock). Bar:
  spread vs deal-break probability, net of costs. A pair with *no* contract is a spread too, ranked lower.
- **drift** — slow digestion of public information (incl. liquidity provision / short-term
  reversal). No barrier required. Bar: net alpha after costs, beats own-momentum + industry +
  placebo controls, holds in every era. Drift ideas are fair game only with a named mechanism — the
  record so far is all null, so the bar is high, not a ban.
- **premium** — a compensated risk (value, quality, low-vol factors). Not a mispricing, so the event
  study is the wrong test. Bar: long-run net Sharpe and drawdown vs NIFTY 500 and vs the cheap factor
  ETF that already sells it.

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
- **Alerts** — `scanner/notify.py` (pure: which candidates alert + text) + `scripts/notify_telegram.py`
  (daily, after the scans): a newly open buyback tender or a `BUY RE` rights entitlement → one Telegram
  message, once per opportunity (`alerts_sent`, unique `(signal_name, alert_key)`; key recorded only after
  Telegram accepts). Secrets `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`; `--dry-run`, `--test`.
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
  (https://ai-hedge-fund-fawn.vercel.app/). `npm run dev|test|lint --prefix dashboard`.
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
  - **Review unlocks (2026-09-24, `docs/GITHUB_PROJECT_REVIEW.md`)** — four NSE feeds other repos
    proved reachable from runners: **`shareholding`** (`scanner/shareholding.py`, weekly + `backfill.yml
    what=shareholding`; quarterly SHP XBRL per symbol, 2020→: promoter/public/MF/DII/FPI %, promoter
    **pledge** as % of promoter holding and of total, and **`small_holder_pct`** — the ≤₹2 lakh float that
    is the buyback 15%-reservation denominator → `buyback.estimate_entitlement` fills the acceptance
    floor before the letter of offer; the scan records `est_entitlement` + `entitlement_source`);
    **`insider_trades`** (`scanner/insider.py` PIT parsers, daily; one row per disclosure with person
    category, Buy/Sell/Pledge, mode Market/ESOP/Gift/…; a *forward* feed — dated windows reach back only
    ~5 months, so backtests of sells use Reg 29); **`surveillance_daily`** (`scanner/surveillance.py`,
    daily ASM long/short-term + GSM snapshot; `asmTime` is the list-run date, so entries/exits exist only
    from 2026-09-24 on — backlog #5 becomes testable after ~6-12 months); **`pref_issues`** +
    corporate_events `pref_lockin_expiry` (`scanner/prefissues.py`, daily 45-day window + backfill
    2023→; the listing XBRL gives each lock-in tranche — 6 m non-promoter / 18 m promoter — and the
    ICDR 6-m default is flagged; study `scripts/validate_pref_lockin.py`).
  - **Buyback lifecycle (2026-09-24)** — `parse_buyback` keeps a **tender before its letter of offer**
    (entitlement `None`, `issue_type='tender'`); the scan fills the floor from the small-holder float
    (`entitlement_source='estimated'`, printed `31%~`) and treats no-close-date as OPEN — the record
    date is when you must buy, and chittorgarh's ratio only arrives after it (Global Pet id 248 was
    invisible the day before its record date). Market cap comes from `company_snapshot` when < 14 d
    old (`market_cap_for`), else screener. **Realized acceptance**: `scanner/buyback_results.py` solves
    the response table of each NSE *Post Buyback Public Announcement* (per-symbol
    `api/corporate-announcements`, reaches 2023) by arithmetic consistency (reserved × response % =
    tendered; column order and OCR noise vary) → `buyback_results` (`ss_acceptance`; `needs_manual`
    rows are newspaper scans → `python -m scanner.track result --buyback-id … --ss-reserved … --ss-tendered …`).
    `scripts/refresh_buyback_results.py [--all] [--retry-manual]` (daily, after the scan);
    `python -m scanner.calibrate` compares realized acceptance with `_MCAP_ACCEPTANCE_PRIOR`.
  - **IPO study (2026-09-26, #11)** — `ipos` gains subscription by category (`sub_retail/qib/nii/total`,
    `retail_shares_offered`, `lot_size`, `applications`; chittorgarh publishes the category split only for recent
    issues — older ones are behind its paywall, left alone) + `sub_retail_nse` (`scanner/ipobids.py`, NSE
    `api/ipo-bid-details`: NSE-platform bids only, ≈ 0.647 of the consolidated retail figure; mainboard only).
    `ipo_gmp` (`scanner/gmp.py`, investorgain `chr-gmp/x/<chittorgarh id>/` → its own page's `gmpData`: one GMP per
    day, kept to the issue's window; **before 2026 only the last ~3 post-close quotes exist**, so daily capture
    `scripts/refresh_gmp.py` is the only source of application-time GMP). `pricestore.first_bar` gives a session's
    OPEN from the bhavcopy months (the table keeps closes). Odds per application: `scanner/ipostudy.allot_prob`.
    Study `scripts/validate_ipo.py`; live lens `python -m scanner.run ipo_listing`. NSE listings only (BSE is
    unreachable from runners); REITs / InvITs excluded.
  - **Consolidation scan (2026-09-26)** — `scanner/consolidation.py`: a 40-session range ≤ 10% of price on
    ≥ ₹1 crore/day turnover, breakout = first close outside it; `pricestore.bar_panel(start, end)` builds every
    stock's OHLC + volume / delivery in one pass over the raw bhavcopy months. Company universe only (ETFs trade
    in EQ and liquid-fund ETFs look permanently "consolidated"). Daily `python -m scanner.run consolidation
    --save` → scan_runs/candidates. Study `scripts/validate_consolidation.py`.
  - **OFS events (#23)** — `scanner/ofs.py` → `ofs_events` (chittorgarh `/ofs/x/<id>/`, 2025→: floor,
    both days, share split, seller; cut-off is never populated there). `scripts/refresh_ofs.py`
    (daily id probe) · `scripts/validate_ofs_retail.py` · live `python -m scanner.run ofs_retail`.
  - **Filings (F1-F3)** — `scanner/filings.py` → `filings` (NSE corporate announcements, material
    categories only + the buyback lifecycle categories, PDF link; `scripts/refresh_filings.py`, daily). F2 analysis
    (`docs/FILINGS_KPI_ANALYSIS.md`) chose what to extract; `scanner/kpis.py` rule_v1 extracts
    order book, order-win value, current capacity utilisation and guidance *quotes* from filing
    PDFs (PyMuPDF text; every value keeps its exact quote + source filing) → `company_kpis`
    (`scripts/extract_kpis.py`, ≤1500 PDFs per daily run, floor 2024-01-01 — the backlog clears
    itself). Sector packs (financials, commodities) are the next extractors. Precision over recall:
    every false positive found by hand review becomes a regression test in `tests/test_kpis.py`.
    **Retention (WP8):** `scripts/archive_filings.py` (weekly) copies months older than 24 to bucket
    `filings` (YYYY-MM.parquet) then nulls `subject` — except rows extraction may still need.
  - **Credit ratings (2026-09-26)** — `scanner/ratings.py` rule_v1 reads each agency's rating from the
    NSE `Credit Rating*` filings (Reg 30; one `Credit Rating` category until Sep-2024, then `- New /
    - Revision / - Others`) → `credit_ratings` (one row per filing × agency × long/short term: grade,
    1-20 notch, outlook, watch, action, previous rating, exact quote) + view `current_credit_ratings`
    (latest per symbol/agency/term, withdrawals dropped). Domestic `[ICRA]AA-` / `CRISIL|Crisil` / `CARE`
    / `IND` / `ACUITE` / `BWR` / `IVR` prefixes; global Fitch / S&P / Moody's / JCR / CareEdge Global
    from the covering letter only, each on its own scale, capped at A-/A3 (an Indian issuer can't sit
    far above the sovereign — a better grade is a misread). First rating per agency+term wins (skips
    history/glossaries); "Current | Previous" columns give `prev_rating` (header order decides which
    is which); `(CE)`/`(SO)` paper and bracketed third parties ("Bank of India (BoI, CARE AA+ …)") are
    skipped. `scripts/extract_ratings.py` (daily, newest 500) marks the filing `ok` / `no_rating` (ESG
    scores, gradeless withdrawals, image-only PDFs, unparsed → review queue). Measured on 300 live
    filings: ~97% of text filings that state a rating are read; grades 40/40 + 22/22 on audit; known
    slips are secondary fields (an outlook written "The Outlook remains Stable", a short-term row
    taking the long-term verb). Dashboard: header "Credit rating" stat + Events-tab history.

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
  (even from GitHub runners, probed 2026-09-24): `api/corporate-announcements` (filings),
  `api/corporate-sast-reg29` (promoter/insider acquisitions), **`api/corporates-pit-gg`** (PIT insider
  filings + per-filing XBRL; `api/corporates-pit` *without* `-gg` is dead and always empty),
  `api/reportASM` / `api/reportGSM` (surveillance snapshots; send `Accept-Encoding: gzip, deflate` —
  no `br`), `api/corporate-share-holdings-master?symbol=` (+ SHP XBRL: small-shareholder %, pledge),
  `api/corporate-further-issues-pref|ri?index=FIPREFIP|FIPREFLS|FIRIIP` (preferential / rights
  issues; date windows filter on submission date; the pref listing list starts Mar-2023).
  `api/corporates-financial-results` returns only the latest quarter per window (no history).
- **BSE `api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w`** answers with `Referer` +
  `Origin: https://www.bseindia.com` from a residential IP only — **403 from GitHub runners**
  (`AnnGetData/w` is dead everywhere). Delisting RBB stays parked.
- **Bulk/block deals** — NSE **static archive CSVs** (`nsearchives.../bulk.csv`,
  `block.csv`). NSE's JSON APIs (PIT/insider/historical) are JS-gated → empty/503; the
  static CSVs are the way in.
- **Buybacks** — chittorgarh detail pages by id (`/buyback/x/<id>/`); list page is
  JS-rendered (not scrapable), so enumerate ids. Symbol is in `nseCode` (double-escaped).
  **chittorgarh 307-redirects unknown ids** to a listing page that contains the marker text —
  always fetch with `allow_redirects=False` / `redirect: "manual"` or the gap-stop never fires.

## Run
`python -m pytest` (682 tests) · `python -m scanner.run --list` ·
`python -m scanner.run buyback_arb [--save]` · `python -m scanner.track buybacks|tender|outcome` ·
`npm run dev --prefix dashboard` · `npm test --prefix dashboard` (vitest). One-offs: `scripts/backfill_deals.py`,
`scripts/seed_buybacks.py`, `scripts/emit_signals_json.py`,
`scripts/validate_index_rebalance.py [--nifty50]`, `scripts/segment_index_rebalance.py`.
**Scheduled refresh runs on GitHub Actions — no laptop needed** (`.github/workflows/`):
`refresh-daily` (weekdays 20:30 IST: corporate actions, F&O bans, **bhavcopy prices**, IPOs +
120-day re-check + GMP, rights, board meetings/results, band changes, ASM/GSM snapshot, PIT insider
filings, preferential issues, filings + KPIs + credit ratings, 10-day deals refill, buyback + rights scans, Telegram alerts) and
`refresh-weekly` (Sun 10:00 IST: trading calendar, price prune, company master + index membership,
fundamentals + snapshot history, shareholding/pledge (2 new quarters per symbol), filings archive;
`smoke` input for a 5-company test). Both call `scripts/scheduled_refresh.py`;
secrets `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` live in repo Actions secrets; a failed step
fails the run → GitHub emails the owner; the last step `scripts/check_freshness.py` also fails
the run on any **age** rule (calendar or trading days), **row-volume floor**, **ratio**
(industry known ≥ 95%), a stuck **buyback frontier** (no new id in 60 d, or a scan that saw ≥ 10
pages and parsed 0 tenders — the 2026 format change), or **DB size** (warn 300 MB, fail 400 MB via
RPC `db_size_bytes`). A test forces every dated table in `db/schema.sql` to carry a rule.
**CI** (`ci.yml`): pytest + dashboard lint/build on every push.
On demand (Actions, never the laptop): `backfill.yml` (`what=board-meetings|prices|orphans|shareholding|insider|pref-issues|credit-ratings|ipos|ipo-gmp|ipo-bids`,
`from`/`to`) · `validate.yml` (`script=validate_*.py`, `args`; publishes evidence) ·
`probe-sources.yml`. Manual: `gh workflow run refresh-daily.yml`.
Individual loaders: `scripts/refresh_companies.py` · `scripts/refresh_events.py
actions|fo-ban|ipos|rights|holidays|board-meetings|bands` · `scripts/refresh_prices.py [--date D |
--from A --to B | --prune]` · `scripts/refresh_fundamentals.py [--symbols A,B] [--stale-days 7]` ·
`scripts/refill_deals.py --from` · `scripts/archive_filings.py` · `scripts/backfill_orphans.py` ·
`scripts/extract_ratings.py [--limit N] [--since D]` · `scripts/refresh_gmp.py [--since D]` · `scripts/refresh_ipo_bids.py` · `scripts/refresh_filings.py --ratings-only --from --to` ·
`scripts/refresh_shareholding.py [--symbols] [--per-symbol N] [--xbrl-limit N]` · `scripts/refresh_insider.py
[--from --to | --all]` · `scripts/refresh_surveillance.py` · `scripts/refresh_prefissues.py [--from --to]` ·
`scripts/rebuild_snapshot_history.py` (no re-scrape) · `scripts/refresh_buyback_results.py [--all]
[--retry-manual]` · `scripts/refresh_ofs.py [--from 1]` · `python -m scanner.calibrate` ·
`python -m scanner.track results|result`. Validations: `scripts/validate_*.py
[--exclude-results-window N] [--publish]`.

## Stack
Python · pandas · yfinance · nselib · jugaad-data · requests/bs4 · html5lib · pytest ·
Supabase (raw PostgREST, no ORM/SDK) · React + Vite + supabase-js (dashboard). P0–P3 built +
deployed (https://ai-hedge-fund-fawn.vercel.app/). `buyback_arb` now self-discovers current
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

- **2026-09-24** — GitHub project review (`docs/GITHUB_PROJECT_REVIEW.md`): adopted **data, not
  strategies**. The star repos (TradingAgents, ai-hedge-fund, qlib, Vibe-Trading) are US LLM/ML drift
  machines; every honest Indian factor backtest on GitHub reaches our null. Three India data repos
  proved the NSE PIT `-gg`, ASM/GSM JSON, shareholding-master + SHP XBRL and further-issues endpoints
  from runners → ingested (shareholding, insider_trades, surveillance_daily, pref_issues). *Reason:*
  they unblock backlog #5/#8, a new structural candidate (pref lock-in expiry) and the buyback
  acceptance model's missing small-shareholder feature; no agent framework, no factor re-tests.
  Same-day verdicts: turn_of_month null, promoter_sells null (era-unstable), **pref_lockin null** —
  lock-in expiry is a forced flow only when the locked holder must exit (anchors), not for strategic
  allottees. Thesis refined, not broken.
- **2026-09-24** — BSE JSON stays out: 403 from GitHub runners (works only residential). *Reason:*
  the laptop must never be a dependency; delisting RBB remains parked.

- **2026-09-24** — A tender buyback is kept in the scan **before its letter of offer** (entitlement
  unknown → estimated from the small-holder float, OPEN until a close date exists). *Reason:* the
  ratio chittorgarh publishes arrives after the record date, i.e. after the only moment a buyer can
  act; the old rule hid Global Pet (record date T+1) and a live VRL Logistics tender.
- **2026-09-24** — Realized small-shareholder acceptance is read from NSE *Post Buyback Public
  Announcements* by **arithmetic solving** (reserved × response% = tendered), not fixed columns.
  *Reason:* the SEBI table's column order, wording and OCR quality vary per registrar; a pair that
  fails the arithmetic is dropped rather than stored. Newspaper-scan PDFs (≈60%) stay
  `needs_manual`; no OCR dependency in CI.
- **2026-09-24** — Acceptance prior is **flat 45%** (was 90% small-cap → 12% large-cap). *Reason:* 24
  published response tables show ~50% in every cap bucket (median 42%); the gradient was invented.
  Re-fit only via `scanner.calibrate` on more parsed/hand-entered results; the premium→acceptance
  link is the open question.
- **2026-09-24** — `ofs_retail` (#23) validated **thin / watch** (n=26, 2025-26, T+1 vs floor +1.9%
  median). *Reason:* a reservation exists but the clearing price is not the floor when the book is
  oversubscribed, and the source has no cut-off; one-day capital ≤ ₹2 lakh. Not a trade.

- **2026-09-24** — Telegram alerts for **new Act candidates only** (no digest, no failure pings —
  GitHub already emails those). Every open buyback alerts (not gated on `exp_return`): the verdict is
  tax-slab conditional, so the call stays manual. *Reason:* signal over noise; dedup is a DB constraint.

- **2026-09-24** — Backtest review: the buyback study now enters at the **last cum-entitlement
  close** (`buyback.last_buy_close`; T+1: record −1 session), not the record-day close, which is
  ex-entitlement (median −2.7% that day). Verdict narrowed: floor −2.3%, 3× +3.0% gross, 20%-slab
  +1.3%, ≤5%-slab +8-9% (n=101). `is_open` now also requires today ≤ `last_buy_date`; alerts carry
  it. Rebalance scripts gained the corporate-action guard (`rebalance.drop_blocked`; BEL bonus was a
  −66% "add"); `eventstudy.summarize(..., clusters=)` adds a cluster-robust t. *Reason:* every
  record-date study must price the last cum session; a null is robust to inflating biases, a
  positive is not — so the corrections concentrate on the signals we would act on.
- **2026-09-24** — `demerger_listing` (#10) = **conditional lens**: a newly listed child falls −5.9%
  median vs NIFTY 500 in its first 5 sessions (n=64, clustered t −2.8, placebo-clean, 2022-26
  stable), but the pre-specified mechanism cut fails (index-parent children −1.4% n.s.; small/
  non-index parents −6 to −10%), it is unshortable (T2T, no F&O) and the buy-after leg's median is
  negative. *Reason:* the seller is the parent's holder base dumping small allotments, not a
  mandate-bound institution; same lock-in pattern — the barrier that excludes arbitrageurs excludes
  retail. Event set is hand-curated (`data/demerger_listings.csv`, 27 of 90 records had no listed
  child); the child-listing mapping is the only part that needs upkeep.
- **2026-09-24** — Options strategies **declined** as a review; one falsification test logged as
  backlog #24 (results-day implied vol vs realised move, F&O bhavcopy needed). *Reason:* an option
  strategy is a payoff shape, not a barrier — nobody is excluded from NSE options, the premium is a
  competed tail-risk premium (beta, not alpha), SEBI 2024-25 raised the retail floor (~₹15 lakh lots),
  a lot is ~7× the ₹2 lakh buyback slab so it can't hedge our edge, and fresh listings aren't in F&O so
  puts can't short the unshortable lenses.
- **2026-09-26** — Credit ratings come from the **NSE rating filings we already index**, parsed by rule,
  not agency websites or NSDL. *Reason:* Reg 30 makes every listed company file every rating action, the
  PDFs have text layers (no OCR), one parser covers all agencies, and it runs in the daily job; agency
  sites would be one scraper each with unproven runner reachability. Ratings are **data / a lens**
  (credit health, avoid downgrades), not a signal: a rating change is public news, i.e. a drift signal —
  test it in the event-study harness before trusting any reaction to it.
- **2026-09-26** — `rating_change` validated **null** (CONCLUSIONS §17): downgrades n=456 move −0.3% on
  the filing (t −0.9) with no drift after, and the stock had already fallen (T−21→T−1 median −4.6% vs
  −3.2% for the same stock 120 sessions earlier); out-of-IG / default cuts n.s.; upgrades +0.6% vs
  +0.2–0.3% for reaffirmations and placebo, fading. Robust to a results-window exclusion. *Reason:* a
  public, lagging opinion — the agency reacts to what the price already showed. Ratings stay as data
  on the company page, not an alert or exit rule.
- **2026-09-26** — Four signal types (structural / spread / drift / **premium**), each with its own bar;
  a structural barrier is **no longer required** — measured net alpha is. *Reason:* the barrier was a
  finding about where edge survived, not a precondition; drift ideas with a named mechanism (customer
  momentum over a buyer–seller graph) are testable under the drift bar. Premium added because a factor
  can lose for years and still be real — the event-study harness would falsely reject it.
- **2026-09-26** — `customer_momentum` pilot **null** (CONCLUSIONS §21), first test under the drift bar:
  buyer→seller links from the SEBI order-win "entity awarding" field (`scanner/links.py`, exact name or
  curated alias only — abbreviation/substring matching made false links). 301 listed links, 806 events:
  same-day co-move +1.0%, next-day entry ~0, +20d +0.94% ≈ placebo customer +0.80%. *Reason:* the filing
  itself names the customer, so the link is public and priced at once. No 2020 free-text backfill; the
  graph stays evidence, not a table. Weight ≥ 25% hint (+1.6%, t 1.8) logged, not pursued.
- **2026-09-26** — `ipo_listing` validated **thin / watch** (CONCLUSIONS §18): the retail quota is a real
  barrier, capturable as a lottery — one mainboard application = P(allot) × listing gain = +1.6% (≈ ₹237)
  pooled but ≈ ₹34 in 2025-26 (n=416); ≤ 2× retail loses; buying after listing is null (median −10% at 1y);
  pre-listing GMP predicts the open (ρ 0.87). *Reason:* a barrier that lets retail in still gets competed
  down — more retail money per issue (odds fall as pops rise). GMP at application time is backlog #25
  (daily capture from 2026-09-26). Allotment odds for old issues come from NSE's retail bids ÷ 0.647, not
  from chittorgarh's paywalled figures.
- **2026-09-26** — `ipo_unlock` validated **null** (CONCLUSIONS §19): entering a new listing after its 6-month
  pre-IPO lock-in expiry returns −5.3% / −13.3% median vs NIFTY 500 over 6 / 12 months (n=900 unlocks), no
  better than month 3 or 9; the unlock itself −0.35% (n.s.); below-issue stocks worst. *Reason:* post-IPO
  underperformance runs ~18 months and pre-IPO holders aren't forced sellers (same as `pref_lockin`);
  "it has already fallen" is not a floor.
- **2026-09-26** — `consolidation` validated **null** (CONCLUSIONS §20): up-breakouts from a tight 40-session
  range return −0.7% / −1.7% median vs NIFTY 500 at +20 / +60 (n=938), no better than wide-range breakouts
  or the same stock earlier; every pre-set segment negative; down-breakouts only mark already-weak stocks.
  *Reason:* a public chart pattern with no barrier. Kept as a daily informational scan.

## Conventions / Don'ts
- **TDD**: pure logic (signal math, arb math, parsers) is tested before implementation.
- **No silent bad data**: every scrape/price path needs sanity guards (we hit warrant
  series mis-picks, delisted-ticker garbage, 246% "premiums"). Guard, don't surface.
- Don't trade a `null`/`thin` signal as if it were edge. A drift idea needs a named mechanism and
  must pass the drift bar above (controls + every era) — never re-test a falsified one without a new reason.
- Schema + edge-function changes go through the Supabase MCP; keep `db/schema.sql` and
  `supabase/functions/` in sync with the live project. Anon key is read-only (RLS) — never
  put the service-role key in any `VITE_` var / client bundle.
- Persist data that's hard to re-acquire (deals → Supabase); bulk history goes to Storage buckets
  (prices, statements, filings archive, evidence); local parquet is a read-through cache only.
- Any market-cap cut in a study uses `pointintime.mcap_bucket_at` (as of the event date), and any
  premium vs a nominal price uses unadjusted closes (`source="db"` / `"nse"`).
