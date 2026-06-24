"""Emit the signal registry (verdicts) as JSON for the dashboard.

Single source of truth is scanner/catalog.py; re-run this whenever the catalog
changes so the frontend's verdict badges stay in sync.

    python scripts/emit_signals_json.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner.catalog import list_signals  # noqa: E402

DEST = Path(__file__).resolve().parent.parent / "dashboard" / "src" / "signals.json"


def main():
    data = [asdict(m) for m in list_signals()]
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"wrote {len(data)} signals -> {DEST}")


if __name__ == "__main__":
    main()
