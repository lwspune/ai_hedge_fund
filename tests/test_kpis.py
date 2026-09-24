"""Test-first spec for rule-based KPI extraction from filings (F3). Cases are real sentences
from the Aug-2026 results-season sample — both the ones to catch and the traps to reject."""
import pytest

from scanner.kpis import to_crore, order_book, order_win_value, capacity_utilisation, guidance_quotes


def test_to_crore_units():
    assert to_crore(9445, "crore") == 9445
    assert to_crore(5410, "Mn") == 541.0
    assert to_crore(2.5, "bn") == 250.0
    assert to_crore(50, "lakh") == 0.5
    assert to_crore(210, "USD million") is None      # non-INR: kept raw, not converted


@pytest.mark.parametrize("text,value,unit", [
    ("All-time-high Order Book of ₹9445 crore, with 120+ orders worth ₹670+ crore secured in Q1", 9445, "crore"),
    ("As of June 30, 2026, company's order book is standing at INR9,923 crores, providing multiyear", 9923, "crore"),
    ("Our order book remains healthy at Rs. 1,864 crore, providing strong revenue visibility.", 1864, "crore"),
    ("Our consolidated order book as on June 30, 2026, stands at over INR18,700 crores, providing", 18700, "crore"),
    ("₹5,410 Mn Total Order Book Order book as on 30 June 2026 plus orders received", 5410, "mn"),
    ("20 States 1 Union Territory Pan-India Rs 30,215 Cr Diversified Order Book across 12 verticals", 30215, "crore"),
    ("currently holding an active order book exceeding ₹ 300 Crores (~US$ 32 Million), which", 300, "crore"),
])
def test_order_book_catches_real_phrasings(text, value, unit):
    got = order_book(text)
    assert got and got[0]["value"] == value and got[0]["unit"] == unit  # canonical units
    assert got[0]["quote"] in text


@pytest.mark.parametrize("text", [
    "our 12-month order backlog has grown by 25% year-on-year terms and 13% in constant currency",
    "This improvement was driven by growth in order book across our diversified product mix",
    "Our current order book stands at approximately 19 crores liters, and we remain confident",   # litres
    "Order Book & Pipeline • FY27 order inflow target: ₹4,500 – ₹5,000 crores. • Orders booked",  # heading
])
def test_order_book_rejects_traps(text):
    assert order_book(text) == []


def test_order_book_reads_as_of_date():
    got = order_book("Our consolidated order book as on June 30, 2026, stands at over INR18,700 crores")
    assert got[0]["as_of"] == "2026-06-30"
    assert order_book("Order Book of ₹9445 crore, with 120+ orders")[0]["as_of"] is None


def test_order_win_value_from_reg30_table():
    t = ("Size of order/contract Brief details: consideration or size of the order(s)/contract(s) "
         "The Size of Order as per Work Order is Rs 95.14 Crore (excluding GST)")
    assert order_win_value(t)[0]["value"] == 95.14
    t2 = "consideration or size of the order(s)/contract(s) Approximately USD 210 Million 8"
    got = order_win_value(t2)[0]
    assert got["value"] == 210 and got["unit"] == "USD mn" and got["value_cr"] is None
    band = "consideration or size of the order(s)/contract(s) Mega Order Construction of 400 kV line"
    assert order_win_value(band) == []   # banded, value undisclosed


def test_capacity_utilisation_current_only():
    assert capacity_utilisation("Capacity utilization stood at more than 65% in Q1FY27.")[0]["value"] == 65
    assert capacity_utilisation("Capacity utilization stands at around between 65% to 70%.")[0]["value"] == 65
    assert capacity_utilisation("Bhiwadi ~76% Capacity Utilisation Winding Wires")[0]["value"] == 76
    assert capacity_utilisation("in next 1-2 years, we will reach more than 80% capacity utilization") == []
    assert capacity_utilisation("we expect by quarter four to be at around 65% to 70% of that capacity utilization") == []


def test_guidance_quotes_are_sentences_with_numbers():
    t = ("Moderator: Thank you. We stand by the guidance of 15% volume growth. In the first quarter, "
         "we have achieved 20%. The guidance was discussed earlier without numbers.")
    q = guidance_quotes(t)
    assert q == [{"kpi": "guidance", "value": None, "unit": None, "value_cr": None, "as_of": None,
                  "quote": "We stand by the guidance of 15% volume growth."}]


# --- regressions from the 200-document precision review (every numeric extraction read) ---

@pytest.mark.parametrize("text", [
    "order bookings during the quarter of $339 mn",                                   # inflow, not level
    "Order Book New orders reached approximately US$339 million",                     # inflow
    "Order Book Largest Ever Single Tollway Collection Contract of Rs. 328.7 Cr",     # one contract
    "order book, we used to be about INR400 to INR500 crore",                         # history chatter
    "order book is left out around INR830 crores",                                    # remaining on a project
    "order book performance for the third consecutive quarter led by a $25 million",  # deal size
])
def test_order_book_rejects_review_false_positives(text):
    assert order_book(text) == []


def test_order_book_segment_rejected_and_spaced_ordinal_date():
    assert order_book("order book for Segment B stood at over ₹6,345 crores") == []
    got = order_book("Order Book as at 30 th June 2026 of Rs. 27,691 Cr.")
    assert got[0]["value"] == 27691 and got[0]["as_of"] == "2026-06-30"


def test_capacity_utilisation_headline_allows_undated_transcript_status_lines():
    from scanner.kpis import extract_all
    rows = extract_all("Capacity utilization stands at around 65% to 70%.", "Analysts/Institutional Investor "
                       "Meet/Con. Call Updates", "Transcript of earnings call")
    assert [r["value"] for r in rows if r["kpi"] == "capacity_utilisation"] == [65]


def test_order_book_lakh_crore_and_currency_ranges():
    got = order_book("NBCC's order book is INR 2 lakh crore as of June 30, 2026")[0]
    assert got["value_cr"] == 200000 and got["unit"] == "lakh crore"
    got = order_book("an order backlog of US$1.3–1.4 billion")[0]
    assert got["unit"] == "USD bn" and got["value_cr"] is None


def test_headline_order_book_prefers_dated_statement_and_filters_transcript_chatter():
    from scanner.kpis import headline
    rows = order_book("We have the order book of around INR8,700 crores. Our order book as on June 30, 2026 "
                      "stands at INR8,667 crores. INR15,000 crores plus order book is the aspiration.")
    h = headline(rows, "transcript")
    assert [(r["value"], r["as_of"]) for r in h] == [(8667, "2026-06-30")]
    assert headline(order_book("INR15,000 crores plus order book is possible"), "transcript") == []
    assert headline(order_book("Order Book of ₹9445 crore, with 120+ orders"), "presentation")[0]["value"] == 9445
