"""Test-first spec for the bulk/block-deal 'smart money' signal.

Client names below are taken verbatim from a live NSE bulk/block CSV pull, so
the classifier is tested against the real-world noise it must separate.
"""
from scanner.deals import (
    classify_client,
    is_notable_buy,
    aggregate_by_symbol,
    NOTABLE,
)


# --- client classification ---------------------------------------------------

def test_mutual_funds_are_notable():
    for n in ["INVESCO MUTUAL FUND", "FRANKLIN TEMPLETON MUTUAL FUND"]:
        assert classify_client(n) == "mutual_fund"
        assert "mutual_fund" in NOTABLE


def test_insurer_is_notable():
    assert classify_client("LIFE INSURANCE CORPORATION OF INDIA") == "insurance"
    assert "insurance" in NOTABLE


def test_foreign_asset_manager_is_notable():
    # FII-style account from real block data.
    n = "MERRILL LYNCH INVESTMENT MANAGERS LIMITED A/C. MLI EQ.F (MAU"
    assert classify_client(n) == "asset_manager"
    assert "asset_manager" in NOTABLE


def test_prop_llp_broker_is_noise():
    # These dominate bulk data and are mostly two-sided / arbitrage -> not signal.
    for n in ["QE SECURITIES LLP", "GRT STRATEGIC VENTURES LLP",
              "SILVERLEAF CAPITAL SERVICES PRIVATE LIMITED"]:
        assert classify_client(n) == "prop_broker"
        assert "prop_broker" not in NOTABLE


def test_unknown_name_is_other():
    assert classify_client("RAMESH KUMAR SHAH") == "other"


# --- notable-buy gate --------------------------------------------------------

def _deal(client, side, qty, price):
    return {"symbol": "X", "client": client, "side": side,
            "qty": qty, "price": price, "value": qty * price}


def test_is_notable_buy_true_for_fund_buy_over_threshold():
    d = _deal("INVESCO MUTUAL FUND", "BUY", 100000, 250.0)  # 2.5 cr
    assert is_notable_buy(d, value_min=1_00_00_000) is True  # >= 1 cr


def test_is_notable_buy_false_for_sell():
    d = _deal("INVESCO MUTUAL FUND", "SELL", 100000, 250.0)
    assert is_notable_buy(d, value_min=1_00_00_000) is False


def test_is_notable_buy_false_for_prop_broker():
    d = _deal("QE SECURITIES LLP", "BUY", 100000, 250.0)
    assert is_notable_buy(d, value_min=1_00_00_000) is False


def test_is_notable_buy_false_below_threshold():
    d = _deal("INVESCO MUTUAL FUND", "BUY", 100, 250.0)  # 25k
    assert is_notable_buy(d, value_min=1_00_00_000) is False


# --- aggregation -------------------------------------------------------------

def test_aggregate_ranks_by_distinct_institutions_then_value():
    deals = [
        _deal_sym("CRAFTSMAN", "FRANKLIN TEMPLETON MUTUAL FUND", "BUY", 30000, 9250),
        _deal_sym("CRAFTSMAN", "INVESCO MUTUAL FUND", "BUY", 100000, 9250),
        _deal_sym("ABC", "LIFE INSURANCE CORPORATION OF INDIA", "BUY", 50000, 1000),
        _deal_sym("NOISE", "QE SECURITIES LLP", "BUY", 100000, 250),   # dropped (prop)
        _deal_sym("CRAFTSMAN", "SOME MUTUAL FUND", "SELL", 1000, 9250),  # dropped (sell)
    ]
    out = aggregate_by_symbol(deals, value_min=1_00_00_000)
    assert [r["symbol"] for r in out] == ["CRAFTSMAN", "ABC"]
    top = out[0]
    assert top["n_buyers"] == 2
    assert top["total_value"] == (30000 + 100000) * 9250
    assert "NOISE" not in [r["symbol"] for r in out]


def _deal_sym(symbol, client, side, qty, price):
    return {"symbol": symbol, "client": client, "side": side,
            "qty": qty, "price": price, "value": qty * price}
