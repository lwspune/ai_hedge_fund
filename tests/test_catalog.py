"""Test-first spec for the signal registry (the platform's honesty layer)."""
import pytest

from scanner.catalog import (
    SIGNALS, get_signal, list_signals, VERDICTS, ROLES, TYPES,
)

EXPECTED = {"buyback_arb", "mean_reversion", "smart_money_deals",
            "merger_arb", "open_offer_arb"}


def test_all_validated_signals_registered():
    assert set(SIGNALS) == EXPECTED


def test_every_signal_has_valid_metadata():
    for meta in list_signals():
        assert meta.type in TYPES
        assert meta.verdict in VERDICTS
        assert meta.role in ROLES
        assert meta.summary  # non-empty one-liner


def test_only_buyback_is_primary():
    primaries = [m.name for m in list_signals() if m.role == "primary"]
    assert primaries == ["buyback_arb"]


def test_drift_signals_marked_null():
    for name in ("mean_reversion", "smart_money_deals"):
        assert get_signal(name).meta.verdict == "null"


def test_get_signal_has_callable_run():
    assert callable(get_signal("buyback_arb").run)


def test_get_unknown_signal_raises():
    with pytest.raises(KeyError):
        get_signal("does_not_exist")
