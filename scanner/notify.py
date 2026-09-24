"""Telegram alerts for new Act candidates (pure logic; sending lives in scripts/notify_telegram.py).

An alert is a dict {signal_name, alert_key, text}. alert_key identifies the *opportunity*, not the
scan row, so the same open tender seen on ten daily scans alerts once (`alerts_sent` is unique on
(signal_name, alert_key)).
"""
from __future__ import annotations

from html import escape
from urllib.parse import quote

DASHBOARD = "https://ai-hedge-fund-gamma.vercel.app/"
BUY_RE = "BUY RE"  # prefix of scanner.rights.re_action's actionable verdict


def _pct(v, digits=1) -> str:
    return "—" if v is None else f"{v * 100:.{digits}f}%"


def _link(symbol: str) -> str:
    return f'<a href="{DASHBOARD}#/company/{quote(symbol, safe="")}">dashboard</a>'


def buyback_alerts(candidates: list[dict]) -> list[dict]:
    """Open tenders from a buyback_arb scan -> alerts, keyed symbol|record_date."""
    out = []
    for c in candidates:
        p = c.get("payload") or {}
        if not p.get("is_open"):
            continue
        sym = c["symbol"]
        text = (f"<b>Buyback open: {escape(sym)}</b>\n"
                f"buyback ₹{p['buyback_price']:,.0f} vs price ₹{p['cur_price']:,.0f} "
                f"(premium {_pct(p.get('premium'))})\n"
                f"est acceptance {_pct(p.get('est_acceptance'), 0)} · "
                f"exp after-tax {_pct(p.get('exp_return'))}\n"
                f"record {p.get('record_date') or '—'} · closes {p.get('close_date') or '—'}\n"
                f"Edge holds only at a tax slab ≤20%. Verify before acting · {_link(sym)}")
        out.append({"signal_name": "buyback_arb", "alert_key": f"{sym}|{p.get('record_date')}",
                    "text": text})
    return out


def rights_alerts(candidates: list[dict]) -> list[dict]:
    """'BUY RE' entitlements from a rights_re scan -> alerts, keyed symbol|re_last_day."""
    out = []
    for c in candidates:
        p = c.get("payload") or {}
        if not str(p.get("action", "")).startswith(BUY_RE):
            continue
        sym = c["symbol"]
        text = (f"<b>Rights RE discount: {escape(sym)}</b>\n"
                f"RE trades {_pct(p.get('gap'))} below stock − issue price "
                f"(issue ₹{p['issue_price']:.2f}, ratio {escape(str(p.get('ratio') or '—'))})\n"
                f"buy the RE instead of the stock, then subscribe\n"
                f"RE last day {p.get('re_last_day') or '—'} · apply by {p.get('issue_close') or '—'}\n"
                f"{_link(sym)}")
        out.append({"signal_name": "rights_re", "alert_key": f"{sym}|{p.get('re_last_day')}",
                    "text": text})
    return out


def new_alerts(alerts: list[dict], sent: set[tuple[str, str]]) -> list[dict]:
    """Drop alerts already sent (and repeats within this batch), keeping order."""
    seen = set(sent)
    out = []
    for a in alerts:
        k = (a["signal_name"], a["alert_key"])
        if k not in seen:
            seen.add(k)
            out.append(a)
    return out
