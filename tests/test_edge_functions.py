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
