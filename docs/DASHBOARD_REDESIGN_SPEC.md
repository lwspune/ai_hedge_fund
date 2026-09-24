# Dashboard redesign spec

**Status:** approved direction, ready to implement · **Scope:** `dashboard/` only · **Written:** 2026-09-24

This document is self-contained. An implementer with the repo and no other context should be able
to build the redesign from it. Read `CLAUDE.md` first for the project's rules (TDD, accessibility,
no secrets in the client, conventional commits, plan-then-confirm per phase).

---

## 0. Why (diagnosis, condensed)

The current dashboard renders the project's internal documentation as a web page. Concretely:

| Problem | Where | Effect |
|---|---|---|
| One vertical scroll of 8 equal-weight panels; the actionable table (open buybacks) is 5th | `src/App.jsx` | The daily question "anything to do today?" is not answered above the fold |
| 60 rows of bulk/block deals (a **null** signal) and a 25-row scan log on the landing page | `DealsView`, `ScanHistory` | Most pixels go to non-actionable data |
| Monospace for body, headings and prose | `src/index.css` body font | Reads as a terminal |
| Six font sizes within a 4px band, uppercase tracked labels everywhere | `index.css` | No hierarchy, everything shouts |
| Panel border → card border + coloured edge → badge border → tag border | `.panel .card .badge .tag` | Box-in-box clutter |
| One accent colour (mint) used for links, buttons, symbols, "edge", buy side, success notes, focus | `--accent` | Colour carries no meaning; every table has a column of green mono links |
| Internal jargon in UI: `buyback_arb`, "honesty layer", "feedback loop", "lens", shell commands in empty states | all components | Talks to the developer, not the user |
| All table cells `nowrap`, no sort/filter/sticky header, no frozen first column on statement tables | `index.css`, `CompanyPage` | Horizontal scroll everywhere, row labels lost |
| Company page = 10 stacked panels, no tabs, no sticky header, no search | `CompanyPage.jsx` | Long scroll to find anything |
| Whole-page "Loading…" then pop-in; rights/unlocks pop in later | `App.jsx` | Janky first paint |
| Vite template residue: `App.css` (unused), `assets/*.png|svg`, `public/icons.svg`, template README, `<title>dashboard</title>` | repo | Unprofessional |

**Keep:** verdict-aware concept, read-only supabase-js + RLS, hash routing without a router
dependency, existing accessibility groundwork (focus rings, `sr-only`, `aria-labelledby`,
scoped `th`).

## 1. Goals and non-goals

**Goals**
1. The home view answers "is there anything to act on or avoid today?" in one screen.
2. Reference material (signal verdicts, evidence) and bulk data (deals, history, logs) are one click
   away, not on the home view.
3. A small, consistent design system: sans-serif UI, monospace numerals, flat surfaces, one
   interactive accent, semantic colour reserved for verdict/direction/status.
4. Every table is readable on a 390px phone and a 1440px desktop.
5. Zero regression in the accessibility baseline; keyboard-complete.

**Non-goals (do not do)**
- No changes to Python, `db/schema.sql`, edge functions, or GitHub workflows (except adding the
  dashboard test step to `ci.yml`).
- No new runtime dependencies. One new dev dependency: `vitest`. No router, no UI kit, no CSS
  framework, no chart library.
- No light theme. Tokens are structured so one can be added later; do not build it now.
- No writes from the browser other than the two existing edge-function calls (`refresh-deals`,
  `refresh-buybacks`). Anon key only. Never a `VITE_` service key.
- No new business logic in the client (no recomputing expected returns, acceptance, gaps). Display
  what the scanner stored.

## 2. Information architecture and routes

Hash routes, extending `src/useHashRoute.js` (`parseHash` is already unit-testable).

| Route | View | Purpose |
|---|---|---|
| `#/` | **Desk** | Today: act / avoid. Status strip. |
| `#/signals` | **Signals** | The verdict table. Evidence on expand. Last run per signal. |
| `#/data` → `#/data/deals` (default), `#/data/buybacks`, `#/data/positions`, `#/data/scans` | **Data** | Filterable bulk tables. |
| `#/company/:symbol` → `#/company/:symbol/overview` (default), `/financials`, `/events`, `/filings`, `/deals` | **Company** | Tabbed company page. |

