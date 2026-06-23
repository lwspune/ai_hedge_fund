# Suggestions

A running list of actionable improvements surfaced during /update-docs runs.
Each item is outside the scope of the work that surfaced it. Strike through when done.

---

## 2026-06-13

### Fix the phantom-cashflow XIRR bug in the live Google Sheet

The forensic audit proved the sheet's headline XIRRs are wrong: a blank end-date row
injects a negative cash flow at serial date 0 (1899-12-30), 110 years before the
data, which dominates the XIRR. Reproduced to 0.0001pp. This is not a port artifact —
it silently misreports returns in the *live* sheet Vilas uses to evaluate any stock,
not just in this project.

**Why:** every XIRR he reads from that sheet today is distorted downward; decisions
based on it are made on bad numbers. One-cell fix, high value, affects ongoing use.

**How to apply:** wrap the daily-return formula —
`=IFERROR(IF(ISBLANK(E_curr), "", E_curr/E_prev - 1), "")` — so the blank trailing row
stops producing a phantom −1 return → phantom cash flow. Claude can walk through the
exact column/cell in `Stocks_Buy_Signal_Analyser_15Yr` on request. (Deferred this
session — user said "that's fine" / not now.)

### Resume the value-investing project kickoff (blocked on two decisions)

Direction is set (discretionary fundamental value, India-first, single-company dossier
tool) and the build plan is written, but no code exists yet because two user decisions
are pending. See the `value-investing-project` memory for the full plan.

**Why:** the next session should start by closing these two questions, not by
re-deriving the plan. Keeps momentum and avoids re-litigating settled scope.

**How to apply:** confirm (1) **form factor** — Python CLI (recommended, for the
scraping + PDF-parsing work) vs his usual single-file-HTML tool pattern; and (2) a
**guinea-pig company** to build the first dossier against a real annual report
end-to-end. Then scaffold a NEW repo/dir (not this concluded one) and build v1
test-first.
