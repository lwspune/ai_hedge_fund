"""Telegram alerts for new Act candidates (scanner/notify.py) -> your chat, once per opportunity.

    python scripts/notify_telegram.py              # latest buyback_arb + rights_re scans; send what's new
    python scripts/notify_telegram.py --dry-run    # print what would be sent; send/record nothing
    python scripts/notify_telegram.py --test       # one hello message (setup check)

Needs TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID (Actions secrets, or .env locally). A key is recorded in
`alerts_sent` only after Telegram accepts the message: a failed record can repeat an alert, never
drop one. Any failed send fails the run (GitHub emails the owner).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner import db  # noqa: E402
from scanner.notify import buyback_alerts, new_alerts, rights_alerts  # noqa: E402

SIGNALS = {"buyback_arb": buyback_alerts, "rights_re": rights_alerts}


def latest_candidates(signal: str) -> list[dict]:
    run = db.select("scan_runs", {"select": "id", "signal_name": f"eq.{signal}",
                                  "order": "run_at.desc", "limit": "1"})
    if not run:
        return []
    return db.select_all("candidates", {"select": "symbol,score,payload", "run_id": f"eq.{run[0]['id']}"})


def send(token: str, chat_id: str, text: str) -> str | None:
    """POST one message; None on success, else the error (never the URL: it holds the token)."""
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=20,
                          json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                                "disable_web_page_preview": True})
    except requests.RequestException as e:
        return type(e).__name__
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    return None if r.ok and body.get("ok") else f"{r.status_code} {body.get('description', '')}"


def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    db._load_env()
    token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not dry and not (token and chat_id):
        sys.exit("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set (Actions secrets or .env).")
    if "--test" in args:
        err = send(token, chat_id, "Market-intel alerts connected ✅")
        sys.exit(f"test send failed: {err}" if err else 0)

    alerts = [a for sig, build in SIGNALS.items() for a in build(latest_candidates(sig))]
    sent = {(r["signal_name"], r["alert_key"])
            for r in db.select_all("alerts_sent", {"select": "signal_name,alert_key"})}
    todo = new_alerts(alerts, sent)
    print(f"{len(alerts)} actionable candidates, {len(todo)} new")
    failed = 0
    for a in todo:
        if dry:
            print(f"--- {a['signal_name']} {a['alert_key']}\n{a['text']}")
            continue
        err = send(token, chat_id, a["text"])
        if err:
            failed += 1
            print(f"[send failed] {a['signal_name']} {a['alert_key']}: {err}")
            continue
        db.insert("alerts_sent", {"signal_name": a["signal_name"], "alert_key": a["alert_key"],
                                  "message": a["text"]},
                  on_conflict="signal_name,alert_key", ignore_duplicates=True, return_rows=False)
        print(f"[sent] {a['signal_name']} {a['alert_key']}")
    if failed:
        sys.exit(f"{failed} alert(s) failed to send")


if __name__ == "__main__":
    main()
