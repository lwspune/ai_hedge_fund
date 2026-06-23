# Pillar Yes/No Formula Audit (2026-06-12)

Read the **actual** signal formulas from the local xlsx (openpyxl, not the Drive
value-export). This closes the 4 "STILL UNVERIFIED" items from the May-11 session.

Source: `extracted/sheets/Stocks_{EMA,Drawdown,Zone,Aggregate}_Signal.xlsx`.
Extractor: `extracted/audit_signal_formulas.py` + ad-hoc TopXX probes.

## Sheet mechanics (all three Signal workbooks share a template)
- Per-stock daily data lives in `Top20_Stocks` etc. Column **D = close price**
  (GOOGLEFINANCE "price"), oldest at row 9, newest at the bottom (~row 994).
- Row 996 "Latest …" = `INDEX(col, COUNTA(...))` → the most recent value.
- Row 997/1001 = the Yes/No **Signal**.
- `Summary` just pulls row-997/1001 values via INDEX and (for Drawdown) applies
  the threshold test.

## Results

| Pillar | Sheet formula (decoded) | Our impl | Verdict |
|---|---|---|---|
| **EMA** | `IF(WMA_N >= price, "Yes")` → **price ≤ WMA_N** | `price > lwma(N)` | ❌ **INVERTED** |
| **Drawdown** | `MAX(D14:cur)` = expanding ATH; `IF(dd <= -X%, "Yes")` | `cummax()`, `dd <= -X%` | ✅ match |
| **Zone** | `MIN(D..cur)` rolling-N low; `IF(low == price, "Yes")` | `price <= rolling(N).min()` | ✅ match |

### EMA — the one that's wrong
- `E993 = SUMPRODUCT(D944:D993, $B$9:$B$58)/SUM($B$9:$B$58)` = 50-bar LWMA
  (weights B = 1,2,…; newest heaviest — matches our `lwma`). F/G/H = 100/200/300.
- `E996` = latest 50-bar LWMA; `D996` = latest price.
- `E997 = IF(E996 >= D996, "Yes", "")` → **Yes when MA ≥ price, i.e. price at/below
  the moving average.** This is a **mean-reversion / buy-the-dip** rule.
- We implemented `price > lwma(N)` (price ABOVE the MA) — trend-following, the
  exact opposite.

### Why this matters
All three pillars are supposed to be **"buy weakness"** signals:
- Drawdown: price fallen ≥X% from ATH ✅
- Zone: price at its N-day low ✅
- EMA (corrected): price at/below its moving average ✅ (mean-reversion)

Our inverted EMA made it trend-following — the odd one out, fighting the other two.
The fix makes the ensemble internally coherent.

### Zone strict-equality is FAITHFUL, not a bug
The May-11 note worried Zone might use a tolerance band. It does **not** — the
sheet fires only when `price == rolling_low` exactly. Our `price <= rolling.min()`
is identical (price can't be below its own trailing min). The ~2.4/48-stocks/day
rarity is true to the sheet. **No change needed.**

### Drawdown reference = expanding ATH (cummax), confirmed
`MAX(D$14:Dcur)` anchored at row 14, expanding window = all-time-high to date =
`cummax()`. NOT a 200-day rolling high. (The `_200_Days` analyser is a separate
research sheet, not the production Drawdown_Signal.) **No change needed.**

## Aggregate `Overall/Buy` rule — AUDITED (Stocks_Aggregate_Signal!Summary)
12 sub-signal columns G:R = EMA(G:J) + Drawdown(K:N) + Zone(O:R), each pulled from
the respective Signal workbook.

- **Per-pillar binary** (S=EMA, T=Drawdown, U=Zone):
  `S4 = if(COUNTIF(G4:J4,"=Yes")>0, 1, 0)` → **ANY of 4 sub-signals fires the
  pillar.** ✅ confirms the assumed ANY-within-pillar rule.
- **`Overall/Buy`** (F): `F4 = IF(SUM(S4:U4)=3, "Yes", "")` → **ALL 3 pillars must
  fire** (AND across pillars). ❌ We've been treating **Aggregate ANY** (≥1 pillar)
  as the working baseline — the sheet's production signal is **Aggregate ALL**
  (`aggregate_signal(mode="all")`).
- **`Signal/Count`** (E): `E4 = COUNTIF(G4:R4,"=Yes")/12` → fraction of the 12
  sub-signals. ✅ matches `signal_count_pct` (÷12), once EMA direction is fixed.

## Two corrections to shipped code
1. **EMA direction** — `ema_pillar` + `signal_count_pct`: `price > lwma` →
   `price <= lwma` (mean-reversion).
2. **Production aggregation** — sheet's `Overall/Buy` = `mode="all"` (3 of 3
   pillars), not the `mode="any"` we headlined.

Both feed the headline result and must be re-run together.

## Impact on prior results (all used inverted EMA)
- "EMA pillar alone +8.98%" — meaningless until re-run with corrected direction.
- "Aggregate ANY +16.37%, Sharpe 0.99" (the headline working baseline) — used
  inverted EMA; must re-run.
- `signal_count_pct` EMA term also inverted.
