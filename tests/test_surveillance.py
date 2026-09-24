"""Test-first spec for the daily ASM/GSM surveillance snapshot (NSE api/reportASM + api/reportGSM).

The lists are snapshots (asmTime = the list-run date, not the entry date), so history is built by
capturing them every trading day; entries/exits are derived from consecutive snapshots."""
from datetime import date

from scanner.surveillance import parse_asm, parse_gsm, transitions

ASM = {"longterm": {"data": [
    {"asmSurvIndicator": "Stage I", "asmTime": "24-Sep-2026", "companyName": "A2Z Infra Engineering Limited",
     "isin": "INE619I01012", "survCode": "LTASM - I (13)",
     "survDesc": "Long Term Additional Surveillance Measure (LTASM) - Stage I", "symbol": "A2ZINFRA", "srno": 1},
    {"asmSurvIndicator": "Stage IV", "asmTime": "24-Sep-2026", "survCode": "LTASM - IV (16)", "symbol": " ZEEL ", "srno": 2},
    {"asmSurvIndicator": "Stage I", "asmTime": "24-Sep-2026", "survCode": "LTASM - I (13)", "symbol": "", "srno": 3},
]}, "shortterm": {"data": [
    {"asmSurvIndicator": "Stage I", "asmTime": "24-Sep-2026", "survCode": "STASM - I (11)", "symbol": "ABH", "srno": 1},
]}}

GSM = [
    {"companyName": "AGS Transact Technologies Limited", "gsmStage": "LXII", "gsmTime": "24-Sep-2026 08:07:02",
     "isin": "INE583L01014", "survCode": "IBC - Receipt & GSM 0 (62)", "survDesc": "IBC ... GSM stage 0",
     "symbol": "AGSTRA", "srno": 1},
    {"gsmStage": "II", "gsmTime": "24-Sep-2026 08:07:02", "survCode": "GSM - II (2)", "symbol": "XYZ", "srno": 2},
]


def test_parse_asm_splits_long_and_short_term_and_normalises_symbols():
    rows = parse_asm(ASM, as_of=date(2026, 9, 24))
    assert rows == [
        {"as_of": "2026-09-24", "symbol": "A2ZINFRA", "list_name": "asm_lt", "stage": "Stage I",
         "surv_code": "LTASM - I (13)"},
        {"as_of": "2026-09-24", "symbol": "ZEEL", "list_name": "asm_lt", "stage": "Stage IV",
         "surv_code": "LTASM - IV (16)"},
        {"as_of": "2026-09-24", "symbol": "ABH", "list_name": "asm_st", "stage": "Stage I",
         "surv_code": "STASM - I (11)"},
    ]


def test_parse_gsm_rows():
    rows = parse_gsm(GSM, as_of=date(2026, 9, 24))
    assert rows[0] == {"as_of": "2026-09-24", "symbol": "AGSTRA", "list_name": "gsm", "stage": "LXII",
                       "surv_code": "IBC - Receipt & GSM 0 (62)"}
    assert rows[1]["stage"] == "II" and len(rows) == 2
    assert parse_gsm({"data": GSM}, as_of=date(2026, 9, 24)) == rows   # tolerate a wrapped response


def test_transitions_between_two_snapshots():
    prev = [{"symbol": "A", "list_name": "asm_lt", "stage": "Stage I"},
            {"symbol": "B", "list_name": "asm_st", "stage": "Stage I"},
            {"symbol": "C", "list_name": "gsm", "stage": "I"}]
    cur = [{"symbol": "A", "list_name": "asm_lt", "stage": "Stage II"},   # stage change, not an entry
           {"symbol": "C", "list_name": "gsm", "stage": "I"},
           {"symbol": "D", "list_name": "asm_st", "stage": "Stage I"}]
    t = transitions(prev, cur)
    assert t["entries"] == [("D", "asm_st")]
    assert t["exits"] == [("B", "asm_st")]
    assert t["stage_changes"] == [("A", "asm_lt", "Stage I", "Stage II")]
    assert transitions([], cur)["entries"] == []   # no previous snapshot -> nothing to compare
