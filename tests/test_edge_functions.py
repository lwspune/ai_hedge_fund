"""Edge functions must allow every header supabase-js sends, or the browser's CORS preflight
fails and the dashboard Refresh buttons die with 'Failed to send a request to the Edge Function'."""
import re
from pathlib import Path

import pytest

FUNCS = sorted((Path(__file__).resolve().parent.parent / "supabase" / "functions").glob("*/index.ts"))
SDK_HEADERS = {"authorization", "x-client-info", "apikey", "content-type"}


@pytest.mark.parametrize("src", FUNCS, ids=lambda p: p.parent.name)
def test_cors_allows_supabase_js_headers(src):
    m = re.search(r'"Access-Control-Allow-Headers":\s*"([^"]+)"', src.read_text(encoding="utf-8"))
    assert m, "no Access-Control-Allow-Headers"
    allowed = {h.strip().lower() for h in m.group(1).split(",")}
    assert SDK_HEADERS <= allowed, f"missing {SDK_HEADERS - allowed}"


# --- refresh-buybacks parser parity with scanner.buyback (WP1) -----------------

import json
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.parametrize("bid", [213, 219, 225])
def test_refresh_buybacks_ts_parser_matches_python(bid):
    from scanner.buyback import parse_buyback
    fx = ROOT / "tests" / "fixtures" / "buyback" / f"{bid}.html"
    out = subprocess.run(["node", str(ROOT / "tests" / "js" / "buyback_parse.cjs"),
                          str(ROOT / "supabase" / "functions" / "refresh-buybacks" / "index.ts"),
                          str(fx), str(bid)], capture_output=True, text=True, check=True)
    ts = json.loads(out.stdout)
    py = parse_buyback(fx.read_text(encoding="utf-8"), bid)
    assert ts["symbol"] == py["symbol"]
    assert ts["buyback_price"] == py["buyback_price"]
    assert ts["record_date"] == py["record_date"].date().isoformat()
    assert ts["close_date"] == py["close_date"].date().isoformat()
    assert ts["entitlement_small"] == pytest.approx(py["entitlement_small"])
    assert ts["issue_size_cr"] == pytest.approx(py["issue_size_cr"])
