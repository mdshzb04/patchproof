"""Demo pull request built from real before/after sources."""

from __future__ import annotations

import difflib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def _read(tree: str, rel: str) -> str:
    return (EXAMPLES / tree / rel).read_text(encoding="utf-8")


def _unified(before: str, after: str, rel: str) -> str:
    old = _read(before, rel)
    new = _read(after, rel)
    if old == new:
        return ""
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
            n=10000,
        )
    )


def demo_diff() -> str:
    parts = [
        _unified("before", "after", "service/jobs.py"),
        _unified("before", "after", "utils/labels.py"),
    ]
    text = "".join(parts)
    if not text.strip():
        raise RuntimeError("Demo diff is empty.")
    return text


def safe_fix_diff() -> str:
    text = _unified("after", "fixed", "service/jobs.py")
    if not text.strip():
        raise RuntimeError("Safe-fix diff is empty.")
    return text


def write_example_files() -> None:
    (EXAMPLES / "demo_pr.diff").write_text(demo_diff(), encoding="utf-8")
    (EXAMPLES / "safe_fix.diff").write_text(safe_fix_diff(), encoding="utf-8")