`parseHash` returns `{ page: 'desk' | 'signals' | 'data' | 'company', tab?: string, symbol?: string }`.
Unknown hash → `desk`. Unknown tab → the view's default tab. Symbol validation regex stays as is.
`hashchange` scrolls to top only when `page` or `symbol` changes, not on tab changes.

**App shell (all views):** a sticky 52px top bar, then a 1200px max-width content column with
24px side gutters (16px below 640px).

Top bar, left to right:
- Wordmark: `Market Intel` (14px, semibold, primary text). Links to `#/`.
- Nav: `Desk` · `Signals` · `Data`. Active item = primary text + 2px accent underline; inactive =
  secondary text. Rendered as `<nav aria-label="Primary">` with `aria-current="page"`.
- Spacer.
- Global company search (see §6.4). Width 260px desktop; below 640px it collapses to an icon
  button that expands the input full-width over the bar.
- Freshness dot (see §6.1) with an accessible tooltip.

No page header, no subtitle paragraph, no footer sentence. The footer becomes a single 12px
tertiary line: `Read-only · data via Supabase · updated by scheduled refresh`.

## 3. Design system

All values live in `src/styles/tokens.css` as custom properties on `:root`. Components use tokens
only; no raw hex outside that file. Delete `src/App.css`. `src/index.css` keeps only the reset,
base element styles and utilities.

### 3.1 Colour (dark)

| Token | Value | Use |
|---|---|---|
| `--bg` | `#0b0d10` | Page background (`body`). Tables sit directly on this. |
| `--surface` | `#111418` | Raised surfaces: candidate cards, popovers, inputs, sticky bars. |
| `--surface-hover` | `#161a20` | Row hover, button hover. |
| `--hairline` | `#1f242b` | The only border colour. 1px. |
| `--text` | `#e6e9ee` | Primary text, headings, symbols, numbers. |
| `--text-2` | `#9aa3b0` | Secondary: labels, company names, dates. |
| `--text-3` | `#778190` | Tertiary: captions, table headers, footer. Meets 4.5:1 on `--bg` and `--surface`. |
| `--accent` | `#7aa2ff` | **Interactive only**: links, active nav, focus ring, primary button. |
| `--pos` | `#3ecf8e` | Positive: edge verdicts, BUY side, open status, favourable gap. |
| `--warn` | `#e8b34a` | Warning: thin/conditional-with-caveat, stale data, watch role. |
| `--neg` | `#f0616d` | Negative: SELL side, errors, null verdicts are **not** red (see below). |
| `--pos-bg` / `--warn-bg` / `--neg-bg` | the above at 14% alpha | Badge fills. |
| `--neutral-bg` | `rgba(154,163,176,0.14)` | Neutral badge fill (null verdict, closed status). |

Rules:
- Symbols and numbers are `--text`, never accent. A symbol that navigates gets an underline on
  hover/focus only.
- "Null / no edge" is **neutral grey**, not red. Red means loss or error.
- Focus ring: `outline: 2px solid var(--accent); outline-offset: 2px` on every interactive element.
- Contrast: every text token ≥ 4.5:1 on both `--bg` and `--surface`; verify with a checker before
  merging. Badge text on its 14% tint must also pass.

### 3.2 Typography

Load Inter from Google Fonts in `index.html` (`display=swap`, weights 400/500/600). No package.

| Token | Value |
|---|---|
| `--font-ui` | `Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif` |
| `--font-mono` | `ui-monospace, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace` |

Scale (size/line-height, weight):

| Role | Spec | Where |
|---|---|---|
| Display | 28/1.2, 600 | Company name |
| Title | 20/1.3, 600 | View title (Desk views have none; Signals/Data have one) |
| Section | 16/1.4, 600 | Section headings |
| Body | 14/1.5, 400 | Default |
| Small | 13/1.5, 400 | Table cells, secondary prose |
| Caption | 12/1.4, 500 | Table headers (sentence case, **no** uppercase, **no** letter-spacing), stat labels, badges |
| Numeric | 13 mono, `font-variant-numeric: tabular-nums` | Every numeric table cell, stat values (15px), prices |

