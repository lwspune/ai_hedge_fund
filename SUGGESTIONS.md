# Suggestions

A running list of actionable improvements surfaced during /update-docs runs.
Each item is outside the scope of the work that surfaced it. Strike through when done.

---

## 2026-06-24

### Calibrate the buyback acceptance prior from the outcomes feedback loop

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

### Buyback refresh-from-UI (mirror the deals pattern)

Deals now refresh from the dashboard via the `refresh-deals` edge function. Buybacks only
refresh via the CLI (`scanner.run buyback_arb --save`).

**Why:** consistency + the buyback signal is the *primary* edge — it deserves the same
one-click refresh. The pattern is proven (chittorgarh reaches datacenter IPs).

**How to apply:** add a `refresh-buybacks` edge function (port `scan_current_buybacks`'s
discovery + scoring to Deno, or have it call out) writing to `buybacks`; add a Refresh
button on the Buyback panel. Note: it also needs prices (yfinance) + market cap (screener)
from the edge runtime — verify those reach datacenter IPs first (deals only needed NSE).

### Automate the daily refresh

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

### Finish the Vercel cutover to `main` + delete stale `master`

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

### Add a Decisions log to CLAUDE.md

The "why" behind key choices (structural-edge thesis, prices-as-cache, RLS read-only +
service-role writes, edge-functions-reach-datacenter-IPs) is currently scattered across
prose and `CONCLUSIONS.md`.

**Why:** a dated Decisions log makes the rationale recallable and prevents re-litigating
settled calls.

**How to apply:** add a `## Decisions log` section to CLAUDE.md with one dated line per
decision + a one-clause reason.
