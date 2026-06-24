"""Supabase persistence via raw PostgREST (no ORM, no SDK).

Pure row-builders (tested) map domain dicts to table rows; thin `requests` calls
hit `{SUPABASE_URL}/rest/v1/<table>`. Credentials come from .env / environment.
Run `db/schema.sql` in Supabase once before using.
"""
from __future__ import annotations

import os
from pathlib import Path

import requests

_ENV_LOADED = False


def _load_env() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    _ENV_LOADED = True


def config() -> tuple[str, str]:
    _load_env()
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError(
            "Persistence needs SUPABASE_URL and SUPABASE_SERVICE_KEY (set them in .env).")
    return url.rstrip("/"), key


def _headers(key: str, prefer: str) -> dict:
    return {"apikey": key, "Authorization": f"Bearer {key}",
            "Content-Type": "application/json", "Prefer": prefer}


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") and not isinstance(v, str) else v


# --- pure row builders -------------------------------------------------------

def scan_run_row(signal_name: str, verdict: str, n_candidates: int, params=None) -> dict:
    return {"signal_name": signal_name, "verdict": verdict,
            "n_candidates": n_candidates, "params": params or {}}


def candidate_row(run_id, signal_name, symbol, score=None, payload=None) -> dict:
    return {"run_id": run_id, "signal_name": signal_name, "symbol": symbol,
            "score": score, "payload": payload or {}}


def buyback_row(bb: dict, est_return=None) -> dict:
    return {"chittorgarh_id": bb.get("id"), "company": bb.get("company"),
            "symbol": bb.get("symbol"), "buyback_price": bb.get("buyback_price"),
            "record_date": _iso(bb.get("record_date")), "close_date": _iso(bb.get("close_date")),
            "entitlement_small": bb.get("entitlement_small"),
            "est_return": est_return if est_return is not None else bb.get("est_return")}


def tender_row(buyback_id, decided_on, shares_bought=None, avg_cost=None,
               capital=None, tendered=True, notes=None) -> dict:
    return {"buyback_id": buyback_id, "decided_on": _iso(decided_on),
            "shares_bought": shares_bought, "avg_cost": avg_cost, "capital": capital,
            "tendered": tendered, "notes": notes}


def outcome_row(tender_id, accepted_shares=None, realized_acceptance=None,
                residual_sold_price=None, realized_return=None) -> dict:
    return {"tender_id": tender_id, "accepted_shares": accepted_shares,
            "realized_acceptance": realized_acceptance,
            "residual_sold_price": residual_sold_price, "realized_return": realized_return}


# --- REST primitives ---------------------------------------------------------

def insert(table: str, rows, on_conflict: str | None = None,
           return_rows: bool = True) -> list[dict]:
    url, key = config()
    if isinstance(rows, dict):
        rows = [rows]
    ret = "representation" if return_rows else "minimal"
    prefer = f"return={ret}"
    params = {}
    if on_conflict:
        prefer = f"resolution=merge-duplicates,return={ret}"
        params = {"on_conflict": on_conflict}
    r = requests.post(f"{url}/rest/v1/{table}", headers=_headers(key, prefer),
                      params=params, json=rows, timeout=30)
    r.raise_for_status()
    return r.json() if return_rows else []


def select(table: str, params: dict | None = None) -> list[dict]:
    url, key = config()
    r = requests.get(f"{url}/rest/v1/{table}", headers=_headers(key, "count=none"),
                     params=params or {}, timeout=20)
    r.raise_for_status()
    return r.json()


# --- high-level helpers ------------------------------------------------------

def log_scan(signal_name: str, verdict: str, candidates: list[dict] | None = None,
             params: dict | None = None) -> int:
    """Log a scan run and its candidates; returns run id. candidate dicts need a
    'symbol' and optionally 'score'/'payload'."""
    candidates = candidates or []
    run = insert("scan_runs", scan_run_row(signal_name, verdict, len(candidates), params))[0]
    rid = run["id"]
    if candidates:
        insert("candidates", [candidate_row(rid, signal_name, c["symbol"],
                                             c.get("score"), c.get("payload")) for c in candidates])
    return rid


def upsert_buybacks(buybacks: list[dict]) -> list[dict]:
    """Upsert buyback masters (idempotent on chittorgarh_id)."""
    rows = [bb if "chittorgarh_id" in bb else buyback_row(bb, bb.get("est_return"))
            for bb in buybacks]
    return insert("buybacks", rows, on_conflict="chittorgarh_id")


def record_tender(buyback_id, decided_on, **kw) -> dict:
    return insert("tenders", tender_row(buyback_id, decided_on, **kw))[0]


def record_outcome(tender_id, **kw) -> dict:
    return insert("outcomes", outcome_row(tender_id, **kw))[0]


def max_buyback_id() -> int | None:
    """Highest chittorgarh_id stored — the frontier for the upward scan probe."""
    rows = select("buybacks", {"select": "chittorgarh_id",
                               "order": "chittorgarh_id.desc", "limit": "1"})
    return rows[0]["chittorgarh_id"] if rows else None


def check_connection() -> bool:
    select("buybacks", {"limit": "1"})
    return True