Mono is used **only** for: ticker symbols, numeric cells, stat values, code in empty-state hints.

### 3.3 Space, radius, layout

- Spacing scale: 4 / 8 / 12 / 16 / 24 / 32 / 48 (`--s1`…`--s7`).
- Radius: 6px controls and badges (`--r-sm`), 10px cards and popovers (`--r-md`).
- Sections are separated by 32px vertical space and a section heading. **No panel boxes.** A
  section is `<section aria-labelledby>` with a heading row and content. The only bordered
  containers are: candidate cards on Desk, inputs, popovers, the sticky bars (bottom hairline).
- Tables: no outer border. `th` bottom hairline; `td` bottom hairline at 50% opacity. Row padding
  8px 12px. Sticky `thead` inside the scroll container. Numeric columns right-aligned. Text cells
  wrap by default; only symbol, date and numeric columns are `nowrap`. Row hover `--surface-hover`.
- Content max-width 1200px. Breakpoints: 640 (phone), 960 (tablet).

### 3.4 Motion

Only: 120ms opacity/background transitions on hover and skeleton shimmer. Respect
`prefers-reduced-motion: reduce` (disable shimmer).

## 4. Shared components (`src/components/ui/`)

Each is a small function component with the props listed. No context, no global state.

| Component | Props | Notes |
|---|---|---|
| `TopBar` | `route` | Wordmark, nav, `CompanySearch`, `FreshnessDot`. Sticky. |
| `Section` | `id, title, meta?, info?, action?, children` | Heading row: title (16/600) + optional `meta` (12px tertiary, e.g. "as of 24 Sep, 16:00") + optional `InfoPopover` (`info` = one-sentence evidence string + optional `href` to `#/signals`) + optional right-aligned `action` node. |
| `InfoPopover` | `label, children` | An `ⓘ` icon button (`aria-expanded`, `aria-controls`), toggles a `--surface` popover with the methodology sentence. Escape closes. Focus returns to the button. |
| `Badge` | `tone: 'pos' \| 'warn' \| 'neg' \| 'neutral', children, title?` | Single badge for verdicts, statuses, sides, index tags. 12px/500, 2px 8px, radius 6, tinted fill, **no border**. |
| `VerdictBadge` | `verdict` | Maps `edge`/`conditional` → pos "Edge"/"Conditional edge", `thin` → warn "Thin", `null` → neutral "No edge". Wraps `Badge`. |
| `Stat` | `label, value, sub?, tone?` | Label caption over a 15px mono value; optional 12px `sub`. Used in stat grids and the company header. |
| `StatGrid` | `children` | `display:grid; grid-template-columns: repeat(auto-fill, minmax(150px,1fr)); gap: 16px 24px`. Renders a `<dl>`. |
| `DataTable` | `columns, rows, rowKey, sort?, onSort?, stickyFirstCol?, emptyText, dense?` | `columns: [{ key, header, align: 'left'\|'right', mono?, render?(row), sortable?, width? }]`. Click-to-sort on `sortable` headers with `aria-sort`. `stickyFirstCol` pins the first column (used for statement tables). Wraps the table in a horizontally scrollable container with a subtle right-edge fade when overflowing. |
| `Button` | `variant: 'primary' \| 'ghost', size?, busy?, children` | Primary = accent fill, dark text, 500 weight. Ghost = hairline border, secondary text. `busy` sets `aria-busy`, disables and shows a spinner glyph. Default variant for refresh actions is **ghost**. |
| `Tabs` | `tabs: [{ id, label, href }], active` | Renders `<nav aria-label>` of links (hash hrefs), active gets `aria-current="page"` and an accent underline. Keyboard: arrow keys move focus between tabs. |
| `Skeleton` | `lines?, width?` | Grey shimmer blocks. `SkeletonTable rows cols` helper. |
| `EmptyState` | `title, hint?` | Title 14px secondary; `hint` 13px tertiary, may contain `<code>` for a CLI hint. |
| `ErrorNote` | `message` | Inline `role="alert"`, neg tone, never a full-page banner (except the missing-env case). |
| `SymbolLink` | `symbol, name?` | Mono symbol in `--text` linking to `companyHref(symbol)`; optional secondary name after it. Underline on hover/focus only. |

