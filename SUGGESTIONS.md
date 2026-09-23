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

### Rotate the credentials pasted in chat

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

### Test candidate signal #2 — lock-in expiry overhang

`CANDIDATE_SIGNALS.md` #2 (anchor / pre-IPO lock-in expiry → forced supply, short side) is the
recommended next test. Unlike index rebalancing, lock-in expiries aren't a 4-week-pre-announced
trade everyone front-runs, so the structural thesis doesn't pre-doom it.

**Why:** it's the next-highest-value 🟢 structural/forced-flow candidate, and the harness +
event-set curation pattern from signal #1 (primary-source dates, pure leg math, TDD, segment
before trusting) ports directly.

**How to apply:** build the event set (IPO listing date → 30/90-day anchor + 6-mo pre-IPO
lock-in dates, from chittorgarh/prospectuses), reuse `scanner.eventstudy` + the `rebalance.py`
date-to-date math, run short-side abnormal return around expiry, then segment before any verdict.
