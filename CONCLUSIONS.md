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
101 tender buybacks (record dates Dec-2022 → Jul-2026, incl. the 2026 tenders recovered by the
chittorgarh format fix), ₹2L, **unadjusted closes** (cloud price store), **entry at the last
cum-entitlement close** (the session before the record date — see the 2026-09-24 correction
note; the record date itself is ex-entitlement under T+1), residual sold 21 trading days after
close. Re-run 2026-09-24 after the backtest review:

| Scenario | Mean | Median | Win |
|---|---|---|---|
| Record-day (ex) close vs the cum entry | −2.9% | −2.7% | 11% |
| Buyback premium vs entry | +19.6% | +18.1% | 99% |
| Gross @ entitlement floor | −1.3% | **−2.3%** | 43% |
| Gross @ 3× entitlement (high-acceptance) | +2.9% | **+3.0%** | 60% |
| After-tax today's rules, 30% slab — floor | −3.7% | −3.8% | 32% |
| After-tax today's rules, 30% slab — 3× | −2.7% | **−3.2%** | 34% |
| After-tax today's rules, 20% slab — 3× | +1.3% | **+1.3%** | 57% |
| After-tax today's rules, 5% / 0% slab — 3× | +7.3% / +9.3% | +8.2% / +8.9% | 67% / 73% |

Blind tendering **loses** ~2% at the floor; the high-acceptance (3×) case earns ~+3% gross, which
the Oct-2024 dividend tax turns into **−3% at a 30% slab, ~+1% at 20%, +8-9% at a ≤5% slab**.
So the edge survives only for a **nil / 5%-slab ₹2L account** (family members without other
income), and even there only on **selected high-acceptance, high-premium tenders** (the
structural 15% small-shareholder reservation — barred to institutions — is what makes acceptance
high). At 20% it is thin; at 30% it is negative. The low-slab rows assume the accepted shares'
cost is used as a capital loss **against other short-term gains** (credited at the 20% STCG rate
in `after_tax_return`); without gains to offset, that benefit only carries forward. **Still the
one structural signal, but its actionable envelope is now narrow: the right account, the right
tender.**

*Realized acceptance (2026-09-24):* the post-buyback public announcements each company files on NSE
carry the actual response table, and 24 of the 106 settled tenders since 2023 parse cleanly (65 are
newspaper scans awaiting hand entry, 17 not yet announced). **Small-shareholder acceptance is ~50%
flat across market-cap buckets** — 52% (small, n=9), 59% (small/mid, n=8), 16% (mid, n=2), 51%
(large, n=5); median 42%, range 6% (Symphony) to 100% (IITL, Triveni, SIS-2025, Weizmann). The
"small-caps ≈ 90%, large-caps ≈ 12%" prior the selection model used was a guess in both directions
and is retired for a flat 45%. Practical reading: the "3×" high-acceptance case above is the
*top half* of tenders, not a small-cap property; the six 2026 tenders hint that a bigger premium
draws more retail tendering (Go Colors 19% premium → 23% accepted; IITL 1.6% → 100%), which is the
next calibration question. (`scanner/buyback_results.py`, `python -m scanner.calibrate`.)