Existing `VerdictBadge.jsx` is replaced by the version above; old `.badge/.status/.side/.tag/.card`
CSS is deleted.

## 5. Formatting and copy rules

### 5.1 `src/lib/format.js` (pure, fully tested)

| Function | Input → output |
|---|---|
| `fmtDate(iso)` | `'2026-09-24'` → `'24 Sep'` if current year, else `'24 Sep 2025'`. Null → `'—'`. |
| `fmtDateTime(iso)` | timestamptz → `'24 Sep, 16:00 IST'` (convert to `Asia/Kolkata` explicitly; source rows are UTC). |
| `fmtRelative(iso, today?)` | `'today'`, `'tomorrow'`, `'in 6 d'`, `'3 d ago'`, `'in 5 wk'` beyond 21 days. |
| `fmtPct(fraction, dp=1)` | `0.034` → `'3.4%'`; sign shown for negatives only. |
| `fmtPctPts(value, dp=1)` | value already in percent (`3.4` → `'3.4%'`). Use for screener ratios. |
| `fmtInr(v, dp=2)` | `1234.5` → `'₹1,234.50'` with en-IN grouping. |
| `fmtCr(rupees)` | `12_345_678` → `'₹1.23 cr'`; ≥ 100 cr → no decimals. |
| `fmtCrValue(cr)` | value already in crore → `'₹1,234 cr'`. |
| `fmtLakh(rupees)` | `'12.3 L'`. |
| `fmtQty(n)` | en-IN grouped integer. |
| `dash(v, fn)` | null/undefined → `'—'` else `fn(v)`. |

Every formatter returns `'—'` for null/undefined/NaN. All dates in the UI go through these; no raw
ISO strings and no `toLocaleString()` calls in components.

### 5.2 Signal display copy — `src/lib/signalLabels.js`

`signals.json` stays the source of truth for verdict/type/role/summary (generated from
`scanner/catalog.py`; do not hand-edit). The dashboard adds display copy keyed by `name`; unknown
names fall back to the raw name.

| name | label | headline (one line, ≤ 90 chars) |
|---|---|---|
| `buyback_arb` | Buyback tender arbitrage | Small-shareholder quota; works at ≤ 20% tax slab, ~0 at 30% |
| `rights_re` | Rights entitlement discount | REs trade ~3.5% below stock − issue price on liquid days |
| `lockin_expiry` | Anchor lock-in unlock | −1.25% dip T−1→T+2 at the 90-day unlock; not shortable |
| `merger_arb` | Merger arbitrage | Thin (~4–5% annualised), efficiently priced, deal-break tail |
| `mean_reversion` | Mean reversion | No edge vs buy-and-hold after costs |
| `smart_money_deals` | Bulk/block deal following | Post-disclosure return ~0; front-run before disclosure |
| `open_offer_arb` | Open offer arbitrage | No retail reservation → no structural edge (control case) |
| `index_rebalance` | Index rebalance front-run | Pre-announced flow is arbitraged before you can act (n=151) |
| `fno_ban` | F&O ban reversal | n=920 episodes, no reversal at any window |
| `promoter_buying` | Promoter open-market buying | Worked 2020–23, gone 2024–26 |

Role labels: `primary` → "Trade", `watch` → "Watch", `lens` → "Lens", `documented` → "Control".
Type labels: `structural` → "Structural", `drift` → "Drift", `spread` → "Spread".

### 5.3 Copy rules

- Sentence case everywhere. No uppercase labels.
- No snake_case identifiers in headings or body. They may appear as 12px mono secondary text next
  to the human label on the Signals view only.
- No methodology paragraphs inside views. Each section gets one sentence in an `InfoPopover`.
- Empty states: one plain sentence, plus an optional CLI hint in `<code>` as the `hint`.
- Status messages after a refresh: one sentence, e.g. "Scanned 40 ids, 2 new." Auto-clear after
  8 s or on the next action.
- Error text: "Couldn't load X." followed by the raw message in 12px tertiary.

## 6. Views

Every view loads its own data with `useEffect` per section (independent skeletons), never a
whole-page loading gate. Only the missing-env case (`configured === false`) shows a full-page
message.

