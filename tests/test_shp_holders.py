"""Test-first spec for the named holders in an SHP XBRL (SEBI names every public holder >= 1% and
every promoter-group holder). One row per named holder: the typed-member axis it sits under, the
name, shares, % of total shares and the holder count.

A holder's name lives in a duration context and its numbers in the instant context with the same
typed-member value; context ids differ by taxonomy (`001D`/`001I` in 2021, `D_x`/`x` in 2025-10),
so pairing is by the typed member. The % is shares / total shares — the taxonomies disagree on
units (2021: 2.14 = 2.14%; 2025-10: 0.0192 = 1.92%). Fixtures are trimmed from real filings
(GRAVITA Sep-2021, DMART Jun-2026)."""
from pathlib import Path

import pytest

from scanner.shareholding import parse_shp_holders

FIX = Path(__file__).parent / "fixtures"


def _by_name(rows):
    return {r["name"]: r for r in rows}


def test_old_taxonomy_pairs_name_and_numbers_by_typed_member():
    rows = _by_name(parse_shp_holders((FIX / "shp_holders_2021.xml").read_text(encoding="utf-8")))
    atul = rows["ATUL KUCHHAL"]
    assert atul["axis"] == "IndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh"
    assert atul["shares"] == 1479156
    assert atul["pct"] == pytest.approx(1479156 / 69037914 * 100, abs=1e-4)  # 2.14%, not 214%
    assert atul["n_holders"] == 1
    assert rows["RAJAT AGRAWAL"]["axis"] == "IndividualsOrHUF"
    assert rows["RAJAT AGRAWAL"]["pct"] == pytest.approx(47.87, abs=0.01)


def test_category_aggregate_rows_are_not_holders():
    # "Bodies Corporate" is a sub-category total (164 holders), not a named shareholder
    names = _by_name(parse_shp_holders((FIX / "shp_holders_2021.xml").read_text(encoding="utf-8")))
    assert "Bodies Corporate" not in names
    assert len(names) == 4


def test_new_taxonomy_fraction_units_and_entity_unescape():
    rows = _by_name(parse_shp_holders((FIX / "shp_holders_2026.xml").read_text(encoding="utf-8")))
    ign = rows["Ignatius Navil Noronha"]  # whitespace collapsed
    assert ign["axis"] == "ResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh"
    assert ign["pct"] == pytest.approx(12529072 / 652245977 * 100, abs=1e-4)  # 1.92%, not 0.0192
    assert rows["ICICI Prudential Mutual Fund"]["axis"] == "MutualFundsOrUTI"
    assert rows["ICICI Prudential Mutual Fund"]["shares"] == 15231593
    assert rows["The Growth Fund Of America"]["axis"] == "InstitutionsForeignPortfolioInvestorOne"
    assert rows["Radhakishan Shivkishan Damani"]["axis"] == "IndividualsOrHUF"


def test_zero_share_rows_are_dropped():
    # promoter-group entity listed with 0 shares (and the &amp; would otherwise leak through)
    names = _by_name(parse_shp_holders((FIX / "shp_holders_2026.xml").read_text(encoding="utf-8")))
    assert "Health & Glow Private Limited" not in names
    assert not any("&amp;" in n for n in names)


def test_unrecognised_document_gives_no_rows():
    assert parse_shp_holders("<html>not xbrl</html>") == []
