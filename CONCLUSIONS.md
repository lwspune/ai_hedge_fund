# CONCLUSIONS — Indian Market Inefficiency Validations

**Status: active platform. Eleven signals validated. Two actionable edges (buyback tender, rights-entitlement discount); one real but unshortable effect.**

The question that started this: *are there real, past-tested inefficiencies in Indian
markets exploitable for quick gains?* We tested four, with honest event studies and
realistic costs. Below is the verdict on each and the thesis that ties them together.

## The meta-thesis (the most valuable finding)
**Edge survives only where a structural barrier puts retail on the inside.** Everything
else — predicting drift from public signals, or capturing an efficiently-priced spread —
gets arbitraged or competed away after costs.

- Drift-prediction signals → **null** (arbitraged away).
- Efficiently-priced spreads (merger arb on safe deals) → **thin** (~risk-free).
- Structural reservation (buyback small-shareholder quota) → **conditional edge**.
- Forced supply behind a **short-sale barrier** (anchor lock-in unlock) → real, persistent
  dip — the barrier that shields it from arbitrageurs also blocks retail shorts, so it is an
  avoid/exit rule, not a trade.

## The validations

### 1. Mean reversion (RSI<35 + 20% below 200-DMA + quality) — NULL
Built and runnable, but the prior project already proved this signal family loses to
NIFTY buy-and-hold after costs on liquid large-caps. Kept as an informational lens.

### 2. Follow institutional bulk/block buys — NULL
Event study, 2yr, 451 institutional buy-events, T+1 entry vs NIFTY:

| Horizon | Institutional buys | Placebo (prop/LLP) |
|---|---|---|
| Pre-event T−10→T0 | +1.70% (t=3.3) | +14.24% (t=13.6) |
| Post T+1→T+20 | **+0.21% (t=0.3)** | −2.20% (t=−2.3) |
| Post T+1→T+60 | −0.54% | −6.23% (t=−3.9) |

Post-disclosure return is ~0 — the edge is **front-run away pre-event**, where a public
follower can't act. The classifier works (placebo prop-buys are toxic, −6% over 60d), but
the institutional signal itself carries no follower edge.
*Evidence:* `evidence/smart_money_deals/2026-09-24` (the raw 2024-25 deals the study used) · sha 4f552e3 (laptop baseline).

### 3. Buyback small-shareholder tender arb — CONDITIONAL EDGE (the keeper)
81 tender buybacks (Dec-2022 → Dec-2025), ₹2L, **unadjusted NSE closes** (corrected
2026-09-24 — see note), residual sold 21 trading days after close:

| Scenario | Mean | Median | Win |
|---|---|---|---|
| Buyback premium vs entry | +24% | +22% | 99% |
| Gross @ entitlement floor | +1.5% | **+0.4%** | 51% |
| Gross @ 3× entitlement (high-acceptance) | +6.4% | **+5.4%** | 69% |
| After-tax today's rules, 30% slab — floor | −1.3% | −2.1% | 40% |
| After-tax today's rules, 30% slab — 3× | +0.0% | **−1.5%** | 42% |
| After-tax today's rules, 20% slab — 3× | +4.3% | +3.8% | 68% |
| After-tax today's rules, 0–5% slab — 3× | +11–13% | +10–12% | 81–83% |

Blind tendering ≈ break-even; the money is in **selecting high-acceptance, high-premium
small-caps** (the structural 15% small-shareholder reservation — barred to institutions —
gives near-100% retail acceptance). **Since Oct-2024 the edge is also conditional on the
tax slab:** payouts are taxed as dividend at slab, so at 30% the high-acceptance trade is
~0 after tax; it works at ≤20% (low-income / family ₹2L accounts). The low-slab rows assume
the accepted shares' cost is used as a capital loss **against other short-term gains** (credited
at the 20% STCG rate in `after_tax_return`); without gains to offset, that benefit only
carries forward. **Still the one signal worth building selection around — for the right account.**