### 6.1 Desk (`#/`)

Layout (top to bottom):

**Status strip** — one 12px line under the top bar, tertiary text, items separated by `·`:
`Deals 24 Sep · Buyback scan 2 h ago · Rights scan 2 h ago · Filings today`. Each item turns
`--warn` when older than its rule. Rules mirror `scripts/check_freshness.py`: deals 6 days,
filings 5 days; scans 2 days. The `FreshnessDot` in the top bar is green if all fresh, amber if any
stale, with the strip text as its tooltip. Queries (one row each, `limit 1`):
- `market_deals` order `deal_date desc`
- `scan_runs` where `signal_name = buyback_arb` order `run_at desc`
- `scan_runs` where `signal_name = rights_re` order `run_at desc`
- `filings` order `disclosed_at desc`

**Section "Act" → "Open buybacks"** (meta: `as of {fmtDateTime(run_at)}`; info: the buyback_arb
headline; action: ghost `Refresh` calling `refresh-buybacks` then reloading).
Data: latest `scan_runs` row for `buyback_arb` → `candidates` where `run_id = that id`, order
`score desc`. Keep rows where `payload.is_open === true`. Fetch `buybacks` `in ('symbol', …)` for
`company` and `status`. Render as `DataTable` (dense):

| Column | Source | Format |
|---|---|---|
| Company | `SymbolLink symbol name=company` | |
| Price | `payload.cur_price` | `fmtInr` |
| Buyback | `payload.buyback_price` | `fmtInr` |
| Premium | `payload.premium` | `fmtPct` |
| Entitlement | `payload.entitlement_small` | `fmtPct(…, 0)` |
| Est. acceptance | `payload.est_acceptance` | `fmtPct(…, 0)` |
| After-tax est. | `payload.exp_return` | `fmtPct`; pos tone if > 0.02, else `--text` |
| Record date | `payload.record_date` | `fmtDate` + `fmtRelative` in tertiary |
| Closes | `payload.close_date` | `fmtDate` |
| Status | `buybacks.status` | `Badge`: open → pos, tendered → warn, settled/skipped → neutral |

Column header for "After-tax est." carries `title="At the 30% slab; see Signals"`.
Empty: "No open tender buybacks." hint `python -m scanner.run buyback_arb --save`.

**Section "Act" → "Rights entitlements trading"** (meta: `as of …`; info: rights_re headline).
Data: latest `scan_runs` for `rights_re` → its `candidates`, order `score desc`. Columns: Company,
Ratio, Issue price, Stock, RE, Gap (`fmtPct(…, 2)`, pos tone when `action` starts with `BUY`),
Turnover (`fmtLakh`), RE last day (`fmtDate` + relative), Apply by, Action (`Badge`: `BUY…` → pos
"Buy RE", `RE rich…` → warn "RE rich", `illiquid` / `penny…` / `fair` → neutral with the raw text as
`title`). Empty: "No rights entitlements trading right now."

