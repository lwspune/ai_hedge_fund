# CANDIDATE_SIGNALS — the testing backlog

Untested signals to validate **one by one** through the event-study harness
(`scanner/eventstudy.py` + `scripts/validate_*.py`). Ordered by the platform thesis:

> **Edge survives only where a structural barrier puts retail on the inside.**
> Drift-prediction from public signals → expect null. Efficiently-priced spreads → expect thin.
> Forced-flow / reservation / supply-overhang events → the only place to *expect* edge.

Already validated (don't re-test): `buyback_arb` (conditional edge), `merger_arb` (thin),
`mean_reversion` (null), `smart_money_deals` (null), `open_offer_arb` (null), `ofs_retail` (thin, #23). See `CONCLUSIONS.md`.

**Legend** — Bucket: 🟢 structural/forced-flow (test first) · 🟡 event/over-reaction · 🔵 spread · ⚪ drift/calendar (cheap, expect null).
Data: ✅ reachable on our free stack · ⚠️ partially (gated/manual) · ❌ blocked.
Prior = honest expectation before testing.

---

## Tier 1 — Structural / forced-flow (thesis says: *here is where edge can live*)

| # | Signal | Bucket | Data | Prior | How to test |
|---|---|---|---|---|---|
| 1 | ~~**Index rebalance front-run** — NIFTY 50 / Next 50 inclusions & exclusions force index-fund buying/selling on a known effective date.~~ **TESTED → NULL (2026-06-24).** n=151 verified Next 50 events; front-run earns ~0 (tight window flat); lone deletion-rebound was a 2021-22 regime artifact. Pre-announced ⇒ arbitraged before a follower can act (no barrier excludes competitors). See `CONCLUSIONS.md` §5, `scripts/validate_index_rebalance.py` + `segment_index_rebalance.py`. | 🟢 | ✅ done | ~~most promising~~ → **null** | — |
| 2 | ~~**Anchor / pre-IPO lock-in expiry overhang**~~ **TESTED → CONDITIONAL (2026-09-24).** Real, control-verified dip T-1→T+2 (90d −1.25%, t=−4.6; 30d −0.7%; placebo ~0; holds 2022-26). Not shortable by retail (new IPOs not in F&O) → avoid/exit-timing lens `lockin_expiry`. Pre-IPO (6-mo/18-mo promoter) lock-ins not yet tested. See `CONCLUSIONS.md` §6. | 🟢 | ✅ done | ~~plausible edge~~ → **real, unshortable** | — |
| 3 | ~~**Delisting / reverse-book-building arb**~~ **PARKED (2026-09-24): data not reachable** — no free automatable source of offers + discovered prices (chittorgarh none, BSE 403, NSE gated, SEBI no category). Needs manual PDF curation; post-Sep-2024 fixed-price route likely compresses the premium. See `CONCLUSIONS.md` §9. | 🟢 | ❌ | structural, but unmeasurable for now | manual curation only |
| 4 | ~~**Rights-entitlement (RE) mispricing**~~ **TESTED → CONDITIONAL (2026-09-24).** REs trade ~3.4% (median, non-penny liquid days) below fair S − issue price, every era 2020-26, 34/40 issues. Capturable without shorting if you want/hold the stock (buy RE + subscribe / switch). Live: `scanner.run rights_re`. See `CONCLUSIONS.md` §8. | 🟢 | ✅ done | ~~spread-ish~~ → **conditional, actionable** | — |
| 5 | **ASM / GSM surveillance entry-exit** — entering Additional/Graded Surveillance forces 100% margin & trade-to-trade → liquidity shock; exit → relief bounce. **Data unlocked 2026-09-24:** `api/reportASM|GSM` JSON works from runners; snapshot only (no entry dates), captured daily into `surveillance_daily` since 2026-09-24 → testable once ~6-12 months of entries/exits exist. | 🟢 | ✅ daily snapshot accruing | forced-margin shock → mean-revert on exit; test both legs | Event study on entry date (drift down?) and exit date (bounce?). |
| 6 | ~~**F&O ban-period reversal**~~ **TESTED → NULL (2026-09-24).** n=920 episodes 2020-26: the pre-ban move doesn't reverse at entry/during/exit/post (|t|<1, no better than same-stock controls); flickers are fat-tail means or single-era. Ban blocks derivatives, not the cash market → no barrier. See `CONCLUSIONS.md` §7. | 🟢 | ✅ done | ~~over-reaction → revert~~ → **null** | — |

| 20 | ~~**Preferential-allotment lock-in expiry**~~ **TESTED → NULL (2026-09-24).** n=1,394 tranches 2023-26: 6-month event T-1→T+2 −0.24% (t=−1.2) = same-stock placebo; 18-month promoter tranches −0.63% (t=−2.1, inside costs); no recovery leg. Pref allottees are strategic holders, not forced sellers — the anchor-unlock mechanism needs a holder who must exit. `CONCLUSIONS.md` §14. | 🟢 | ✅ done | ~~real dip likely~~ → **null** | — |
| 21 | **Pledge invocation → forced sale** — a lender invoking pledged promoter shares sells into the market; no pre-announcement, nobody can front-run, retail can buy the dip. | 🟢 | ⚠️ PIT forward feed only (`insider_trades` txn_type Pledge/Invocation, from May-2026) | dip real, rebound unknown | Event study at disclosure once ≥ ~50 invocations accrue; contrast with pledge release (#8). |
| 23 | ~~**OFS retail quota**~~ — 10% of every offer for sale reserved for retail bids (≤ ₹2 lakh) at/above the floor set by the non-retail book the day before. **TESTED → THIN (2026-09-24).** n=26 floors within 15% of the pre-close (2025-26): T+1 close vs floor +1.9% median (+1.6% net, 69% up, t=2.3); the pooled +3% is floors set 20-40% below market whose books cleared far above the floor (cut-off unrecorded). One era, one-day capital, pro-rata allotment. Watch: bid at the floor only in a name you want. `CONCLUSIONS.md` §15. | 🟢 | ✅ chittorgarh `/ofs/x/<id>/` (2025→) | ~~reservation → edge~~ → **thin** | — |

## Tier 2 — Corporate-action over-reaction (retail behavioural, mixed priors)

| # | Signal | Bucket | Data | Prior | How to test |
|---|---|---|---|---|---|
| 7 | ~~**Promoter open-market buying (SAST/insider)**~~ **TESTED → NULL (decayed, 2026-09-24).** Worked 2020-23 (+60d median ~+5%) but 2024-26 big-stake/cluster buys −1.0%/−1.6% median; pooled mean is a small-cap fat tail. Data: NSE `corporate-sast-reg29` (reachable from cloud). **New idea to pre-register:** promoter *sells* 2024-26 −5.8% median (flips sign vs 2022-23). See `CONCLUSIONS.md` §10. | 🟡 | ✅ done | ~~conviction~~ → **null** | — |
| 22 | ~~**Promoter open-market SELLS**~~ **TESTED → NULL (2026-09-24, pre-registered).** n=1,131 clusters 2020-26: +60d +0.0% pooled (t=0.0); −4.0% in 2024-26 (t=−4.6) but +4.7% in 2022-23 (t=+3.1) — sign flips every era; same-stock placebo medians match. `CONCLUSIONS.md` §13. | 🟡 | ✅ done | ~~thin/null~~ → **null** | — |
| 8 | **Pledge-release signal** — sharp drop in promoter pledged % (deleveraging) as a positive structural de-risking event. **Data unlocked 2026-09-24:** quarterly `pledge_pct_of_promoter` from SHP XBRL in `shareholding` (backfilling 2020→); PIT feed carries Pledge / Pledge Revoke / Invocation transactions going forward. | 🟡 | ✅ `shareholding` (quarterly), `insider_trades` (forward) | thin; low-frequency | Event study around pledge-% reduction disclosures. |
| 9 | **Bonus / stock-split announcement drift** — retail over-reacts to "cheaper" shares; pre-record-date run-up, post-drift. | 🟡 | ✅ NSE corp-actions + prices | likely null (well-known); cheap control | Abnormal return announcement→record and record→T+20. |
| 10 | ~~**Demerger listing flow** — the newly listed child is dumped in its first sessions (index funds / holders who don't want it); nobody can front-run a listing.~~ **TESTED → CONDITIONAL lens (2026-09-24).** n=64 children (61 demergers, 2019-26, hand-curated `data/demerger_listings.csv`): first 5 sessions **−5.9% median vs NIFTY 500** (t=−2.8 clustered; same-child placebo flat; −10% in 2022-23, −5.6% in 2024-26). Mechanism cut fails — index-parent children −1.4% (n.s.), small/non-index parents −6 to −10% — so it is holder dumping, not index flow. Unshortable (T2T, no F&O); buy-after-T+5 median −0.9% (fat-tail mean). Lens: don't buy a child in its first week. `CONCLUSIONS.md` §16. | 🟢 | ✅ done | ~~possible unlock~~ → **real dip, no trade** | — |
| 11 | **IPO listing-day & post-listing drift** — first-day pop and 1–4 week drift (GMP vs listing vs 1-month). | 🟡 | ✅ chittorgarh (GMP, issue price, listing) + prices | listing pop real but uncapturable by retail at allotment; post-listing drift likely null | Measure issue→listing and listing→T+20; can't act on allotment, so post-listing is the testable leg. |

## Tier 3 — Spreads (thesis says: expect thin / efficiently priced)

| # | Signal | Bucket | Data | Prior | How to test |
|---|---|---|---|---|---|
| 12 | **Cash-futures basis** — single-stock / index futures premium-discount vs fair carry; roll-period dislocations. | 🔵 | ⚠️ needs F&O EOD (NSE bhavcopy F&O) | thin, competed; carry ≈ risk-free | Compute basis vs cost-of-carry; flag |dislocation| > costs. |
| 24 | **Results-day implied vol vs realised move** (logged 2026-09-24) — the only options idea consistent with the thesis, and only as a *falsification test*, not a strategy review. Is single-stock IV before a results date systematically above the realised move, and does the excess survive the bid-ask spread? A variance risk premium is compensation for tail risk, not a barrier: nobody is excluded from NSE options, prop desks sell the same premium cheaper, and SEBI 2024-25 (~₹15 lakh min contract, one weekly expiry per exchange, higher STT, upfront premium) raised the retail floor. Options also can't hedge the buyback slab (one lot ≈ 7× a ₹2 lakh position) nor short the unshortable lenses (fresh listings aren't in F&O — §6, §16). **Do not** review covered calls / condors / straddle-selling generally: payoff shapes, not edges. | 🔵 | ⚠️ needs F&O EOD (NSE F&O bhavcopy is a static archive → should reach runners like the cash bhavcopy; results dates already in `corporate_events` `board_meeting`/`results`) | competed risk premium; expect null after spreads outside the top ~30 names | Event set = results dates ∩ F&O list (point-in-time). Pre-specified cut: ATM straddle price at T-1 close vs |close-to-close move| T-1→T+1, net of the quoted spread; segment top-30 liquid names vs the rest, and 2022-23 vs 2024-26 (post-SEBI). Verdict is *null* unless the excess survives both cuts; even then it is a risk premium (lens), never an Act signal. |
| 13 | **NSE–BSE dual-listing spread** | 🔵 | ✅ yfinance/nselib both venues | ~0 (arbitraged in ms) | Daily close spread; almost certainly null — documents efficiency. |
| 14 | **ADR/GDR vs local** — INFY/WIT/HDB/IBN vs NSE close (FX-adjusted). | 🔵 | ✅ yfinance both | efficient; FX + time-zone noise | Overnight gap study; expect null. |

## Tier 4 — Drift / calendar (cheap to run, thesis says: expect null — run as controls)

| # | Signal | Bucket | Data | Prior | How to test |
|---|---|---|---|---|---|
| 15 | **PEAD (post-earnings drift)** — drift after large earnings surprise. (2026-09-24: NSE `corporates-financial-results` serves only the latest quarter per window — no history; still ⚠️.) | ⚪ | ⚠️ earnings dates + actual/estimate (screener; estimates weak) | classic anomaly, but estimate data is the bottleneck in India | Surprise proxy (price gap on results day) → T+20 drift. |
| 16 | **52-week-high breakout momentum** | ⚪ | ✅ prices | likely null after costs | Forward return after new 52wk high vs benchmark. |
| 17 | ~~**Turn-of-month / Monday seasonality**~~ **TESTED → NULL (2026-09-24).** Last-1 + first-3 trading days vs the rest, NIFTY 50 / NIFTY 500 (cloud closes 2022-08→): the TOM premium lived in 2022-23 (NIFTY 500 +0.34%/day, t=3.9) and is ~0 in 2024-26 (+0.00%/day, t=0.0); pooled +0.46%/mo window, t=1.8, inside an era cut. `scripts/validate_turn_of_month.py` (evidence on Actions). | ⚪ | ✅ done | ~~null (control)~~ → **null** | — |
| 18 | **Event-day vol (Budget / RBI policy / election)** | ⚪ | ✅ prices + known dates | not a trade; characterise only | Realised vol around scheduled macro events. |
| 19 | **Sector pair / cointegration mean-reversion** | ⚪ | ✅ prices | drift-family → expect null | Cointegrate sector pairs; z-score reversion backtest with costs. |

---

## Suggested order to actually test (highest expected-value-per-hour first)

1. **#1 Index rebalance front-run** — cleanest forced-flow, fully reachable, strong prior. Start here.
2. ~~**#2 Lock-in expiry overhang**~~ — done: real dip, not shortable (lens).
3. **#5 ASM/GSM** (unblocked 2026-09-24: daily snapshot accruing; test in 2027) + ~~**#6 F&O ban**~~ (done: null).
   ~~#20 pref lock-in expiry~~ done: null (strategic allottees aren't forced sellers); ~~#22 promoter sells~~ done: null.
4. ~~**#3 Delisting RBB**~~ — parked: data not reachable (manual curation only).
5. ~~**#4 Rights-entitlement**~~ — done: conditional, actionable (RE discount ~3%).
6. Everything in Tier 3/4 as **cheap controls** (run to document efficiency, not to find edge).
   **#24 results-day IV** sits at the bottom, next to #12: it needs an F&O bhavcopy loader first and
   a null is the expected outcome. Options strategies in general are **declined** (2026-09-24, see #24).

## Testing protocol (per signal — keep it honest)
- Write the arb/abnormal-return math as a **pure, tested function first** (TDD — see `buyback.py`).
- Build the event set from a **verified source** (guard against delisted-ticker garbage, warrant-series mis-picks).
- Run `forward_abnormal_return` vs NIFTY over multiple horizons (T+1→T+5/20/60), report mean/median/%-positive/t-stat.
- Net **realistic costs** (≈30 bps round-trip + STT + impact for small-caps) before any verdict.
- Add a **placebo/control** leg where possible (the `smart_money_deals` prop-buy placebo is the template).
- Register the result in `scanner/catalog.py` with its `SignalMeta` verdict — **null results get logged, not deleted.**

## Tested from the filings layer
| # | Signal | Verdict |
|---|---|---|
| 9 | ~~**Order-win drift**~~ (Reg 30 order disclosures, sized vs revenue) | **NULL (2026-09-25)** — priced on announcement day (+0.9%; +2.0% for orders ≥25% of revenue); follower +1/+5/+20d ≈ 0 to negative, below controls; n=1,638 (2024-26). `CONCLUSIONS.md` §11. |
