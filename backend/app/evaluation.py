"""Small labelled benchmark. Metrics come from running the engine on these files."""

from __future__ import annotations

import json
from pathlib import Path

from app.rules import analyze_ast, dedupe

ROOT = Path(__file__).resolve().parents[1] / "benchmark"
MANIFEST = ROOT / "manifest.json"


def load_cases() -> list[dict]:
    cases = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for case in cases:
        case["source"] = (ROOT / case["file"]).read_text(encoding="utf-8")
    return cases


def score_cases(cases: list[dict] | None = None) -> dict:
    cases = cases if cases is not None else load_cases()
    rows = []
    tp = fp = tn = fn = 0
    for case in cases:
        found = sorted({item.rule_id for item in dedupe(analyze_ast(case["source"], case["file"]))})
        expected = sorted(set(case["expect"]))
        hit = sorted(set(expected) & set(found))
        missed = sorted(set(expected) - set(found))
        extra = sorted(set(found) - set(expected))
        if expected:
            tp += len(hit)
            fn += len(missed)
            fp += len(extra)
        else:
            if found:
                fp += len(found)
            else:
                tn += 1
        rows.append(
            {
                "id": case["id"],
                "file": case["file"],
                "label": case["label"],
                "expect": expected,
                "found": found,
                "missed": missed,
                "extra": extra,
                "pass": not missed and not extra,
            }
        )
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "sample_count": len(cases),
        "vulnerable_count": sum(1 for c in cases if c["expect"]),
        "safe_count": sum(1 for c in cases if not c["expect"]),
        "true_positives": tp,
        "false_positives": fp,
        "true_negatives": tn,
        "false_negatives": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "cases": rows,
        "disclaimer": (
            "This is a small controlled test set written for PatchProof. "
            "It is not a measurement of detection quality on real repositories."
        ),
    }
