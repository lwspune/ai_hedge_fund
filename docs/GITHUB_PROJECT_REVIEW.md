# GitHub hedge-fund / investment project review — 2026-09-24

Purpose: survey public GitHub projects for (a) **data we should pull** and (b) **strategies we
should test**, judged against the platform thesis (edge lives only behind a structural barrier
that excludes competitors; drift signals → null; spreads → thin). Analysis only — nothing built.

## 1. Verdict in one paragraph

The famous repos (TradingAgents 99k★, virattt/ai-hedge-fund 63k★, Microsoft qlib 45k★,
HKUDS/Vibe-Trading 31k★, NoFx, AutoHedge) are LLM-agent or ML-factor **drift machines on US
data**. They contribute nothing to this platform: no Indian data, no structural events, and their
"strategies" are exactly the public-signal drift chasing we concluded against. The honest Indian
backtest repos independently reach our null (momentum, reversal, factors, XBRL fundamentals all
lose to an index fund). **The real payoff of this review is data, not strategies:** three India
repos have verified — two of them from GitHub Actions runners — NSE/BSE endpoints that unblock
four backlog signals and the buyback acceptance model's missing feature. Six endpoints, one
probe run, and the backlog gets four testable items plus one new structural candidate.

## 2. Projects reviewed

### 2a. Large "AI hedge fund" frameworks — not applicable

| Repo | Stars | What it is | Why it doesn't apply |
|---|---|---|---|
| TauricResearch/TradingAgents | 99k | Multi-LLM-agent "trading firm" debating SEC filings, news, charts | US, LLM opinion → drift; no measurable edge claim |
| virattt/ai-hedge-fund | 63k | Investor-persona agents + Financial Datasets API, backtest CLI | US-only paid data; personas = fundamental/technical drift |
| microsoft/qlib | 45k | ML factor platform (Alpha158/360), RD-Agent factor mining | Factor mining is the thing our nsefactor-style evidence says fails in India; heavy |
| HKUDS/Vibe-Trading | 31k | Agent + backtest engine; US/HK/CN/KR/crypto | No India; LLM-driven |
| NoFx, AutoHedge, OpenAlice | 1–13k | Signal pipelines / agent execution for crypto & US | Execution automation — we trade manually via Kite by design |

Nothing here is worth porting. Do not adopt an agent framework.

### 2b. India backtest repos — corroborate the thesis (nothing to re-test)

| Repo | What they tested | Result | Takeaway for us |
|---|---|---|---|
| md0n-cmd/indian-equity-backtests | 8 strategies, full retail costs, OOS | ORB, intraday momentum, weekly reversal, breakout, sector/size rotation **fail**; cross-sectional momentum inconclusive; turn-of-month "marginal pass" (9.0% vs 8.1% on NIFTYBEES); dual momentum Nifty/gold/cash pass (12.1% vs 9.2%, 2008-26) | Confirms Tier-4 priors. Dual momentum is asset allocation, not stock selection — out of scope. Their per-leg retail cost table (STT 0.1% both sides, DP ₹16/scrip, 0.1% slippage) is a good cross-check for our ~30 bps assumption. |
| Abhinav7582/indian-equity-research | 6 pre-registered hypotheses, Nifty 100, event-driven engine, DSR/PBO gates | H1 momentum monotonicity rejected (NW t=1.47; decile 10 negative); H2 momentum net of costs rejected (10.9% vs 17.1% TRI, loses before costs); H4 regime overlay worsened drawdown | Exactly our discipline (pre-register, era-cut, costs). **Reusable:** niftyindices press-release sweep → Nifty 100 membership 2015→ from 1,037 PDFs (we curated Next-50 by hand); a delisting register that classifies acquisition vs collapse for terminal returns. |
| AnoopIbrampur/nsefactor | 11 yrs bhavcopy, PIT universe, XBRL fundamentals | "A Nifty 500 index fund beat every variant"; XBRL fundamental factors have no predictive power; only vol forecasting worked | **Reusable:** corporate-action adjustment factors recovered from bhavcopy `prevclose` ratios — lets return studies run on the cloud store without yfinance. |
| kousikdutta-1005/market-lab | Daily CI scorer from official NSE files (same architecture as ours) | Survivorship demo: EW Nifty 200 today's members 30.1%/yr vs 9.4% actual; 12-m reversal loses 61% of the time | Reinforces `pointintime` rule. |
| shekhar-atulya/india-factor-backtest | Momentum/vol/reversal on 20 stocks, no costs | Sharpe ~1 gross | Too small, no costs — ignore. |
| sachin5678/investment-backtest | 20 SIP/rotation backtests, reconstructs NIFTY200 Momentum 30 etc. | Curves only | Ignore. |

