"""JSON file store. No database."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from app.models import Review

_LOCK = threading.Lock()
_DEFAULT = Path(__file__).resolve().parents[1] / "data" / "reviews.json"


def data_path() -> Path:
    return Path(os.environ.get("PATCHPROOF_DATA", str(_DEFAULT)))


def _read() -> list[dict]:
    path = data_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []


def _write(rows: list[dict]) -> None:
    path = data_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def list_reviews() -> list[Review]:
    with _LOCK:
        return [Review.model_validate(row) for row in _read()]


def get_review(review_id: str) -> Review | None:
    for review in list_reviews():
        if review.id == review_id:
            return review
    return None


def save_review(review: Review) -> Review:
    with _LOCK:
        rows = [row for row in _read() if row.get("id") != review.id]
        rows.insert(0, review.model_dump())
        _write(rows)
    return review


def set_resolved(review_id: str, finding_id: str, resolved: bool) -> Review | None:
    with _LOCK:
        rows = _read()
        for row in rows:
            if row.get("id") != review_id:
                continue
            for finding in row.get("findings") or []:
                if finding.get("id") == finding_id:
                    finding["resolved"] = resolved
                    _write(rows)
                    return Review.model_validate(row)
        return None


def stats() -> dict:
    reviews = list_reviews()
    introduced = [f for review in reviews for f in review.findings]
    unresolved = [f for f in introduced if not f.resolved]
    return {
        "reviews": len(reviews),
        "sample_reviews": sum(1 for review in reviews if review.source == "sample"),
        "findings": len(introduced),
        "critical_high": sum(1 for f in unresolved if f.severity in {"critical", "high"}),
        "resolved": sum(1 for f in introduced if f.resolved),
        "unresolved": len(unresolved),
        "recent": [
            {
                "id": review.id,
                "title": review.title,
                "filename": review.filename,
                "source": review.source,
                "created_at": review.created_at,
                "findings": len(review.findings),
                "pre_existing": len(review.pre_existing),
                "critical_high": sum(1 for f in review.findings if f.severity in {"critical", "high"} and not f.resolved),
            }
            for review in reviews[:8]
        ],
    }
