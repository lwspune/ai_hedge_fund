"""Test-first spec for the filing -> KPI pipeline pieces (PDF text + row mapping)."""
import fitz

from scanner.kpis import kpi_rows, pdf_text


def _pdf(pages: list[str]) -> bytes:
    doc = fitz.open()
    for text in pages:
        doc.new_page().insert_text((72, 72), text)
    return doc.tobytes()


def test_pdf_text_reads_pages_and_caps_them():
    data = _pdf(["Order Book of Rs 9445 crore", "second page", "third page"])
    text, n = pdf_text(data, max_pages=2)
    assert n == 3 and "9445" in text and "second page" in text and "third page" not in text


def test_pdf_text_rejects_non_pdf():
    assert pdf_text(b"<html>not a pdf</html>") == (None, 0)


def test_kpi_rows_attach_filing_identity():
    filing = {"seq_id": 7, "symbol": "RITES", "disclosed_at": "2026-08-05T18:00:00+05:30"}
    extracted = [{"kpi": "order_book", "value": 9445, "unit": "crore", "value_cr": 9445.0,
                  "as_of": None, "quote": "Order Book of ₹9445 crore"}]
    assert kpi_rows(filing, extracted) == [{
        "seq_id": 7, "symbol": "RITES", "disclosed_at": "2026-08-05T18:00:00+05:30",
        "kpi": "order_book", "value": 9445, "unit": "crore", "value_cr": 9445.0, "as_of": None,
        "quote": "Order Book of ₹9445 crore", "method": "rule_v1"}]
