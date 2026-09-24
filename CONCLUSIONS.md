# CONCLUSIONS — Indian Market Inefficiency Validations

**Status: active platform. Five signals validated. One real edge found.**

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