*Correction note (2026-09-24):* the original table (n=48: floor median −0.1%, 3× median
+6.4%, 3× mean +23%) used yfinance closes, which are back-adjusted for later splits/bonuses
while the buyback price is nominal (SPORTKING's 1:10 split showed as a "+1282%" premium),
and a cache that had silently dropped 29 events. Medians barely moved; the inflated means
did. Verdict unchanged; the tax-slab condition is new.
*Update (2026-09-24, n=81 → 101):* the table now includes 2026's tenders and prices from the cloud
store. Every reading holds: floor median +0.4% → −0.2%, 3× median +5.4% → +4.9%, 30%-slab 3×
median −1.5% → −0.8%, 20%-slab 3× +3.8% (unchanged). A new as-of market-cap cut at *floor*
acceptance (small −1.4%, n=26 … large +6.1%, n=14) is not a test of the acceptance prior — small-caps
earn through near-100% acceptance, which only logged outcomes can measure.
*Correction note (2026-09-24, backtest review — the one that changed the reading):* every earlier
table entered at the **record-day close**. Under T+1 settlement (all stocks from 2023-01-27) the
record date is the ex-date: a buyer must own the shares the session before, and the record-day
close is an ex-entitlement price that already lacks the tender's value — stocks fall a median 2.7%
that day (11% rise). The old tables therefore booked the entitlement's own value as premium.
Entry is now `buyback.last_buy_close` (T+1: record −1 session; T+2: record −2). Effect on the
medians: floor −0.2% → −2.3%; 3× +4.9% → +3.0%; 20%-slab 3× +3.8% → +1.3%; 30%-slab 3× −0.8% →
−3.2%. The as-of market-cap cut at floor acceptance keeps its shape (small −6.2%, n=26 … large
+5.5%, n=14). Same lesson for every record-date study (demerger, rights, dividends).
*Evidence:* pre-correction `evidence/buyback_arb/2026-09-24T073956Z` (Actions re-run); laptop
event list `evidence/buyback_arb/2026-09-24` · sha 4f552e3; corrected run published from Actions
after this commit (see `validation_runs`).

### 4. Stock-swap merger arb — THIN
3 verified completed deals (HDFC, LTIMindtree, Shriram): announcement spreads +2.7/2.4/6.7%
(mean +3.9%, ~4.6% annualised *gross*). Efficiently priced; before futures carry and the
deal-break tail (Zee-Sony). Unattractive for retail. (Open-offer arb, Form A, is a
structural null — no small-shareholder reservation — kept only as the control that proves
why buybacks work.)

### 5. Index-rebalance front-run (NIFTY 50 / Next 50 reconstitution) — NULL
Buy index additions / short deletions on the announcement, exit at the effective date.
Event study over **149 verified NIFTY Next 50 clean entries/exits, 2018→2025** (announce +
effective dates extracted verbatim from niftyindices.com press-release PDFs; promotion/
relegation and ad-hoc/merger events excluded as confounded; 2 events with a bonus/split inside
the window dropped — see correction note), benchmark-adjusted vs NIFTY. `t` treats events as
independent; `t_cl` clusters by review (16 reviews), since every event of a review shares dates:

| Window | Adds (long) | Drops (short) | Combined |
|---|---|---|---|
| announce+1 → effective | +1.88% (t=1.3, t_cl=1.5), median +1.0% | −0.12% (t=−0.1) | +0.88% (t=0.9, t_cl=0.9) |
| **effective−5 → effective** (forced-flow window) | +0.06% | −0.03% | **+0.02% (t=0.0)** |
| effective → effective+5 (reversal) | −0.01% | −1.54% (t=−2.4, t_cl=−2.0) | −0.77% (t=−1.8, t_cl=−2.1) |

The front-run is **null** — even the tight window where funds are forced to trade is flat.
*Correction note (2026-09-24, backtest review):* the original table (n=151, adds wide +0.83%)
read unadjusted closes with no corporate-action guard; BEL's 2:1 bonus of 2022-09-15 sat inside
its Sep-2022 add window and counted as −66%. `rebalance.drop_blocked` now removes such events
(BEL, MOTHERSON). The adds wide mean roughly doubles but stays inside noise; nothing else moves.
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
*Evidence:* re-run on Actions `evidence/rights_re/2026-09-24T073019Z` (reproduces: non-penny median +3.52%, 48/55 issues above hurdle); laptop baseline `evidence/rights_re/2026-09-24` (+ RE closes zip) · sha 4f552e3.

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

### 12. Turn-of-month seasonality (backlog #17) — NULL (control)
Last 1 + first 3 trading days of each month vs all other days, NIFTY 50 and NIFTY 500 unadjusted
index closes from the cloud store (2022-08 → 2026-09; truncated edge months excluded). Run on Actions.

| NIFTY 500 | TOM days (%/day) | other days (%/day) |
|---|---|---|
| pooled | +0.11% (n=199, t=1.5) | +0.03% (n=810) |
| 2022-23 | **+0.34% (t=3.9)** | +0.02% |
| 2024-26 | +0.00% (t=0.0) | +0.04% |

The pooled TOM window is +0.46%/month (t=1.8), all of it from 2022-23; NIFTY 50 reads the same
(+0.29% t=3.0 → −0.04% t=−0.4). A calendar effect with no barrier, gone in the current era — the
external "marginal pass" (NIFTYBEES 2021-26, +0.9%/yr gross) is this flicker. Documented, not traded.
(`scanner/seasonality.py`, `scripts/validate_turn_of_month.py`.) *Evidence:*
`evidence/turn_of_month/2026-09-24T083330Z` (Actions).

### 13. Promoter open-market selling (Reg 29, pre-registered leg of §10) — NULL (era-unstable)
Hypothesis registered 2026-09-24 before the run: a promoter open-market sale cluster predicts
underperformance vs NIFTY 500 over +20/+60d, pooled and in 2024-26. n=1,131 clusters (2020-26),
entry the day after disclosure; contrast legs non-promoter sells (1,400) and promoter buys (1,744);
same-stock 20-day placebo windows. Run on Actions.

| promoter sells | +20d | +60d | placebo pre / post (20d) |
|---|---|---|---|
| pooled | +0.2% (median −1.8%, t=0.4) | **+0.0%** (median −3.5%, t=0.0) | +1.2% (t=2.5) / +0.5% |
| 2020-21 | +1.7% | +3.0% | |
| 2022-23 | −0.1% | **+4.7% (t=+3.1)** | |
| 2024-26 | −0.5% | **−4.0% (t=−4.6, 37% up)** | |

Cluster / stake-size cuts are all within ±1%. The 2024-26 leg looks like the §10 contrast
(−5.8% median) but the sign has now flipped in every era (+, +, −), and the negative medians
also appear in the placebo windows of the same stocks (small-cap drift, not the event). A public
disclosure with no barrier — null, like promoter buying. Not a trade; at most an "avoid adding"
lens. (`scripts/validate_promoter_sells.py`.) *Evidence:*
`evidence/promoter_sells/2026-09-24T090701Z` (Actions).

### 14. Preferential-allotment lock-in expiry (#20) — NULL (the anchor mechanism doesn't transfer)
Every lock-in tranche from NSE further-issues listing XBRLs (`pref_issues`, Mar-2023 →): 1,455
expiries, 1,394 usable (0 ICDR-default rows), unadjusted cloud closes vs NIFTY 500, split/bonus
windows dropped, mcap as of the event. Run on Actions.

| window | 6-month (n=1,027) | 18-month promoter (n=302) |
|---|---|---|
| pre T-10→T-1 | +0.08% | −0.56% |
| **event T-1→T+2** | **−0.24% (t=−1.2)**, median −0.75% | **−0.63% (t=−2.1)**, median −0.66% |
| post T+2→T+10 | −0.04% | −0.37% |
| recovery T+2→T+20 | −0.37% (t=−0.8) | −0.12% |
| placebo 3-day, same stocks | −0.08% / −0.24% | +0.54% / +0.13% |

- 6-month tranches (the bulk) are indistinguishable from their own placebo windows: null.
- 18-month promoter tranches show a −0.6% dip that clears its placebo but sits inside round-trip
  costs, and every era / segment reads −0.5 to −1.5% with |t| ≤ 3 (small_mid caps −1.5%, t=−3.0,
  n=60). No recovery leg anywhere — nothing a long buyer could harvest.
- Contrast the anchor unlock (§6: −1.25%, t=−4.6): anchors are funds allotted at the IPO who exit
  when allowed; preferential allottees are promoters / strategic investors / HNIs who chose the
  stock and are under no pressure to sell when the lock ends. **Lock-in expiry is a forced flow
  only when the locked holder wants out** — the thesis holds, with that refinement.
(`scanner/prefissues.py`, `scripts/validate_pref_lockin.py`.) *Evidence:*
`evidence/pref_lockin/2026-09-24T092623Z` (Actions).

### 15. Offer-for-sale retail quota (#23) — THIN (watch)
An OFS reserves 10% for retail bids (≤ ₹2 lakh) on day 2, at or above a floor the non-retail book
priced on day 1 — a reservation only retail can use, so the thesis says measure it. 45 OFS from
chittorgarh `/ofs/x/<id>/` (Jan-2025 →, the page's coverage floor), 34 priced from the cloud store,
everything vs the **floor** (the cut-off price is not on the page; an oversubscribed book clears
above the floor, so these numbers are an upper bound on the retail leg).

| vs floor | all (n=34) | floor within 15% of pre-close (n=26) | PSU (n=14) | private (n=12) |
|---|---|---|---|---|
| floor discount to pre-close | −8.0% median | −7.9% | −8.0% | −7.7% |
| retail-day close | +3.4% | +2.7% (88% up, t=3.6) | +1.5% | +4.7% |
| **T+1 (allotment, first sellable)** | +3.0% | **+1.9% median, +1.6% net, 69% up, t=2.3** | +1.1% | +3.8% |
| T+20 | +4.5% | +4.1% (t=1.5) | +4.1% | +3.3% |

- The pooled +3% is carried by floors set 20-40% below the market (Wendt, Eimco Elecon, HMA Agro):
  those books clearly cleared far above the floor, so the floor-based return is fiction. The
  robust cut (floor within 15%) is the honest read: **~+2% by T+1**, ~1.6% after costs.
- One era (2025-26, chittorgarh has nothing earlier), n=26, one-day capital, ≤ ₹2 lakh, and the
  retail allotment is pro-rata when the quota is oversubscribed. A PSU retail discount (when DIPAM
  grants one) is unrecorded and would add to the PSU rows.
- **Verdict: thin / watch.** Bid at the floor only in a name you would hold anyway; not a trade
  on its own. Re-test when n doubles and if a cut-off source appears.
(`scanner/ofs.py`, `scripts/refresh_ofs.py`, `scripts/validate_ofs_retail.py`, live screen
`python -m scanner.run ofs_retail`.) *Evidence:* `evidence/ofs_retail/2026-09-24T110239Z`.

### 16. Demerger listing flow (#10) — CONDITIONAL (real first-week dip, not the index mechanism, no trade)
Hypothesis: when a demerged child lists, index funds and benchmark-bound holders must sell what
they received (the child is in no index) and nobody can front-run it (the child cannot be bought
before it lists) → a forced-flow dip a retail buyer could capture after T+5. Event set:
`data/demerger_listings.csv`, 68 children of 61 demergers since 2019, curated by hand (the
corporate-action feed gives only the parent's ex-date; no free source names the child) and every
row verified against the company master's listing date or the first bhavcopy close; 27 of the 90
demerger records had no newly listed child and were excluded. 64 priced (unadjusted cloud closes,
NIFTY 500 benchmark). T = first close; windows fixed in advance; t clustered by scheme.

| Window (child vs NIFTY 500) | Mean | Median | Up | t / t_cl |
|---|---|---|---|---|
| **sell T+0→T+5** (trade-for-trade period) | **−5.0%** | **−5.9%** | 30% | −2.8 / −2.8 (by week −2.9) |
| recovery T+5→T+20 | +8.4% | −0.9% | 48% | +2.2 (fat tail: IWEL +138%, DRC +78%, NDR +76%) |
| late T+10→T+30 | +3.8% | −1.8% | 45% | +1.2 |
| placebo 5-session windows on the same children (T+60, T+120) | +1.9% / −0.6% | +0.8% / −1.4% | 53% / 43% | — |

- **The dip is real** and specific to the listing: same-length windows later in the child's life
  are flat; the raw median path sits −4.5 to −5.5% below the first close on every one of the first
  10 sessions. Era: −1% (2019-21, n=19), **−10% (2022-23, n=17, t=−3.9)**, −5.6% (2024-26, n=28,
  t=−2.2).
- **The mechanism cut fails.** Children of NIFTY 50 / Next 50 parents (n=13, curated flag): sell
  −1.4% (t=−0.5); non-index parents −5.9% (t=−2.8); by parent cap as of the ex-date: large −0.8%,
  small_mid **−10.4% (t=−4.2)**. Index-fund selling is not what moves these prices; the seller is
  the parent's own holder base dumping small unwanted allotments into a trade-for-trade book.
- **No trade.** Unshortable (T2T for 10 sessions, no F&O); the buy-after leg has a negative median
  (the mean is four multi-baggers). Index-parent recovery +4.6% median (n=13) is the one positive
  cell — too few to act on; re-test when n doubles.
- **Lens:** don't buy a demerged child in its first week; if you hold the parent through the
  record date, the child's first-week price is the wrong one to judge it by.

Thesis check: a forced flow nobody can front-run exists, but the barrier that keeps arbitrageurs
out (no short, T2T) keeps retail out too — the lock-in pattern again — and the flow is retail
dumping, not a mandate-bound institution. (`scanner/demerger.py`, `scripts/validate_demerger.py`,
`data/demerger_listings.csv`.) *Evidence:* published from Actions after this commit (`validation_runs`).

### 17. Credit-rating change — NULL (agencies follow the price)
Hypothesis: a rating action is news about default risk, so the stock reacts on the filing and
(for a slow market) keeps drifting — a downgrade as an exit / avoid rule, an upgrade as a buy.
Events: `credit_ratings` (every NSE Reg 30 rating filing 2020-26, parsed by `scanner/ratings.py`:
11,432 filings, 17,798 agency ratings, 1,537 companies) → `scanner/ratingevents.py`: domestic
long-term grade moves (size from the stated or our own previous rating), watch placements, and
**reaffirmations as the control**; T = first session after the filing (15:30 IST cut-off); one
event per symbol and kind per 30 days; corporate-action guard. Abnormal vs NIFTY 500, unadjusted
cloud closes, t clustered by event week, windows and segments fixed in advance.

| Window (vs NIFTY 500) | Downgrades n=456 | Upgrades n=1,258 | Reaffirmed n=3,456 |
|---|---|---|---|
| pre T−21→T−1 (median / mean, t_cl) | **−4.6% / −2.7%, −2.7** | −0.5% / +1.5%, +3.3 | −1.2% / −0.1%, −0.3 |
| react T−1→T+1 | −0.8% / −0.3%, **−0.9** | +0.0% / **+0.6%, +4.5** | −0.2% / +0.2%, +2.7 |
| follower +20d | −1.7% / +1.1%, +1.2 | −0.3% / +1.4%, +3.0 | −0.7% / +1.0%, +3.3 |
| follower +60d | −1.0% / +3.0%, +2.0 | −1.3% / +3.4%, +2.8 | −1.3% / +2.6%, +4.4 |
| same stock 120 sessions earlier, 20d | −3.2% / −1.5%, −2.2 | +0.3% / +2.2%, +5.0 | −1.0% / +0.6%, +2.1 |
| same stock earlier, 2d | −0.6% / −0.5%, −2.1 | −0.2% / +0.3%, +2.2 | −0.3% / +0.2%, +1.9 |

- **Downgrades carry no news.** No announcement move (t −0.9, the same stocks' random 2-day
  windows are as negative) and no drift after (medians negative, means positive: no direction).
  The fall happened first — the run-up window is barely worse than the same stock 120 sessions
  earlier (median −4.6% vs −3.2%): these are weak stocks the agency catches up with. Pre-specified
  cuts all n.s.: out of investment grade (58) react −1.0% (t −0.9), into default (31) −2.0% (t −1.1),
  2+ notches (95) −0.9%.
- **Upgrades: a small, fading bump.** +0.6% on the filing against +0.2-0.3% for reaffirmations and
  the same stocks' placebo — ~+0.3% of news, one round-trip cost; 2020-22 +0.9%, 2023-26 +0.4%.
  Nothing after: +20d is below the same stocks' own placebo (+2.2%). The positive means everywhere
  are small-cap fat tails in a bull market; medians sit at or below zero.
- Watch placements (48 negative / 38 positive) and global agencies (92 moves) n.s.
- Robust to dropping the 366 events within 2 trading days of a results meeting (downgrade react
  −0.3%, t −0.9; upgrade +0.56% vs reaffirmed +0.27%).

Thesis check: a rating is public, and the agency reacts to the same public information the market
already priced — a lagging opinion, not a barrier. Kept as data: the company page shows each
agency's current rating and history. (`scanner/ratings.py`, `scanner/ratingevents.py`,
`scripts/validate_rating_change.py`.) *Evidence:* `rating_change/2026-09-26T061849Z` (all events) and
`rating_change/2026-09-26T072017Z` (`--exclude-results-window 2`).

### 18. IPOs and the grey-market premium (#11) — THIN (a small positive lottery, decayed)
Hypothesis: the retail quota (35% of a mainboard issue, lottery-allotted one minimum lot per winner
when oversubscribed; institutions can't bid into it) is a structural barrier like the buyback's, so
one application is worth P(allotment) × listing gain. Scope: every NSE company IPO listed Feb-2020 →
Sep-2026 (1,002; 385 BSE-only issues have no free listing price, 13 REITs/InvITs excluded). Listing
gain = sell at the listing-day open (bhavcopy), after 0.2% costs. Odds: exact where chittorgarh
publishes the basis of allotment (2026); else 1.10 ÷ consolidated retail times (lots per applicant,
calibrated on 32 issues, 1.01-1.54), with older consolidated figures rebuilt from NSE's own retail bid
data ÷ 0.647 (NSE's share of retail bids, 0.51-0.72 over 32 issues) — chittorgarh keeps them behind
its paywall and that was left alone. SME: no free retail figure before 2026 and overall times is no
proxy (retail/overall 0.2-10×), so SME odds only for 7 recent issues.

| Mainboard, one application | n | Gain if allotted (median / mean) | Below issue | P(allot) median | EV per application |
|---|---|---|---|---|---|
| all 2020-26 | 416 | +9.8% / +20.2% | 28% | 14.8% | **+1.6% (≈ ₹237)** |
| 2020-22 / 2023-24 / 2025-26 | 102 / 142 / 172 | — | — | — | +1.9% / +3.1% / **+0.3%** (≈ ₹276 / ₹457 / **₹34**) |
| retail ≤ 2× | 109 | −0.2% | 55% | 100% | −0.1% |
| retail 2-10× | 130 | +9.3% | 27% | 24% | **+3.5%** (+4.0 / +5.0 / +1.6% by era) |
| retail 10-50× | 132 | +19.3% | 14% | 5.4% | +1.5% |
| retail > 50× | 44 | +38.8% | 5% | 1.7% | +0.9% |

- **The quota is real but the prize is small and shrinking.** The median application is ₹14,841;
  ~₹237 of expected profit per application pooled, ~₹34 in 2025-26 as listing gains fell (median
  +5% in 2025, 32-35% of issues below issue). The better the listing, the worse the odds — hot
  issues pay +39% at ~2%. Only multiple PANs scale it (one application each).
- **Skip undersubscribed issues:** ≤ 2× retail lists below issue 55% of the time — the one cell a
  rule can act on (the live subscription is public on the last bidding day). 2-10× is the best cell
  in every era (post-hoc cut: a hypothesis, not a finding).
- **GMP:** the last pre-listing GMP predicts the listing open (Spearman +0.87 mainboard n=407, +0.82
  SME n=441; median error −1 / −2 pts, |error| 6 / 13 pts; GMP ≤ 0 → 61% of mainboard issues below
  issue, GMP > 30% → none). But GMP *at application time* is untestable: before 2026 investorgain
  keeps only the last ~3 quotes, all after the issue closes (n=25 with a pre-close quote: ρ +0.79,
  GMP ≥ 20% → 0 of 11 below issue). Daily capture now runs → backlog #25.
- **Don't buy after listing.** Mainboard from the listing close: +5/+20/+60/+250 sessions ≈ 0 mean
  (t ≤ 1.3), medians −1.6% / −1.1% / −2.8% / **−10.5%**; the biggest pops do worst (> 50% pop: +60d
  median −8.9%). SME: mean +10% at +60 and +33% at +250 (t_cl 3) but median −8.5% / −14% and 41-45%
  up — a few multibaggers, concentrated in 2020-22 (+60d mean +41% vs +5% in 2023-26), in lots of
  ₹1-2 lakh, trade-for-trade: a lottery, not a portfolio anyone can hold.
- SME if allotted: median +14.6% at the open (mean +38%), 23% below issue; +40% median in 2024, +6% /
  +3% in 2025-26 with 37-38% below issue.

Thesis check: a barrier (the retail quota) does let retail in and keep institutions out — and the
prize has been competed down anyway: more retail money chases each issue (odds fall as pops rise),
and issuers price closer to the market. Positive, but thin. (`scanner/gmp.py`, `scanner/ipobids.py`,
`scanner/ipostudy.py`, `scripts/validate_ipo.py`.) *Evidence:* `ipo_listing/2026-09-26T101256Z`.

## Data infrastructure findings (free stack, residential IP)
- yfinance proven for `.NS`; **nselib** reaches historical/delisted symbols (filter
  `Series=='EQ'`); jugaad-data fallback.
- NSE JSON APIs (insider/PIT, historical deals) are **JS-gated → empty/503**. NSE **static
  archive CSVs** (bulk/block deals) are the free path.
- screener.in (fundamentals) and chittorgarh (buybacks) are scrapable from a residential IP.
- **Kite Connect is not needed** for an EOD scanner; the free stack does the job.

## The tally (2026-09-26)
Eighteen signals validated: 2 actionable (`buyback_arb` conditional edge — narrow after the
2026-09-24 cum-date correction, `rights_re` conditional watch), 2 real-but-unshortable lenses
(`lockin_expiry`, `demerger_listing`), 3 thin (`merger_arb`, `ofs_retail`, `ipo_listing`), 11 null
(mean_reversion, smart_money_deals, open_offer_arb, index_rebalance, fno_ban, promoter_buying,
order_wins, turn_of_month, promoter_sells, pref_lockin, rating_change).

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
