"""Every module and script must at least compile — a broken string literal in a script that
no test imports (scanner/run.py, 2026-09-24) otherwise slips past the suite and fails in CI's
scheduled refresh instead."""
import py_compile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FILES = sorted([*ROOT.glob("scanner/*.py"), *ROOT.glob("scripts/*.py")])


@pytest.mark.parametrize("path", FILES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_compiles(path):
    py_compile.compile(str(path), doraise=True)