**Strategy conclusion:** every honest Indian factor/drift study on GitHub lands on our null. No
external repo surfaces a structural signal we haven't already listed. The candidates in §4 come
from the *data* the repos unlock, not from their strategies.

### 2c. India data repos — the useful part

| Repo | Verified how | What it proves |
|---|---|---|
| Pareshking/NSE-BSE-Insider-Tracker | Runs on **GitHub Actions**; probe artifact 2026-08-31, validation run 2026-09-01 | Which NSE/BSE endpoints answer from a datacenter IP (see §3) |
| hxrsh90/stockerrr | Live probing 2026-09-08/10, notes in `research/01-nse-bse-filings-api.md` | ASM/GSM JSON, shareholding master + pledge XBRL, financial-results API, working BSE announcements endpoint + headers |
| theabhinavsharma/shree-ganesh-model | Docs | Symbol-by-symbol shareholding + pledge history from NSE APIs; NSDL fortnightly FPI sector flows |
| dvygo/Fundamental-Screener | Docs | NSE/BSE daily bundles + SEBI XBRL + screener dossiers; insider open-market buys as a screen |
| subscriptionmanager26-png/fund-disclosures | Docs + public API | AMC-direct monthly/fortnightly MF portfolio holdings, mapped to AMFI codes |
| BuildAlgos/screener-scraper, BennyThadikaran/BseIndiaApi | Docs | BSE endpoints changed in 2026 → 403 unless `Referer` + `Origin` are set (stockerrr confirms the fix) |

## 3. Data we should pull — endpoint by endpoint

Everything below is in the same `www.nseindia.com/api/*` + `Referer` family as
`corporate-announcements` and `corporate-sast-reg29`, which already work from our runners.
"Verified" = someone else proved it; "probe" = we must confirm from `probe-sources.yml` first.

