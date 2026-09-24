# CANDIDATE_SIGNALS — the testing backlog

Untested signals to validate **one by one** through the event-study harness
(`scanner/eventstudy.py` + `scripts/validate_*.py`). Ordered by the platform thesis:

> **Edge survives only where a structural barrier puts retail on the inside.**
> Drift-prediction from public signals → expect null. Efficiently-priced spreads → expect thin.
> Forced-flow / reservation / supply-overhang events → the only place to *expect* edge.

Already validated (don't re-test): `buyback_arb` (conditional edge), `merger_arb` (thin),
`mean_reversion` (null), `smart_money_deals` (null), `open_offer_arb` (null). See `CONCLUSIONS.md`.

**Legend** — Bucket: 🟢 structural/forced-flow (test first) · 🟡 event/over-reaction · 🔵 spread · ⚪ drift/calendar (cheap, expect null).
Data: ✅ reachable on our free stack · ⚠️ partially (gated/manual) · ❌ blocked.
Prior = honest expectation before testing.

---

## Tier 1 — Structural / forced-flow (thesis says: *here is where edge can live*)

| # | Signal | Bucket | Data | Prior | How to test |
|---|---|---|---|---|---|
| 1 | ~~**Index rebalance front-run** — NIFTY 50 / Next 50 inclusions & exclusions force index-fund buying/selling on a known effective date.~~ **TESTED → NULL (2026-06-24).** n=151 verified Next 50 events; front-run earns ~0 (tight window flat); lone deletion-rebound was a 2021-22 regime artifact. Pre-announced ⇒ arbitraged before a follower can act (no barrier excludes competitors). See `CONCLUSIONS.md` §5, `scripts/validate_index_rebalance.py` + `segment_index_rebalance.py`. | 🟢 | ✅ done | ~~most promising~~ → **null** | — |
| 2 | ~~**Anchor / pre-IPO lock-in expiry overhang**~~ **TESTED → CONDITIONAL (2026-09-24).** Real, control-verified dip T-1→T+2 (90d −1.25%, t=−4.6; 30d −0.7%; placebo ~0; holds 2022-26). Not shortable by retail (new IPOs not in F&O) → avoid/exit-timing lens `lockin_expiry`. Pre-IPO (6-mo/18-mo promoter) lock-ins not yet tested. See `CONCLUSIONS.md` §6. | 🟢 | ✅ done | ~~plausible edge~~ → **real, unshortable** | — |
| 3 | **Delisting / reverse-book-building arb** — promoter delisting via RBB; retail tenders at discovered price, floor price often revised up; failed-delisting re-rating. | 🟢 | ⚠️ chittorgarh/NSE delisting announcements (manual list) | structural (retail tender mechanics, like buybacks) — worth a hard look | Collect completed delistings; measure floor→final discovered price and post-announcement drift. |
| 4 | **Rights-entitlement (RE) mispricing** — REs trade in their own NSE series during the rights window; often illiquid & priced off theoretical (cum-rights − rights price). | 🟢 | ⚠️ nselib RE-series prices + NSE corp-action terms | spread-ish but structurally retail-accessible | For each rights issue, compare RE market price vs theoretical entitlement value; measure capturable gap after costs. |
| 5 | **ASM / GSM surveillance entry-exit** — entering Additional/Graded Surveillance forces 100% margin & trade-to-trade → liquidity shock; exit → relief bounce. | 🟢 | ✅ NSE ASM/GSM static lists + prices | forced-margin shock → mean-revert on exit; test both legs | Event study on entry date (drift down?) and exit date (bounce?). |
| 6 | **F&O ban-period reversal** — stock crossing 95% MWPL enters ban (no fresh F&O); forced unwind → over-extension that reverts on ban exit. | 🟢 | ✅ NSE daily F&O ban list + prices | over-reaction during ban → revert; cheap to test | Compare returns during ban vs post-ban-exit window. |

## Tier 2 — Corporate-action over-reaction (retail behavioural, mixed priors)

| # | Signal | Bucket | Data | Prior | How to test |
|---|---|---|---|---|---|
| 7 | **Promoter open-market buying (SAST/insider)** — promoter/insider buying own stock from open market (distinct from the null bulk/block-deal signal). | 🟡 | ⚠️ BSE/NSE insider-trading disclosures (JSON often gated; BSE CSV path?) | promoter conviction *may* beat generic institutional — but same front-run risk → guard | Same harness as `smart_money_deals` but filtered to promoter/insider acquirers; post-disclosure abnormal return. |
| 8 | **Pledge-release signal** — sharp drop in promoter pledged % (deleveraging) as a positive structural de-risking event. | 🟡 | ⚠️ quarterly shareholding / pledge disclosures (screener/BSE) | thin; low-frequency | Event study around pledge-% reduction disclosures. |
| 9 | **Bonus / stock-split announcement drift** — retail over-reacts to "cheaper" shares; pre-record-date run-up, post-drift. | 🟡 | ✅ NSE corp-actions + prices | likely null (well-known); cheap control | Abnormal return announcement→record and record→T+20. |
| 10 | **Demerger / scheme-of-arrangement value unlock** — when-issued & post-listing re-rating of demerged entity. | 🟡 | ⚠️ corp-action + manual deal list | event-driven, low-frequency, possible unlock | Study parent + child returns around record/listing. |
| 11 | **IPO listing-day & post-listing drift** — first-day pop and 1–4 week drift (GMP vs listing vs 1-month). | 🟡 | ✅ chittorgarh (GMP, issue price, listing) + prices | listing pop real but uncapturable by retail at allotment; post-listing drift likely null | Measure issue→listing and listing→T+20; can't act on allotment, so post-listing is the testable leg. |

## Tier 3 — Spreads (thesis says: expect thin / efficiently priced)

| # | Signal | Bucket | Data | Prior | How to test |
|---|---|---|---|---|---|
| 12 | **Cash-futures basis** — single-stock / index futures premium-discount vs fair carry; roll-period dislocations. | 🔵 | ⚠️ needs F&O EOD (NSE bhavcopy F&O) | thin, competed; carry ≈ risk-free | Compute basis vs cost-of-carry; flag |dislocation| > costs. |
| 13 | **NSE–BSE dual-listing spread** | 🔵 | ✅ yfinance/nselib both venues | ~0 (arbitraged in ms) | Daily close spread; almost certainly null — documents efficiency. |
| 14 | **ADR/GDR vs local** — INFY/WIT/HDB/IBN vs NSE close (FX-adjusted). | 🔵 | ✅ yfinance both | efficient; FX + time-zone noise | Overnight gap study; expect null. |

## Tier 4 — Drift / calendar (cheap to run, thesis says: expect null — run as controls)

| # | Signal | Bucket | Data | Prior | How to test |
|---|---|---|---|---|---|
| 15 | **PEAD (post-earnings drift)** — drift after large earnings surprise. | ⚪ | ⚠️ earnings dates + actual/estimate (screener; estimates weak) | classic anomaly, but estimate data is the bottleneck in India | Surprise proxy (price gap on results day) → T+20 drift. |
| 16 | **52-week-high breakout momentum** | ⚪ | ✅ prices | likely null after costs | Forward return after new 52wk high vs benchmark. |
| 17 | **Turn-of-month / Monday seasonality** | ⚪ | ✅ NIFTY prices | null (control) | Mean return by calendar bucket. |
| 18 | **Event-day vol (Budget / RBI policy / election)** | ⚪ | ✅ prices + known dates | not a trade; characterise only | Realised vol around scheduled macro events. |
| 19 | **Sector pair / cointegration mean-reversion** | ⚪ | ✅ prices | drift-family → expect null | Cointegrate sector pairs; z-score reversion backtest with costs. |

---

## Suggested order to actually test (highest expected-value-per-hour first)

1. **#1 Index rebalance front-run** — cleanest forced-flow, fully reachable, strong prior. Start here.
2. ~~**#2 Lock-in expiry overhang**~~ — done: real dip, not shortable (lens).
3. **#5 ASM/GSM** + **#6 F&O ban** — both fully reachable from NSE static lists, quick to run together.
4. **#3 Delisting RBB** — structural like buybacks; worth the manual data collection.
5. **#4 Rights-entitlement** — structural + retail-accessible; needs RE-series price plumbing.
6. Everything in Tier 3/4 as **cheap controls** (run to document efficiency, not to find edge).

## Testing protocol (per signal — keep it honest)
- Write the arb/abnormal-return math as a **pure, tested function first** (TDD — see `buyback.py`).
- Build the event set from a **verified source** (guard against delisted-ticker garbage, warrant-series mis-picks).
- Run `forward_abnormal_return` vs NIFTY over multiple horizons (T+1→T+5/20/60), report mean/median/%-positive/t-stat.
- Net **realistic costs** (≈30 bps round-trip + STT + impact for small-caps) before any verdict.
- Add a **placebo/control** leg where possible (the `smart_money_deals` prop-buy placebo is the template).
- Register the result in `scanner/catalog.py` with its `SignalMeta` verdict — **null results get logged, not deleted.**