**Section "Avoid" → "Anchor unlocks, next 14 days"** (info: lockin_expiry headline).
Data: `corporate_events` where `event_type in (anchor_lockin_30, anchor_lockin_90)` and
`event_date` between today and today+14, order `event_date, symbol`. Columns: Date (`fmtDate` +
relative), Company (`SymbolLink`), Unlock (`anchor_lockin_30` → "50% at 30 d", `_90` → "Rest at
90 d"), Board (`details.board`), Anchor shares (`fmtQty(details.anchor_shares)`). Empty: "No anchor
lock-in expiries in the next 14 days."

Nothing else on the Desk. No signals cards, no deals, no scan log, no positions.

### 6.2 Signals (`#/signals`)

Title "Signals" + one 13px secondary line: "Every signal carries the verdict its event study
produced. Falsified signals stay as lenses and are never traded."

`DataTable` of `signals.json` merged with `signalLabels` and the latest `scan_runs` per signal
(one query: `scan_runs` order `run_at desc` limit 200, reduce client-side to first per name).
Sort: role order primary, watch, lens, documented; then name.

| Column | Content |
|---|---|
| Signal | label (14px `--text`) with `name` beneath in 12px mono tertiary |
| Verdict | `VerdictBadge` |
| Role | role label, `Badge` neutral (primary → pos) |
| Type | type label, secondary text |
| Finding | headline, secondary text, wraps |
| Last run | `fmtRelative(run_at)` + `n_candidates` ("2 h ago · 3 found"); `'—'` if none |

Each row is expandable (a chevron button, `aria-expanded`): the expanded row shows the full
`summary` (13px secondary, max 70ch) and the last 10 runs for that signal (date, verdict at run
time, candidates) as a mini table. Expansion is client-side; runs come from the same 200-row query.

### 6.3 Data (`#/data/*`)

Title "Data" + `Tabs`: Deals · Buybacks · Positions · Scans.

**Deals** — action: ghost `Refresh` (`refresh-deals`). Filter row above the table: `Badge`-styled
toggle chips for side (Buy / Sell) and kind (Bulk / Block), plus a symbol text filter (client-side
`startsWith`). Data: `market_deals` order `deal_date desc, value desc nullslast`, limit 300;
filters apply client-side. Columns: Date, Company (`SymbolLink`), Client (wraps, max 34ch, full
text in `title`), Side (`Badge` pos/neg), Qty, Price (`fmtInr`), Value (`fmtCr`), Kind. Sortable:
Date, Value, Qty. Footer line: "Showing N of M".

**Buybacks** — all rows, `buybacks` order `record_date desc nullslast`, limit 200. Status chips
(Open / Tendered / Settled / Skipped). Columns: Company, Buyback price, Entitlement, Issue size
(`fmtCrValue`), Floor est. (`est_return`, `fmtPct`), Record date, Close date, Status. Info popover
explains "Floor est. = guaranteed-acceptance return before tax; after-tax ranking is on the Desk."

**Positions** — `tenders` with `buybacks(symbol,company)` and `outcomes(...)` order
`decided_on desc`. Columns: Company, Decided, Shares, Capital (`fmtInr(…, 0)`), Accepted,
Realised acceptance (`fmtPct`), Realised return (`fmtPct`, pos/neg tone by sign). Empty: "No
tenders recorded." hint `python -m scanner.track tender …`.

**Scans** — `scan_runs` order `run_at desc` limit 100. Columns: Signal (label), Verdict, Candidates,
Run at (`fmtDateTime`).

### 6.4 Global company search

Lives in the top bar on every view. Behaviour as today (`companies` `or(symbol.ilike.term*,
name.ilike.*term*)`, 250 ms debounce, ≥ 2 chars, 8 results, delisted badge), rendered as a
`--surface` popover listbox under the input (`role="listbox"`, options `role="option"`, arrow keys
move, Enter navigates, Escape closes, click outside closes). Pressing `/` anywhere (when focus is
not in an input) focuses it. Placeholder: "Search company or symbol". Keep the existing input
sanitiser for PostgREST.

### 6.5 Company (`#/company/:symbol/:tab`)

**Header** (sticky under the top bar, `--surface`, bottom hairline; collapses to non-sticky below
640px):
- Left: name (Display 28), symbol (mono, secondary) beside it; second line 13px secondary:
  `sector › industry › basic_industry` (deduped, fall back to `companies.industry`) · series ·
  listed `fmtDate`; delisted → neutral `Badge` "Delisted {date}". Index memberships as neutral
  badges (max 4, then "+N").
- Right (hidden below 960px, shown as a stat row under the header instead): `Stat` × 4: Price,
  Market cap (`fmtCrValue`), P/E, ROCE. If no snapshot, show a single tertiary "Fundamentals not
  fetched yet".
- Below: `Tabs` Overview · Financials · Events · Filings · Deals (Deals tab hidden when the
  company has no deals; Filings tab shows a count).

Queries are the same nine as today's `CompanyPage.jsx`, split per tab so each tab fetches only what
it renders (header needs `companies` + `company_snapshot`; the tab bar needs counts for filings and
deals, fetched with `head: true, count: 'exact'`).

**Overview**
- "Snapshot" `StatGrid` of 12 stats (as today: market cap, price, 52w high/low, P/E, book value,
  dividend yield, ROCE, ROE, D/E, revenue TTM, net profit TTM, face value). Meta: "screener.in ·
  consolidated · fetched 24 Sep".
- "From filings" (only when `company_kpis` non-empty): `StatGrid` of latest order book, capacity
  utilisation, lender ratios (GNPA, NNPA, NIM, credit cost, PCR, CRAR, CASA, RoA), order wins
  total; then a `DataTable` Metric / Value / Quote (wraps) / Source (date link, opens in new tab,
  `aria-label` as today); then "Management guidance" as a quote list. Info popover: "Extracted by
  rule from filing PDFs; every value keeps its quote and source. Check the quote."
- "Signal activity" (only when non-empty): rows of `VerdictBadge`-style `Badge` + signal label +
  key numbers + date, one line each, from `buybacks` (by symbol) and `candidates` (by symbol, latest
  20).
- "Upcoming events" strip: events with `event_date >= today`, as `Badge` neutral + label + relative
  date, or hidden when none.

**Financials** — three `DataTable`s with `stickyFirstCol` (Metric column pinned), periods as
columns in chronological order, scroll container initialised to the right edge so the newest period
is visible on load. Annual: Revenue, Net profit, OPM %, EPS. Quarterly: same. Shareholding:
Promoters, FIIs, DIIs, Public, Shareholders. Numeric cells mono, right-aligned. Meta: "₹ crore".
Empty per table: "No annual data." etc.

**Events** — `DataTable` Date / Event / Detail / Record date (labels and `eventDetail` as today), and
an IPO line beneath when `ipos` has a row (board, issue price, listing date, day-1 close and %).

**Filings** — category chips (built from the distinct categories present) + `DataTable` Date /
Category / Subject (wraps, full text in `title`) / Document ("PDF ↗" link, new tab, `aria-label`).
Limit 50.

**Deals** — `DataTable` Date / Client / Side / Qty / Price, limit 50. Info popover: "Informational:
bulk/block following is a null signal."

Back navigation: the browser back button (hash history) is the way back; no "← All signals" link.
The top bar nav is always present.

## 7. Loading, error and empty behaviour

- Each `Section` fetches independently: `Skeleton` while loading, `ErrorNote` on failure,
  `EmptyState` when zero rows. Never block sibling sections.
- Skeleton shapes match the content (`SkeletonTable rows={5} cols={n}` for tables, stat-shaped
  blocks for grids).
- Refresh buttons: `busy` during the call; on success a one-line status under the section heading
  (`role="status"`), auto-cleared after 8 s; on failure an `ErrorNote`.
- All fetches guard against unmounted updates (the `live` flag pattern already in
  `CompanyPage.jsx`).
- Log fetch and edge-function errors with `console.error` at the call site (system boundary); no
  other console output.

## 8. Accessibility checklist (must pass before each phase is "done")

- Every interactive element has a visible focus ring (`:focus-visible`), including table sort
  headers, tab links, chips, popover triggers and search options.
- Keyboard: `/` focuses search; arrow keys in the search listbox and in `Tabs`; Escape closes
  popovers and the listbox and returns focus to the trigger.
- Landmarks: one `<header>`, one `<nav aria-label="Primary">`, one `<main>`, sections with
  `aria-labelledby`. Tab groups use `<nav aria-label="…">` with `aria-current`.
- Tables: `<th scope>` everywhere; sortable headers expose `aria-sort`; sticky first column keeps
  `scope="row"`.
- Icon-only buttons have `aria-label`. External links say "(opens in a new tab)" in `aria-label`.
- Contrast ≥ 4.5:1 for all text tokens on both backgrounds; badge text on tints verified.
- `prefers-reduced-motion` disables shimmer.
- Lighthouse accessibility score ≥ 95 on Desk and a company page (manual check, note the score in
  the PR/commit body).

## 9. Testing

Add `vitest` as the only new dev dependency. `package.json`: `"test": "vitest run"`. Add
`- run: npm test` to the dashboard job in `.github/workflows/ci.yml` between lint and build.

TDD applies to pure logic. Write these tests first and watch them fail:

- `src/lib/format.test.js` — every formatter in §5.1, including null → `'—'`, en-IN grouping
  (`12,34,567`), IST conversion of a UTC timestamp, relative-date boundaries (today, tomorrow,
  21-day switch to weeks, past dates).
- `src/useHashRoute.test.js` — `parseHash` for every route in §2, default tabs, unknown tab →
  default, invalid symbol → desk, encoded symbols (`M&M`, `BAJAJ-AUTO`).
- `src/lib/signalLabels.test.js` — every name in `signals.json` has a label and a headline ≤ 90
  chars; unknown name falls back to the raw name.
- `src/lib/freshness.test.js` — the stale rule per source (mirror `scripts/check_freshness.py`
  thresholds) given a fixed "today".
- Table sorting comparator (`src/lib/sort.js`): numeric with nulls last, string, date.

Components are covered by lint, the build, and the manual golden-path check. No DOM testing library.

## 10. Cleanup (part of phase 1)

Delete: `src/App.css`, `src/assets/hero.png`, `src/assets/react.svg`, `src/assets/vite.svg`,
`public/icons.svg`, template `README.md` (replace with a 15-line README: what it is, env vars,
scripts, deploy). Set `<title>Market Intel</title>` and `<meta name="description">` in
`index.html`. `public/favicon.svg` is the Vite lightning bolt: replace it with a simple monogram
SVG (an "M" or a two-bar glyph in `--text` on `--bg`, no gradients).

## 11. Sequencing — four commits, each shippable and confirmed with Vilas before starting

Per `CLAUDE.md`: present the plan for each phase, get confirmation, then build. Definition of done
for each: `npm run lint` clean, `npm test` green, `npm run build` succeeds, golden path checked in
the browser, and the phase's acceptance criteria below met.

**Phase 1 — `refactor(dashboard): design tokens, shared components, formatters` + cleanup (§3, §4,
§5, §9, §10)**
Rewire the *existing* panels onto the new tokens and components without changing the IA yet, so the
visual foundation lands on its own. Acceptance: no monospace body text; no nested bordered boxes;
all dates/numbers pass through `format.js`; old `.panel/.card/.badge/.status/.side/.tag` CSS gone;
template files gone; tests exist and pass; the deployed page is visibly calmer.

**Phase 2 — `feat(dashboard): app shell, Desk and Signals views` (§2, §6.1, §6.2, §6.4)**
Acceptance: `#/` shows only status strip + Act + Avoid and fits in one 1440×900 screen with
typical data; search works from the top bar with keyboard; `#/signals` renders the table with
expand rows; no signals cards, deals or scan log on the Desk.

**Phase 3 — `feat(dashboard): Data view and tabbed company page` (§6.3, §6.5)**
Acceptance: deals filters work client-side; company header sticks; each tab fetches only its data;
statement tables keep the metric column visible while scrolling; a 390px phone shows every table
without page-level horizontal scroll.

**Phase 4 — `feat(dashboard): loading skeletons, keyboard shortcuts, a11y pass` (§7, §8)**
Acceptance: no whole-page loading gate; skeletons match content shapes; Lighthouse a11y ≥ 95 on
Desk and company page; reduced-motion respected.

After phase 4: update the **Dashboard (P3)** paragraph in `CLAUDE.md` (views, routes, test command)
and `scripts/emit_signals_json.py` docstring if `signalLabels.js` needs a reminder to stay in sync
when a signal is added.

## 12. Decisions already made (don't re-litigate without a new reason)

- **Dark only.** Single user, used in the evening after the 20:30 IST refresh.
- **Desk shows the after-tax estimate as stored** (30% slab default from `expected_after_tax`),
  labelled as such. The slab-conditional caveat lives in the info popover and on Signals. No client
  recomputation.
- **Open = `payload.is_open`** from the latest scan, not `buybacks.status` (status is the user's
  lifecycle field and is not advanced automatically).
- **Deals stay in the product** but on the Data view, because the warehouse is useful context on
  the company page even though the signal is null.
- **No router, no UI library, no CSS framework.** The app is ~15 components; the existing
  hash-route hook plus tokens is enough, and it keeps the static Vercel deploy trivial.
- **Inter via Google Fonts link**, not a package and not self-hosted. Falls back to system sans.
- **Blue accent, green positive.** Interaction colour must differ from "good outcome" colour, or a
  link reads as a recommendation.
