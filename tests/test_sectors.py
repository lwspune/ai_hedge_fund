"""Test-first spec for sector indices (scanner/sectors.py, docs/SECTOR_INDICES_SPEC.md §2-3): the reviewed
industry -> sector index map, the index each stock uses (primary until it has a year of history, then
fallback, then NIFTY 500), and the latest-day sector table. Synthetic data only, no network."""
import json

import numpy as np
import pandas as pd
import pytest

from scanner import sectors
from scanner.sectors import (N500, load_sector_indices, load_sector_map, pick_index, sector_rows,
                             sector_symbols)

# NSE industries of listed mainboard companies on 2026-10-01 (company_snapshot.industry). A new NSE industry
# fails test_every_industry_is_mapped until data/sector_map.csv has a row for it.
INDUSTRIES = [
    "Chemicals & Petrochemicals", "Fertilizers & Agrochemicals", "Cement & Cement Products",
    "Paper, Forest & Jute Products", "Ferrous Metals", "Non - Ferrous Metals", "Minerals & Mining",
    "Metals & Minerals Trading", "Other Construction Materials", "Diversified Metals", "Consumer Durables",
    "Textiles & Apparels", "Auto Components", "Realty", "Leisure Services", "Retailing", "Entertainment",
    "Other Consumer Services", "Automobiles", "Media", "Printing & Publication", "Diversified", "Oil",
    "Petroleum Products", "Gas", "Consumable Fuels", "Agricultural Food & other Products", "Food Products",
    "Beverages", "Household Products", "Personal Products", "Diversified FMCG", "Cigarettes & Tobacco Products",
    "Finance", "Capital Markets", "Banks", "Insurance", "Financial Technology (Fintech)",
    "Pharmaceuticals & Biotechnology", "Healthcare Services", "Healthcare Equipment & Supplies",
    "Industrial Products", "Construction", "Industrial Manufacturing", "Electrical Equipment",
    "Aerospace & Defense", "Agricultural, Commercial & Construction Vehicles", "IT - Software", "IT - Services",
    "IT - Hardware", "Commercial Services & Supplies", "Transport Services", "Transport Infrastructure",
    "Engineering Services", "Telecom - Services", "Telecom -  Equipment & Accessories", "Power",
    "Other Utilities",
]


# --- the reviewed map ------------------------------------------------------------------

def test_every_industry_is_mapped():
    smap = load_sector_map()
    missing = [i for i in INDUSTRIES if i not in smap]
    assert not missing, f"unmapped NSE industries: {missing}"
    assert set(smap) == set(INDUSTRIES)                         # no stray rows either


def test_map_targets_are_loadable_indices():
    smap = load_sector_map()
    syms = set(sector_symbols())
    for ind, (primary, fallback) in smap.items():
        for idx in (primary, fallback):
            assert idx == N500 or idx in syms, f"{ind}: {idx} not in data/sector_indices.csv"
        assert (primary == N500) == (fallback == N500), ind     # NIFTY 500 only as both (Diversified)
    assert smap["Banks"] == ("Nifty Bank", "Nifty Financial Services")
    assert smap["Industrial Products"] == ("Nifty Capital Goods", "Nifty India Manufacturing")
    assert smap["Diversified"] == (N500, N500)


def test_sector_indices_resolve_names_and_aliases_uniquely():
    names = load_sector_indices()
    assert names["nifty bank"] == "Nifty Bank" and names["nifty it"] == "Nifty IT"
    assert all(k == k.lower() for k in names)
    assert len(sector_symbols()) == len(set(sector_symbols())) == 30
    assert N500 not in sector_symbols()


# --- which index a stock uses --------------------------------------------------------------

def test_pick_index_prefers_a_primary_with_a_year_of_history():
    smap = {"Industrial Products": ("Nifty Capital Goods", "Nifty India Manufacturing"),
            "Diversified": (N500, N500)}
    assert sectors.MIN_SECTOR_SESSIONS == 250
    full = {"Nifty Capital Goods": 260, "Nifty India Manufacturing": 270}
    assert pick_index("Industrial Products", full, smap) == ("Nifty Capital Goods", False)
    young = {"Nifty Capital Goods": 40, "Nifty India Manufacturing": 270}
    assert pick_index("Industrial Products", young, smap) == ("Nifty India Manufacturing", True)
    assert pick_index("Industrial Products", {"Nifty Capital Goods": 40}, smap) == (N500, True)
    assert pick_index("Diversified", {}, smap) == (N500, False)
    assert pick_index("Something New", full, smap) == (None, False)
    assert pick_index(None, full, smap) == (None, False)


# --- the sector table -------------------------------------------------------------------------

def _series(values, start="2025-01-01"):
    return pd.Series(np.asarray(values, dtype=float), index=pd.bdate_range(start, periods=len(values)))


def test_sector_rows():
    bank = _series(list(np.linspace(100, 120, 60)) + [90.0] * 4 + [110.0])     # peak 120, now 110
    n500 = _series(np.linspace(200, 210, 65))
    last = bank.index[-1]
    states = {f"B{i}": (True, i < 3) for i in range(5)}                            # 5 eligible, 3 above 200-DMA
    states["X"] = (False, True)                                                     # outside the universe
    rows = {r["index_name"]: r for r in sector_rows(
        {"Nifty Bank": bank, "Nifty IT": _series([50.0] * 30)}, n500, states,
        {**{s: "Nifty Bank" for s in states}, "T1": "Nifty IT", "D": N500})}
    r = rows["Nifty Bank"]
    json.dumps(r)
    assert r["as_of"] == last.date().isoformat() and r["close"] == 110.0
    assert r["dd"] == pytest.approx(110 / 120 - 1, abs=1e-4)
    assert r["ret_1m"] == pytest.approx(110 / bank.iloc[-22] - 1, abs=1e-4)
    assert r["ret_3m"] == pytest.approx(110 / bank.iloc[-64] - 1, abs=1e-4)
    assert r["rel_3m"] == pytest.approx(r["ret_3m"] - (210 / n500.iloc[-64] - 1), abs=1e-4)
    assert r["n_stocks"] == 5 and r["pct_above_200"] == pytest.approx(0.6)
    it = rows["Nifty IT"]
    assert it["ret_3m"] is None and it["rel_3m"] is None                            # 30 closes: no 63-session return
    assert it["n_stocks"] == 0 and it["pct_above_200"] is None                     # < 5 stocks: no share
    assert N500 not in rows                                                         # the benchmark is not a sector row
