# Filings KPI analysis (F2) — what is worth ingesting from NSE filings

**Date:** 2026-09-24 · **Question:** of everything companies disclose in presentations, call
transcripts, press releases and order announcements, which metrics are worth extracting into
structured data? Decided from evidence, not guessed.

## Sample
Stratified from the Aug-2026 results season (27-Jul → 30-Aug; 10,471 kept filings with PDFs):
70 investor presentations, 70 earnings-call transcripts, 35 results press releases, 25 order-win
disclosures — 200 documents. Text via PyMuPDF (same library as Question_Bank's ingestion).

**Text-layer triage:** 200/200 downloaded; only **2/70 presentations** are mostly image
(>50% pages with <80 chars). Text extraction covers ~99% of documents; page rendering + visual
reading (the Question_Bank pattern) is only needed for the rare image-only deck.

## Which metrics appear (with a number nearby)

| Metric family | Presentations | Transcripts | Press | Order filings | Already structured elsewhere? |
|---|---|---|---|---|---|
| EBITDA margin | 54/70 | 43/70 | 10/35 | 0 | **yes** — screener OPM |
| Capacity (MW/MTPA/…) | 30 | 15 | 6 | 3 | no (units vary by sector) |
| Revenue / other guidance | 10 | 40 | 1 | 0 | no |
| Capex | 20 | 30 | 0 | 0 | partly (cash-flow capex) |
| Net debt / cash | 27 | 17 | 0 | 0 | **yes** — balance sheet |
| Volume / realisation | 20 | 20 | 3 | 0 | no (commodities) |
| **Order book** | 11 | 12 | 7 | 1 | **no** — 17 of 38 industrials docs |
| Capacity utilisation | 7 | 13 | 2 | 0 | no |
| Order inflow | 7 | 6 | 5 | 0 | no |
| Loan book / AUM, asset quality, NIM, CASA, credit cost | ≤12 each | | | | partly (bank NPA % in screener) |
| TCV / deal wins, ARPU, occupancy, headcount | ≤11 each | | | | no (sector-specific) |

Order-win filings (SEBI Reg 30 table) almost never state the order book — they state the
**value of the order won** in a standard "consideration or size of the order(s)" cell.

## Decision — rule_v1 extracts
1. **Order book level** (₹ crore, as-of date) — formulaic, forward-looking, not available anywhere
   else; the metric the platform's question started from.
2. **Order-win value** — one per Reg 30 order filing; an event, not just a level.
3. **Capacity utilisation (current %)** — with a tense guard (targets rejected).
4. **Guidance** — stored as **quotes**, not numbers: guidance spans revenue, volume, capex,
   costs, store openings — one number field would be a lie.

**Skipped:** EBITDA margin, net debt, working capital (already in financials).
**Deferred to sector packs (next):** financials (NIM, credit cost, CASA, loan growth, GNPA beyond
screener) and commodities (volume, ₹/tonne realisation) — high value *within* their sectors, but
each needs its own lexicon, units and a precision check like the one below.

## Precision (every numeric extraction on the 200 docs read by hand)
Two review rounds; each false positive became a failing test before the fix
(`tests/test_kpis.py`):

| | round 1 | round 2 (shipped) |
|---|---|---|
| Order book | ~50% usable (51 hits) | **15/18 correct**, 3 plausible business-line figures |
| Order-win value | 12/13 | 12/13 |
| Capacity utilisation | ~80% | ~10/12 (some plant/segment level, visible in the quote) |

Round-1 failure modes fixed: `order bookings` (inflow) matched as `order book`; "New orders
reached US$339 mn"; a heading followed by one contract's value; **"₹2 lakh crore" parsed as ₹2
lakh**; "$1.3–1.4 billion" lost its currency; transcript Q&A chatter (9 order-book numbers in one
KNRCON call) → one **headline** per filing: the dated statement, and in transcripts *only* a dated
status line; segment-level lines rejected.

Every stored value keeps its exact quote + source filing link, so any number can be checked on
the company page. Precision over recall: ambiguous phrasings return nothing.

## Sector packs (2026-09-24)
Sample: 40 lender + 40 "Commodities" presentations/transcripts (Aug-2026 season).

**Commodities — not built (evidence, not deferral).** Screener's "Commodities" sector mixes
chemicals, metals, cement and paper: volume appeared in 12/40 docs, realisation in 7/40, ₹/tonne
in 8/40, in inconsistent units. Its most common metric — capacity utilisation (20/40) — is already
extracted by the base pack.

**Financials — built (`fin_ratios`, runs only for Financial Services).** Near-universal in lender
filings: AUM/loans 34/40, GNPA 26, RoA/RoE 26, CRAR 26, NNPA 24, disbursements 23, credit cost 21,
NIM 19, PCR 18. Extracted: GNPA, NNPA, NIM, credit cost, PCR, CRAR, CASA, RoA (% ratios).
Three hand-review rounds on the 40 docs; failure modes, each now a test
(`tests/test_kpis_financials.py`):
- table/label bleed ("NNPA Gross Advances1 Total Deposits 7%") and growth rates read as levels
  ("CASA Deposits grew 14.3%") → the words between label and % must come from a connector
  **allowlist** ("stood at", "improved to", "for the quarter ended 30 June 2026 is", …);
- **value-first KPI tiles** ("3.46% Gross NPA 12.38% 30+ DPD" — reading forward took the next tile's
  number) → a % right before the label that isn't a preceding lender label's value = ambiguous
  tile → skip; label-first slides ("PCR 71% GNPA 3.25%") still read;
- `CAR` matched "car loans" → case-sensitive; guidance bands ("corridor of <1.4%") rejected;
  plausibility floors (CRAR ≥ 8, PCR ≥ 25, NNPA ≤ 10).
Final: 84 unique extractions on 24/40 docs, all read and consistent with their quotes.
AUM/loan-book *levels* not extracted yet (mixed units + segment books).
