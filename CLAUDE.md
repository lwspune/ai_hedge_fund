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
falsified signal is never read as edge. Nine signals validated this way; two actionable edges
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
- **Persistence (P2)** — `scanner/db.py` (raw PostgREST, no ORM) + `db/schema.sql`
  (6 tables: scan_runs, candidates, buybacks, tenders, outcomes, **market_deals**). LIVE on
  Supabase `vgyujznnyuqbhswszzjv`. **RLS is ON**: anon key = read-only; **writes need the
  service-role key** in `.env` as `SUPABASE_SERVICE_KEY`. `scanner/track.py` = feedback CLI.
  Supabase MCP configured in `.mcp.json` for schema/admin.
- **Data warehouse** — `market_deals` holds 45k+ bulk/block deals (2024→); backfilled via
  `scripts/backfill_deals.py`, refreshed by the **`refresh-deals` edge function**
  (`supabase/functions/`, deployed via MCP) which scrapes today's NSE CSV server-side. NSE
  static CSVs + chittorgarh reach datacenter IPs, so edge functions can ingest. Prices stay
  as local parquet cache (too big for the free tier), NOT in Supabase.
- **Dashboard (P3)** — `dashboard/` (Vite + React + supabase-js, read-only). Verdict-aware
  views + **Deals view with a Refresh button** (calls the edge function); `signals.json`
  generated from `catalog.py` via `scripts/emit_signals_json.py`. Deployed on Vercel
  (https://ai-hedge-fund-gamma.vercel.app/). `npm run dev --prefix dashboard`.
  **Company search + `#/company/:symbol` page** (hash-routed, no router dep): snapshot ratios,
  sector, events timeline, annual/quarterly results, shareholding, deals, signal activity.
- **Infra layer (I1–I5)** — the shared data spine every signal/backtest reads from:
  - **I1 company master** — `scanner/master.py` → `companies` (every NSE equity + historical
    delistings, industry, index membership, `is_financial`) + `symbol_changes`.
    `scripts/refresh_companies.py`.
  - **I2 price store** — `scanner/pricestore.get_closes(sym, start, end, source="yf"|"nse")`:
    one guarded parquet cache (`cache/px/`). **yf is split/bonus-adjusted — use `source="nse"`
    (unadjusted) for any premium vs a nominal rupee price.** Replaces per-script caches.
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

## Data sources (free, proven)
**Every source below works from datacenter IPs** — verified from a GitHub Actions runner
(`scripts/probe_sources.py`, workflow `probe-sources`), incl. nselib and screener.in. Only NSE's
JS-gated JSON endpoints (PIT/insider, ASM/GSM) block.
- **Prices** — yfinance (`.NS`, split-adjusted) primary; **nselib** for historical /
  delisted symbols and unadjusted closes (filter `Series=='EQ'`!); jugaad-data fallback.
- **Fundamentals** — screener.in company pages (consolidated vs standalone: take the one with
  the later quarter — consolidated sometimes silently stops updating).
- **Company master** — NSE static `EQUITY_L.csv` (mainboard) + Emerge `SME_EQUITY_L.csv`
  (underscored headers, 2-digit years), `symbolchange.csv` (headerless),
  `delisted.csv` (stale, ~2020); niftyindices `ind_*list.csv` for industry + membership.
- **Corporate actions** — nselib `corporate_actions_for_equity`. **F&O ban** —
  `nsearchives.../archives/fo/sec_ban/fo_secban_DDMMYYYY.csv`. **IPOs** — chittorgarh
  `/ipo/x/<id>/` (Next.js payload keys, e.g. `timetable_anchor_lockin_end_dt_1`).
  **ASM/GSM** — JSON-gated, not available.
- **Bulk/block deals** — NSE **static archive CSVs** (`nsearchives.../bulk.csv`,
  `block.csv`). NSE's JSON APIs (PIT/insider/historical) are JS-gated → empty/503; the
  static CSVs are the way in.
- **Buybacks** — chittorgarh detail pages by id (`/buyback/x/<id>/`); list page is
  JS-rendered (not scrapable), so enumerate ids. Symbol is in `nseCode` (double-escaped).
  **chittorgarh 307-redirects unknown ids** to a listing page that contains the marker text —
  always fetch with `allow_redirects=False` / `redirect: "manual"` or the gap-stop never fires.

## Run
`python -m pytest` (163 tests) · `python -m scanner.run --list` ·
`python -m scanner.run buyback_arb [--save]` · `python -m scanner.track buybacks|tender|outcome` ·
`npm run dev --prefix dashboard` (dashboard). One-offs: `scripts/backfill_deals.py`,
`scripts/seed_buybacks.py`, `scripts/emit_signals_json.py`,
`scripts/validate_index_rebalance.py [--nifty50]`, `scripts/segment_index_rebalance.py`.
**Scheduled refresh runs on GitHub Actions — no laptop needed** (`.github/workflows/`):
`refresh-daily` (weekdays 20:30 IST: corporate actions, F&O bans, IPOs + 120-day re-check,
10-day deals refill, buyback scan) and `refresh-weekly` (Sun 10:00 IST: company master +
fundamentals; `smoke` input for a 5-company test). Both call `scripts/scheduled_refresh.py`;
secrets `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` live in repo Actions secrets; a failed step
fails the run → GitHub emails the owner; the last step `scripts/check_freshness.py` also fails
the run if any table's newest row is older than its cadence (catches loaders that "succeed" while
writing nothing). **CI** (`ci.yml`): pytest + dashboard lint/build on every push.
Manual: `gh workflow run refresh-daily.yml`.
Individual loaders: `scripts/refresh_companies.py` · `scripts/refresh_events.py actions|fo-ban|ipos` ·
`scripts/refresh_fundamentals.py [--symbols A,B] [--stale-days 7]` · `scripts/refill_deals.py --from`
· `scripts/validate_lockin.py` · `scripts/rebuild_snapshot_history.py` (no re-scrape).

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
- **2026-06-24** — Prices stay as parquet cache; deals warehoused in Supabase. *Reason:* persist
  what's hard to re-acquire (NSE serves only today's deal CSV); cache the regenerable (prices,
  ~100MB+ would blow the 500MB free tier).
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

## Conventions / Don'ts
- **TDD**: pure logic (signal math, arb math, parsers) is tested before implementation.
- **No silent bad data**: every scrape/price path needs sanity guards (we hit warrant
  series mis-picks, delisted-ticker garbage, 246% "premiums"). Guard, don't surface.
- Don't trade a `null`/`thin` signal as if it were edge. Don't restart drift signals.
- Schema + edge-function changes go through the Supabase MCP; keep `db/schema.sql` and
  `supabase/functions/` in sync with the live project. Anon key is read-only (RLS) — never
  put the service-role key in any `VITE_` var / client bundle.
- Persist data that's hard to re-acquire (deals → Supabase); keep regenerable data as cache
  (prices → parquet, not Supabase — free-tier size).
