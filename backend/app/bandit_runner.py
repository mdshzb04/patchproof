"""Run Bandit as a subprocess. Never imports or executes the code under review."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from app.models import Finding
from app.rules import make_finding

BANDIT_MAP = {
    "B602": "PP001",
    "B604": "PP001",
    "B605": "PP001",
    "B307": "PP002",
    "B102": "PP002",
    "B301": "PP003",
    "B506": "PP004",
    "B105": "PP005",
    "B106": "PP005",
    "B107": "PP005",
    "B501": "PP006",
    "B306": "PP007",
    "B303": "PP008",
    "B324": "PP008",
    "B304": "PP008",
    "B305": "PP008",
    "B608": "PP009",
    "B110": "PP010",
    "B112": "PP010",
}

SEVERITY = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}
CONFIDENCE = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}


def bandit_available() -> bool:
    return shutil.which("bandit") is not None or _module_exists()


def _module_exists() -> bool:
    try:
        import bandit  # noqa: F401

        return True
    except Exception:
        return False


def run_bandit(files: list[tuple[str, str]]) -> tuple[list[Finding], str]:
    """Return findings and a short status detail. files are (relative path, source)."""
    py_files = [(path, source) for path, source in files if path.endswith(".py") and source.strip()]
    if not py_files:
        return [], "No Python files to scan."
    if not _module_exists() and shutil.which("bandit") is None:
        return [], "Bandit is not installed. AST rules still ran."

    with tempfile.TemporaryDirectory(prefix="patchproof-") as tmp:
        root = Path(tmp)
        for path, source in py_files:
            dest = root / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(source, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-m", "bandit", "-f", "json", "-q", "-r", str(root)],
            capture_output=True,
            text=True,
            timeout=40,
            check=False,
        )
    if not proc.stdout.strip():
        detail = (proc.stderr or "Bandit returned no JSON.").strip().splitlines()
        return [], detail[-1][:240] if detail else "Bandit returned no JSON."
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return [], "Bandit output was not JSON."

    findings: list[Finding] = []
    for issue in payload.get("results") or []:
        test_id = issue.get("test_id") or ""
        rule_id = BANDIT_MAP.get(test_id)
        if not rule_id:
            continue
        filename = str(issue.get("filename") or "")
        rel = _relative(filename, py_files)
        line = int(issue.get("line_number") or 0)
        if line < 1 or not rel:
            continue
        evidence = f"Bandit {test_id}: {issue.get('issue_text') or 'matched'}."
        findings.append(
            make_finding(
                rule_id=rule_id,
                path=rel,
                line=line,
                end_line=line,
                source=_source_for(rel, py_files),
                evidence=evidence,
                severity=SEVERITY.get(str(issue.get("issue_severity")), "medium"),
                confidence=CONFIDENCE.get(str(issue.get("issue_confidence")), "medium"),
                origin="confirmed",
                bandit_id=test_id,
            )
        )
    return findings, f"Bandit scanned {len(py_files)} file(s)."


def _relative(filename: str, files: list[tuple[str, str]]) -> str | None:
    norm = filename.replace("\\", "/")
    matches = [path for path, _ in files if norm.endswith(path)]
    if not matches:
        return None
    return max(matches, key=len)


def _source_for(path: str, files: list[tuple[str, str]]) -> str:
    for candidate, source in files:
        if candidate == path:
            return source
    return ""


def absorb(primary: list[Finding], extra: list[Finding]) -> list[Finding]:
    """Keep AST findings. Attach Bandit ids when they describe the same rule nearby."""
    for item in extra:
        match = next(
            (
                found
                for found in primary
                if found.rule_id == item.rule_id
                and found.file == item.file
                and abs(found.line - item.line) <= 3
            ),
            None,
        )
        if match is None:
            primary.append(item)
            continue
        if item.bandit_id and (match.bandit_id is None):
            match.bandit_id = item.bandit_id
            if item.bandit_id not in match.evidence:
                match.evidence = f"{match.evidence} Bandit {item.bandit_id} matched this pattern."
    return primary
