"""Test-first spec for the signal registry (the platform's honesty layer)."""
import pytest

from scanner.catalog import (
    SIGNALS, get_signal, list_signals, VERDICTS, ROLES, TYPES,
)

EXPECTED = {"buyback_arb", "mean_reversion", "smart_money_deals",
            "merger_arb", "open_offer_arb", "index_rebalance", "lockin_expiry",
            "fno_ban", "rights_re", "promoter_buying"}


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


def test_dashboard_signals_json_in_sync_with_catalog():
    """The dashboard's verdict badges must match the registry (re-run scripts/emit_signals_json.py)."""
    import json
    from dataclasses import asdict
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "dashboard" / "src" / "signals.json"
    assert json.loads(path.read_text(encoding="utf-8")) == [asdict(m) for m in list_signals()]


def test_lockin_expiry_is_a_conditional_lens_not_a_trade():
    m = get_signal("lockin_expiry").meta
    assert (m.type, m.verdict, m.role) == ("structural", "conditional", "lens")


def test_fno_ban_is_a_null_lens():
    m = get_signal("fno_ban").meta
    assert (m.verdict, m.role) == ("null", "lens")


def test_rights_re_is_a_conditional_spread_to_watch():
    m = get_signal("rights_re").meta
    assert (m.type, m.verdict, m.role) == ("spread", "conditional", "watch")


def test_promoter_buying_is_a_null_lens():
    m = get_signal("promoter_buying").meta
    assert (m.type, m.verdict, m.role) == ("drift", "null", "lens")
