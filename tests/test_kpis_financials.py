"""Test-first spec for the financials sector pack (lender ratios). Real sentences from the
Aug-2026 sample (Bandhan, Aye, Piramal, IndusInd, DCB, Yes Bank) — catches and traps."""
import pytest

from scanner.kpis import fin_ratios


def _v(rows, kpi):
    return [r["value"] for r in rows if r["kpi"] == kpi]


@pytest.mark.parametrize("text,kpi,value", [
    ("GNPA Ratio 3.1% (-182 bps YoY & -12 bps QoQ) NNPA", "gnpa", 3.1),
    ("GNPA stood at 4.49%, improving 28 basis points sequentially", "gnpa", 4.49),
    ("Gross NPA: 2.43% & Net NPA: 0.84% Total business", "gnpa", 2.43),
    ("Gross NPA: 2.43% & Net NPA: 0.84% Total business", "nnpa", 0.84),
    ("NNPA Ratio 0.9% (-43 bps YoY & -4 bps QoQ) PCR** 71.1% (-259 bps YoY", "pcr", 71.1),
    ("NIM of 3.35% for Q1FY27 Business Model", "nim", 3.35),
    ("Net Interest Margins (excluding one-offs) at 3.35% vs 3.46% YoY", "nim", 3.35),
    ("our Net Interest Margin improved 20 basis points year-on-year to 2.7%, also holding", "nim", 2.7),
    ("Credit cost moderated further to 4.01%, a reduction of 29 basis points", "credit_cost", 4.01),
    ("PCR as of 30th June 2026 is 63.80% Robust Multi-Tiered", "pcr", 63.8),
    ("Capital & Liquidity CRAR 18.2% CET 1 17.5% Retail Deposits", "crar", 18.2),
    ("net-worth stands at Rs. 28,906 crore with capital adequacy at 18.85% as on June end", "crar", 18.85),
    ("CASA Ratio at 21.65% Provision Coverage Ratio: 79.81%", "casa", 21.65),
    ("CASA Ratio at 21.65% Provision Coverage Ratio: 79.81%", "pcr", 79.81),
    ("ROA 1.0% (20 bps YoY & -11 bps QoQ)", "roa", 1.0),
    ("Return on Assets *Annualized 0.78% CRAR 17.15%", "roa", 0.78),
])
def test_fin_ratios_catch_real_phrasings(text, kpi, value):
    rows = fin_ratios(text)
    assert _v(rows, kpi)[:1] == [value]
    assert all(r["unit"] == "%" and r["quote"] in text for r in rows)


def test_fin_ratios_respectively_pairs():
    rows = fin_ratios("Our total GNPA and NNPA were at 2.4% and 1.6%, respectively. Our net-worth")
    assert _v(rows, "gnpa") == [2.4] and _v(rows, "nnpa") == [1.6]


@pytest.mark.parametrize("text", [
    "Credit Cost (% of Avg Loans) 2.11% 3.24% 2.62% 1.89% 1.74% 26 Loan Related",   # multi-quarter row
    "GNPA NNPA RoA (on assets) RoE Q1FY26 Q4FY26 Q1FY27 14.3% 15.7% 15.9%",          # stacked labels
    "Business Model NIMs 350 bps to 365 bps Improving CASA",                         # bps guidance
    "we expect NIM to be around 3.5% for the full year",                             # guidance
    "Capital Adequacy Ratio (%) Networth (Rs. Crores) Mar-24 Mar-25 Mar-26 Jun-26 32.8% 34.9%",
])
def test_fin_ratios_reject_traps(text):
    assert fin_ratios(text) == []


# --- regressions from the 40-document lender review (every extraction read) ---

@pytest.mark.parametrize("text", [
    "NNPA Gross Advances1 Total Deposits 7% 17% 86,610 cr.",          # Karnataka Bank table bleed
    "CASA Deposits grew 14.3% year on year",                          # growth, not the ratio
    "car loans Disbursements AUM (In ₹ Cr) +15%",                     # 'car' is not CAR
    "Net NPA Y-o-Y decline: -26bps 17.61%",                           # PSB table: implausible NNPA
    "GNPA in corridor of <1.4% and NNPA in corridor of <0.5%",        # guidance band
    "credit cost of 12 basis points. PAT for the quarter grew 4%",    # next sentence's number
    "CASA products Diversified Presence 59%",                         # slide label bleed
    "PCR (excl. TWO) 12% CASA Retail Term Deposit 0.53%",            # table bleed
    "CRAR 0.8%",                                                      # below any regulatory floor
])
def test_fin_ratios_reject_review_false_positives(text):
    assert fin_ratios(text) == []


def test_fin_ratios_value_first_tile_slides_are_skipped_not_misread():
    """KPI-tile slides put the value BEFORE its label; label-first reading would take the next
    tile's number (Five Star 'GNPA 12.38%' was really 30+ DPD). Ambiguous -> skip."""
    five_star = ("₹ 137,218 Mn Loan Portfolio 3.46% Gross NPA 12.38% 30+ DPD ₹ 2,714 Mn Profit After Tax")
    assert [r for r in fin_ratios(five_star) if r["kpi"] == "gnpa"] == []
    maha = "Asset Quality 1.45 % Gross NPA 0.13 % Net NPA 98.55 % PCR 0.99 % / 1.23 % Credit Cost1"
    got = {r["kpi"]: r["value"] for r in fin_ratios(maha)}
    assert "gnpa" not in got and "nnpa" not in got and "pcr" not in got
    indusind = "Average LCR 127% PCR 71% GNPA 3.25% | NNPA 0.95% Universal"   # label-first stays
    got = {r["kpi"]: r["value"] for r in fin_ratios(indusind)}
    assert got["gnpa"] == 3.25 and got["nnpa"] == 0.95


def test_fin_ratios_amount_between_label_and_percent_rejected():
    assert fin_ratios("CASA 35,787 (2 % growth") == []


def test_extract_all_runs_the_lender_pack_only_for_financial_services():
    from scanner.kpis import extract_all
    t = "GNPA Ratio 3.1% (-182 bps YoY) NIM 6.2% (-16 bps YoY)"
    fin = extract_all(t, "Investor Presentation", "Investor presentation", sector="Financial Services")
    assert {r["kpi"] for r in fin} >= {"gnpa", "nim"}
    other = extract_all(t, "Investor Presentation", "Investor presentation", sector="Industrials")
    assert not {r["kpi"] for r in other} & {"gnpa", "nim"}


def test_fin_ratios_allowlist_keeps_long_but_clean_connectors():
    t = "Net interest margin global for the quarter ended 30 June 2026 is 3.37% and"
    assert [r["value"] for r in fin_ratios(t) if r["kpi"] == "nim"] == [3.37]
    t = "provisioning coverage ratio on stage 3 assets was 60% and"
    assert [r["value"] for r in fin_ratios(t) if r["kpi"] == "pcr"] == [60]