| # | Endpoint | Verified by | What it gives | Unlocks | Status in our stack |
|---|---|---|---|---|---|
| D1 | `api/corporates-pit-gg?index=equities` (+ per-filing XBRL via `xmlFileName`) | Pareshking, **from Actions** | Every PIT disclosure: person category (Promoter / KMP / Director…), Buy/Sell, qty, value, mode (market / ESOP / off-market / pledge), pre/post holding | Pre-registered **promoter sells** test (CONCLUSIONS §10); insider-mode filter | We call `api/corporates-pit` — the **dead** endpoint (always empty). `-gg` is the live one. |
| D2 | `api/reportASM`, `api/reportGSM` (Referer `/reports/asm`; send `Accept-Encoding: gzip, deflate` — no `br`, it serves Brotli) | stockerrr, live | Current ASM long/short-term + GSM lists: `symbol`, `survDesc` (stage), `asmTime`/`gsmTime` | Backlog **#5 ASM/GSM** | We only probed the static `asm_list.csv` (404) and parked it. Snapshot-only → must be captured daily; history accrues from the day we start. |
| D3 | `api/corporate-share-holdings-master?index=equities&symbol=X` → quarterly rows + XBRL link; pledge % = XBRL `EncumberedSharesHeldAsPercentageOfTotalNumberOfShares` in the promoter context | stockerrr (verified vs IndusInd 50.9→42.8%, Titan/Kotak 0.0) | Quarterly shareholding history per symbol incl. promoter %, **small-shareholder (≤₹2 lakh nominal) %**, pledge % | (i) **the retail-% feature for the buyback acceptance model** — the 15% reservation denominator, listed as "next" in CLAUDE.md; (ii) backlog **#8 pledge release**; (iii) pledge *invocation* candidate (§4) | Not ingested. Only one XBRL taxonomy version verified — guard for `None`. |
| D4 | `api/corporate-further-issues-pref?index=FIPREFIP` / `FIPREFLS` | Pareshking (needed Selenium from Actions — probe plain session first) | Preferential allotments: in-principle + listing stage, price, allottees, dates | **New candidate: preferential-allotment lock-in expiry** (§4) | Not ingested. |
| D5 | `api/corporate-further-issues-ri?index=FIRIIP` / `FIRILS` | Pareshking | NSE's own rights-issue list | Coverage cross-check for `rights_issues` (chittorgarh) | Nice-to-have. |
| D6 | `api/corporates-financial-results?index=equities&from_date&to_date&period=Quarterly` (24 fields: `xbrl`, `audited`, `consolidated`, result PDF, broadcast time) | stockerrr, live | Point-in-time quarterly results with exact broadcast timestamp | **#15 PEAD** control with a surprise proxy (YoY growth vs prior quarters, or results-day gap); replaces `board_meeting` date-only rows for results timing | Not ingested. |
| D7 | BSE `api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w` with `Referer: https://www.bseindia.com/` **and** `Origin: https://www.bseindia.com`, one day per call, 50/page; attachments at `xml-data/corpfiling/AttachHis/` | stockerrr, live 2026-09-08 | BSE announcements incl. `Corp. Action`, `Insider Trading / SAST`, subcategories | Re-opens **#3 delisting RBB** (our BSE 403 was almost certainly the missing headers / the dead `AnnGetData/w`) — still needs offer + discovered-price parsing | Parked on "BSE 403". Re-probe. |
| D8 | niftyindices `Press_Release/<date>.pdf` sweep (Abhinav7582 `circulars_fetch.py`) | Abhinav7582 | Every index reconstitution release 2015→ | Extends `index_membership` history to Nifty 100/Midcap/Smallcap before our weekly diffs began | Optional infra. |
| D9 | Bhavcopy `prevclose` ratio adjustment (nsefactor) | nsefactor | Split/bonus factors from the store itself | Adjusted return series without yfinance; closes the `source="yf"` vs `"db"` split | Optional infra. |
| D10 | AMC portfolio disclosures (fund-disclosures) | repo API | Monthly MF holdings per stock | MF-ownership % as an acceptance feature (general category) | Defer — heavy parsing, marginal. |

Not worth pulling: NSDL FPI sector flows (macro), concall audio (BSE `AUDIO_VIDEO_FILE`), IPO GMP
scrapers (grey-market, unauditable), the historical bulk/block JSON (`api/historicalOR/...`, 70-row
cap, we already warehouse the daily CSV).

## 4. Strategies to test — ranked by the thesis