*Correction note (2026-09-24):* the original table (n=48: floor median −0.1%, 3× median
+6.4%, 3× mean +23%) used yfinance closes, which are back-adjusted for later splits/bonuses
while the buyback price is nominal (SPORTKING's 1:10 split showed as a "+1282%" premium),
and a cache that had silently dropped 29 events. Medians barely moved; the inflated means
did. Verdict unchanged; the tax-slab condition is new.
*Evidence:* `evidence/buyback_arb/2026-09-24` (event list only — the laptop run kept no results file) · sha 4f552e3. A re-run with the 2026 events and as-of market caps is queued (SUGGESTIONS backfill ledger).

### 4. Stock-swap merger arb — THIN
3 verified completed deals (HDFC, LTIMindtree, Shriram): announcement spreads +2.7/2.4/6.7%
(mean +3.9%, ~4.6% annualised *gross*). Efficiently priced; before futures carry and the
deal-break tail (Zee-Sony). Unattractive for retail. (Open-offer arb, Form A, is a
structural null — no small-shareholder reservation — kept only as the control that proves
why buybacks work.)

### 5. Index-rebalance front-run (NIFTY 50 / Next 50 reconstitution) — NULL
Buy index additions / short deletions on the announcement, exit at the effective date.
Event study over **151 verified NIFTY Next 50 clean entries/exits, 2018→2025** (announce +
effective dates extracted verbatim from niftyindices.com press-release PDFs; promotion/
relegation and ad-hoc/merger events excluded as confounded), benchmark-adjusted vs NIFTY:

| Window | Adds (long) | Drops (short) | Combined |
|---|---|---|---|
| announce+1 → effective | +0.83% (t=0.5) | −0.12% (t=−0.1) | +0.36% (t=0.4) |
| **effective−5 → effective** (forced-flow window) | −0.11% | −0.03% | **−0.07% (t=−0.1)** |
| effective → effective+5 (reversal) | −0.38% | −1.54% (t=−2.4) | −0.95% (t=−2.0) |

The front-run is **null** — even the tight window where funds are forced to trade is flat.
**Why:** NSE pre-announces reconstitutions ~4 weeks out, so the forced flow is *anticipated*
and arbitraged before a public follower can act. The lone significant effect (deletions
rebound post-effective) **failed segmentation**: the liquidity gradient runs opposite to the
overshoot mechanism, and the rebound is almost entirely a **2021–22 regime artifact** (−4.2%
that era, ~0 in 2023–25) — a ghost, not an edge. (`scripts/validate_index_rebalance.py`,
`scripts/segment_index_rebalance.py`; data `data/next50_rebalance_events.csv`.)

This is the cleanest confirmation of the meta-thesis yet: a forced flow with **no barrier
keeping competitors out** (anyone can read the announcement) gets arbitraged to zero — the
exact mirror of the buyback small-shareholder quota that *does* fence institutions out.

### 6. Anchor lock-in expiry overhang — CONDITIONAL (real, not shortable)
Anchor investors' shares unlock 30 days after allotment (50%; 100% before Apr-2022) and 90
days (the rest). 1,820 expiries from 2,184 NSE IPOs (chittorgarh, 2006→2026); 1,382 priced on
unadjusted NSE closes (mainboard + SME series), benchmark NIFTY 500. T = first trading day
on/after expiry; windows fixed in advance.

| Window (vs NIFTY 500) | 30-day unlock (n=809) | 90-day unlock (n=573) |
|---|---|---|
| pre T-10→T-1 | +1.7% (median −0.9%) | −0.7% |
| **event T-1→T+2** | **−0.68% (t=−2.6)**, median −1.5% | **−1.25% (t=−4.6)**, median −2.1% |
| post T+2→T+10 | +0.3% | +0.5% |
| placebo 3-day, same stocks (T-20, T+15) | +0.2% / +0.1% | +0.2% / +0.1% |

- **Control passes:** same-length windows on the same stocks away from the unlock are ~0, so
  the dip is the unlock, not the generic post-IPO drift (medians are negative everywhere).
- **Regime passes (90d):** 2022-23 −1.1%, 2024-26 −1.3% (t=−4.2). 30d was strongest pre-2022
  (when it released 100%): −1.15% (t=−3.3); weaker since the split.
- **Segments:** negative in every pre-specified cut; strongest 90d mainboard −1.8% (t=−5.6).
  Anchors under water at expiry show the worst full-window drift (−4.4 to −4.5%).
- **Tradability:** the short side needs an overnight short; new listings are not in F&O
  (only 48/12 of these symbols are in *today's* F&O list, and they joined later). Retail can't
  harvest it. **Use:** don't buy a recent IPO into T-1; a holder can sell at T-1 and rebuy after
  T+2 (~1.25% saved at 90d vs ~0.3% costs + tax friction).
- Caveat: 416 events unpriced (renamed / migrated / thin symbols) — possible survivorship tilt.

Fits the thesis from the other side: the effect persists *because* a barrier (short-sale
constraints on fresh IPOs) keeps arbitrageurs out — but the same barrier keeps retail out.
(`scanner/lockin.py`, `scripts/validate_lockin.py`.) *Evidence:* `evidence/lockin_expiry/2026-09-24` · sha 4f552e3 (laptop baseline).

### 7. F&O ban reversal — NULL
Stocks whose open interest crosses 95% of MWPL enter the F&O ban (no fresh derivative positions).
Hypothesis: the forced unwind overshoots, so the pre-ban 5-day move reverses. 1,035 ban episodes
(96 stocks, NSE ban archive 2020→2026), 920 usable; reversal measured against a **same-stock
control** (same windows 60 trading days away, ≥20 days from any ban) because short-term reversal
is generic.

| Reversal of pre-ban move | Ban | Control |
|---|---|---|
| entry E-1→E+2 | −0.08% (t=−0.5) | +0.34% |
| during the ban | −0.20% (t=−1.0) | +0.18% |
| exit X-1→X+5 | −0.23% (t=−0.6) | −0.03% |
| post X→X+10 | −0.28% (t=−0.9) | −0.03% |

No reversal anywhere, and no better than control. Segment flickers fail the robustness bar:
names that ran *up* into the ban gain after exit on the mean (+1.0%, t=3.1) but the **median is
+0.1%** (fat-tail driven); the exit effect shows in 2022-23 only (t=−2.3), not 2024-26 (t=−0.6).
The one clean effect — stocks *sold* into the ban keep falling during it (−0.7%, median −0.7%,
39% up) — is continuation, not reversal, and sits in the ban window where no fresh short can be
opened. Thesis check: the ban blocks new derivatives but the cash market stays open to all — no
competitor is excluded, so nothing is left for retail. (`scanner/fnoban.py`,
`scripts/validate_fno_ban.py`.) *Evidence:* `evidence/fno_ban/2026-09-24` · sha 4f552e3 (laptop baseline).

### 8. Rights-entitlement (RE) discount — CONDITIONAL (actionable, small)
Since Jan-2020 NSE lists rights entitlements (REs) while the issue is open. One RE + the issue
price = one new share, so fair RE = S − issue. Gap = (S − issue − RE)/S at the close; positive
= RE cheap. Inputs from the `rights_issues` table (chittorgarh offer data: exact issue price, the
RE's own NSE symbol, timetable): 248 fully-paid, non-withdrawn NSE issues since 2020; 94 had NSE
RE prices, 79 with liquid days (RE turnover ≥ ₹5 L). Hurdle 0.5% (RE costs + ~4-5 weeks' capital
lock on the application money). Partly-paid issues are excluded (their RE values differently).

| Liquid days | Median gap | Days above hurdle |
|---|---|---|
| all (n=395) | +4.3% | 85% |
| first 3 / last 3 days | +4.0% / +5.1% | 86% / 85% |
| 2020-22 / 2023-24 / 2025-26 | +3.7% / +4.5% / +4.3% | 72% / 86% / 92% |
| **non-penny** (issue ≥ ₹10, stock ≥ ₹20; post-hoc check) n=291 | **+3.5%** | 83% |

- Non-penny, per issue: median +3.4%, **48/55 issues** above the hurdle; positive in every era
  (2020-22 mean ~0 from a few negative outliers, median +3.0%).
- Inputs verified against an external source (NDTV 2025: ₹82 issue, 3:4, FV ₹4).
- An earlier pass that derived the issue price from today's face value + premium and assumed
  every RE was `<SYM>-RE` found the same effect on fewer issues (40 non-penny, +3.35%); the
  stored RE symbols (e.g. `NDTVR`, `TILRR`) added the missing coverage.
- **How to capture it without shorting:** if you want the stock anyway, buy the RE and
  subscribe before the issue closes instead of buying shares; if you hold it, sell shares and
  buy REs (same end position, cash freed). Net ≈ 2.5-3% per issue after costs/capital lock.
- **Limits:** capacity is a few lakh/day; penny issues are noisy. Live (with RE last day and
  application deadline): `python -m scanner.run rights_re`.

Fits the thesis: REs are a procedural, illiquid, short-lived instrument that institutions
ignore and many retail holders don't understand (they dump or let entitlements lapse) — a
friction barrier, with retail able to sit on the right side of it.
*Evidence:* `evidence/rights_re/2026-09-24` (results + RE closes zip) · sha 4f552e3 (laptop baseline).

### 9. Delisting reverse book-building (#3) — PARKED (data not reachable)
No free, automatable source of delisting offers with floor/discovered prices and outcomes:
chittorgarh has no delisting pages, BSE's API 403s (Akamai), NSE has no public endpoint, SEBI
doesn't file delisting offers as a category, and nselib's board-meeting calendar showed only 7
"voluntary delisting" items in 2024 (several single-exchange exits). Needs manual curation
from exchange/news PDFs (~5-15 promoter offers/yr); the Sep-2024 fixed-price route (15% over
floor) likely compresses the RBB premium. Revisit only as a curation project.

### 10. Promoter open-market buying (SAST Reg 29) — NULL (decayed)
NSE `corporate-sast-reg29` disclosures, 2020→2026: 1,854 promoter open-market buy events
(clustered per stock, 10-day gap), entry the day after disclosure, vs NIFTY 500. Contrast legs:
1,241 promoter sells, 1,183 non-promoter buys.

| +60d (median) | 2020-21 | 2022-23 | 2024-26 |
|---|---|---|---|
| big-stake promoter buys | +6.6% | +5.9% | **−1.0%** (47% up) |
| clustered promoter buys | +4.9% | +4.2% | **−1.6%** (44% up) |
| promoter sells | −1.9% | +2.8% | −5.8% (36% up) |

The pooled headline (+60d mean +8.1%, t=10.7) is a small-cap fat tail — median +0.9%, 52% up —
and the effect fails the era cut: it lived in the 2020-23 small-cap run and is gone in 2024-26.
Same decay as `index_rebalance` / `smart_money_deals`: a public drift signal. Recent promoter
*sells* look negative, but that leg flips sign across eras and was a contrast, not a hypothesis —
logged in the backlog to pre-register, not claimed. (`scanner/insider.py`,
`scripts/validate_promoter_buys.py`.) *Evidence:* `evidence/promoter_buying/2026-09-24` (results + the reg29 pulls) · sha 4f552e3 (laptop baseline).

### 11. Order wins (Reg 30 disclosures) — NULL
1,638 order-win events (NSE "Bagging/Receiving of orders/contracts", clustered per stock, 5-day
gap), 2024→2026 — the category only exists from 2024; earlier wins were filed under general
categories and are not in this sample. Order values extracted from the PDFs (rule_v1, 1,524 of
2,519 filings); size = value / last already-public fiscal-year revenue. Follower enters the day
after disclosure; vs NIFTY 500; same-stock control 60 trading days away.

| | All | Orders ≥25% of revenue |
|---|---|---|
| Announcement day T-1→T0 (not tradable) | **+0.86%** (t=10.4) | **+2.0%** (t=7.2), 66% up |
| Follower +1d | −0.15% (t=−2.1) | — |
| Follower +5d | −0.25%, median −1.0% | median −1.0% |
| Follower +20d | −0.17%, median −1.9% | median −1.3% |
| Control +20d | +0.36%, median −1.5% | |

Priced on the day — even the biggest surprises — and a follower does slightly worse than the
control. Public news with no barrier, like `index_rebalance`. (`scanner/orderwins.py`,
`scripts/validate_order_wins.py`.) *Evidence:* `evidence/order_wins/2026-09-24` · sha 4f552e3 (laptop baseline).

## Data infrastructure findings (free stack, residential IP)
- yfinance proven for `.NS`; **nselib** reaches historical/delisted symbols (filter
  `Series=='EQ'`); jugaad-data fallback.
- NSE JSON APIs (insider/PIT, historical deals) are **JS-gated → empty/503**. NSE **static
  archive CSVs** (bulk/block deals) are the free path.
- screener.in (fundamentals) and chittorgarh (buybacks) are scrapable from a residential IP.
- **Kite Connect is not needed** for an EOD scanner; the free stack does the job.

## What's kept
The platform (`scanner/`, 53 tests), the event-study harness, the smart-money classifier,
and these verdicts baked into `scanner/catalog.py`. Recover the prior concluded project at
git `30f1f1e` if ever needed.

## Open / next
- P2: Supabase persistence + outcome tracking (calibrate acceptance estimates from realized
  tenders).
- P3: React dashboard (verdict-aware).
- Refine `buyback_arb` selection: add market cap / issue size / retail-% and an
  acceptance-estimation model.
