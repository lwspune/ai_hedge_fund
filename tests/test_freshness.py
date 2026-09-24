"""The freshness check: every table's newest row must be within its expected cadence."""
from datetime import date

from scripts.check_freshness import RULES, stale


def test_stale_flags_old_and_missing_tables_only():
    today = date(2026, 9, 24)
    latest = {"deals": date(2026, 9, 23), "corporate_actions": date(2026, 9, 10),
              "ipo_listings": None}
    rules = {"deals": 6, "corporate_actions": 7, "ipo_listings": 14}
    assert stale(latest, rules, today) == [
        ("corporate_actions", date(2026, 9, 10), 14, 7),
        ("ipo_listings", None, None, 14),
    ]
    assert stale({"deals": date(2026, 9, 18)}, {"deals": 6}, today) == []   # exactly 6 days: ok


def test_rules_cover_the_scheduled_tables():
    assert set(RULES) >= {"deals", "corporate_actions", "ipo_listings", "companies", "fundamentals"}
