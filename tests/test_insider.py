"""Test-first spec for promoter open-market buying (candidate signal #7; SAST Reg 29 data)."""
from scanner.insider import parse_reg29, disclosure_events

RAW = [
    {"symbol": "ALMONDZ", "acqSaleType": "Acquisition", "acquisitionMode": "Open Market",
     "promoterType": "Y", "acqType": "Equity shares", "acquirerDate": "01-SEP-2026 to 01-SEP-2026",
     "sysTime": "08-Sep-2026 12:36", "totAcqShare": "0.07", "totSaleShare": None, "totAftShare": "0.25"},
    {"symbol": "ALMONDZ", "acqSaleType": "Acquisition", "acquisitionMode": "Open Market",
     "promoterType": "Y", "acqType": "Equity shares", "acquirerDate": "10-SEP-2026 to 11-SEP-2026",
     "sysTime": "12-Sep-2026 18:02", "totAcqShare": ".10", "totSaleShare": None, "totAftShare": "0.35"},
    {"symbol": "ALMONDZ", "acqSaleType": "Acquisition", "acquisitionMode": "Open Market",
     "promoterType": "Y", "acqType": "Equity shares", "acquirerDate": "01-OCT-2026 to 01-OCT-2026",
     "sysTime": "05-Oct-2026 10:00", "totAcqShare": "0.2", "totSaleShare": None, "totAftShare": "0.55"},
    {"symbol": "XYZ", "acqSaleType": "Sale", "acquisitionMode": "Open Market",
     "promoterType": "Y", "acqType": "Equity shares", "acquirerDate": "02-SEP-2026 to 02-SEP-2026",
     "sysTime": "03-Sep-2026 09:00", "totAcqShare": None, "totSaleShare": "1.5", "totAftShare": "60"},
    {"symbol": "PQR", "acqSaleType": "Acquisition", "acquisitionMode": "Off Market",
     "promoterType": "Y", "acqType": "Equity shares", "acquirerDate": "02-SEP-2026 to 02-SEP-2026",
     "sysTime": "03-Sep-2026 09:00", "totAcqShare": "5", "totSaleShare": None, "totAftShare": "60"},
    {"symbol": "BAD", "acqSaleType": "Acquisition", "acquisitionMode": "Open Market",
     "promoterType": "N", "acqType": "Warrants", "acquirerDate": "x", "sysTime": "garbage",
     "totAcqShare": "1", "totSaleShare": None, "totAftShare": "2"},
]


def test_parse_reg29_normalises_and_drops_undated():
    rows = parse_reg29(RAW)
    assert len(rows) == 5  # BAD has no parseable disclosure date
    a = rows[0]
    assert a == {"symbol": "ALMONDZ", "side": "BUY", "promoter": True, "mode": "Open Market",
                 "instrument": "Equity shares", "disclosed": "2026-09-08", "pct": 0.07, "after_pct": 0.25}
    assert rows[1]["pct"] == 0.10
    sale = [r for r in rows if r["symbol"] == "XYZ"][0]
    assert sale["side"] == "SELL" and sale["pct"] == 1.5


def test_disclosure_events_cluster_within_gap_and_filter():
    ev = disclosure_events(parse_reg29(RAW), side="BUY", promoter=True, mode="Open Market", gap_days=10)
    assert [(e["symbol"], e["date"], e["n"], round(e["pct"], 2)) for e in ev] == [
        ("ALMONDZ", "2026-09-08", 2, 0.17),   # 08-Sep + 12-Sep merged (4 days apart)
        ("ALMONDZ", "2026-10-05", 1, 0.20),   # 23 days later -> new event
    ]
    sells = disclosure_events(parse_reg29(RAW), side="SELL", promoter=True, mode="Open Market")
    assert [(e["symbol"], e["date"]) for e in sells] == [("XYZ", "2026-09-03")]