| # | Candidate | Bucket | Mechanism / barrier | Data | Prior | Test |
|---|---|---|---|---|---|---|
| S1 | **Preferential-allotment lock-in expiry** | 🟢 structural | ICDR: 6-month lock-in (non-promoter allottees), 18-month (promoters). Forced supply at a known date in small caps — same mechanism as the validated anchor unlock (§6). Not shortable (not in F&O) → expect a *lens*, but also test the **post-dip recovery leg** (long, actionable), which §6 measured only as T+2→T+10 ≈ +0.3–0.5% | D4 (+ BSE pref page) | real dip likely; recovery unknown | Event study T−1→T+2 and T+2→T+20 vs NIFTY 500, same-stock placebo, era cut, mcap cut via `pointintime` |
| S2 | **Promoter / insider sells** (pre-registered in §10) | 🟡 | Disposal by promoter in the open market (exclude ESOP/off-market/pledge modes — D1 gives mode) | D1 | thin/null; §10 contrast showed −5.8% median 2024-26 but flipped sign across eras | `validate_promoter_buys.py` with sell leg as the hypothesis; era cut mandatory |
| S3 | **Pledge invocation → forced sale** (new variant of #8) | 🟢 | Lender invokes pledged shares and sells → forced flow; no pre-announcement; retail can't front-run but can buy the dip | D1 mode = "invocation" / SAST Reg 31 rows in existing reg29 feed | dip real, rebound unknown | Event study at disclosure; contrast with pledge *release* (#8) |
| S4 | **Pledge release** (#8 as written) | 🟡 | De-risking disclosure | D3 quarterly | thin, low-frequency | QoQ pledge-% drop events → +60d |
| S5 | **ASM/GSM entry / exit** (#5) | 🟢 | Forced 100% margin, trade-to-trade | D2 daily capture | entry dip / exit bounce | Needs ≥6–12 months of captures; `asmTime` allows a right-censored entry study sooner |
| S6 | **PEAD** (#15) | ⚪ control | Public information | D6 | null | Results-day gap → T+20 drift |
| S7 | **Turn-of-month** (#17) | ⚪ control | Calendar | prices | null net of costs (external "marginal pass" is 0.9%/yr gross) | Cheap; document |

Not a strategy but the highest practical value: **D3's small-shareholder % into
`estimate_acceptance`** — it is the actual denominator of the 15% retail reservation and replaces
the market-cap heuristic prior for the primary signal.

## 5. Recommended sequence

1. **Probe (one Actions run, no product code).** Add D1, D2, D3 (+ one XBRL), D4, D6, D7 to
   `scripts/probe_sources.py`; run `probe-sources.yml`. Cost: ~1 hour. Decides everything below.
2. **Ingest what passes**, in this order: D3 shareholding/pledge (feeds buyback_arb *and* S3/S4),
   D1 PIT (extend `scanner/insider.py`), D2 daily ASM/GSM snapshot (tiny table; history starts
   accruing), D4 preferential issues → `corporate_events` `pref_allotment` + lock-in expiry rows.
   Each gets a freshness rule (the test enforces it) and fits the free tier (all quarterly or
   hundreds of rows/day).
3. **Validate** S1, then S2/S3 (same PIT feed), S6/S7 as controls. S5 waits for data.
4. **Feature**: small-shareholder % into `estimate_acceptance` once D3 has coverage.
5. **Optional infra** (D8, D9) only when a study needs them.

Explicitly not doing: adopting qlib/TradingAgents/ai-hedge-fund; re-testing momentum, value,
quality, reversal, factor combos, or LLM-scored stock picks.

## 6. Sources

- https://github.com/Pareshking/NSE-BSE-Insider-Tracker (`DATA_ACQUISITION.md`, `artifacts/acquisition_probe.json`)
- https://github.com/hxrsh90/stockerrr (`research/01-nse-bse-filings-api.md`, `src/stockerrr/nse_client.py`)
- https://github.com/theabhinavsharma/shree-ganesh-model (`docs/source_limitations.md`)
- https://github.com/Abhinav7582/indian-equity-research (`HYPOTHESES.md`, `docs/circulars_worklist.md`)
- https://github.com/AnoopIbrampur/nsefactor · https://github.com/md0n-cmd/indian-equity-backtests
- https://github.com/kousikdutta-1005/market-lab · https://github.com/dvygo/Fundamental-Screener
- https://github.com/subscriptionmanager26-png/fund-disclosures · https://github.com/BuildAlgos/screener-scraper
- https://github.com/BennyThadikaran/BseIndiaApi · https://github.com/virattt/ai-hedge-fund
- https://github.com/TauricResearch/TradingAgents · https://github.com/microsoft/qlib
- https://ultralab.tw/en/blog/ai-finance-github-projects-2026 (star counts, Aug 2026)
