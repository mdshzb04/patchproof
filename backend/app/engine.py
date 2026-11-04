"""Review orchestration. Static results do not depend on the AI layer."""

from __future__ import annotations

import ast
import time
import uuid
from datetime import datetime, timezone

from app.bandit_runner import absorb, run_bandit
from app.diff_parser import DiffFile, parse_unified_diff
from app.models import FileSlice, Finding, Review, Stage
from app.rules import RULES, _chain, _finding_id, analyze_ast, dedupe, scan_added_lines

MAX_STORED_CHARS = 200_000


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _retarget(finding: Finding, added: set[int], snapshot: bool) -> bool:
    span = set(range(finding.line, max(finding.end_line, finding.line) + 1))
    introduced = snapshot or bool(span & added)
    if introduced and not snapshot and span & added:
        finding.line = min(span & added)
    finding.in_diff = introduced
    finding.id = _finding_id(finding.rule_id, finding.file, finding.line, finding.evidence)
    finding.evidence_chain = _chain(
        finding.rule_id,
        finding.file,
        finding.line,
        finding.evidence,
        finding.impact,
        finding.recommendation,
        introduced,
    )
    return introduced


def _analyze_file(path: str, source: str, added: set[int]) -> list[Finding]:
    try:
        ast.parse(source)
    except SyntaxError:
        numbered = {i + 1: line for i, line in enumerate(source.splitlines())}
        return dedupe(scan_added_lines(path, numbered, added or set(numbered)))
    return dedupe(analyze_ast(source, path))


def _slice(path: str, content: str, added: set[int], skipped: str | None = None) -> FileSlice:
    if len(content) > MAX_STORED_CHARS:
        content = content[:MAX_STORED_CHARS] + "\n# truncated for storage\n"
    return FileSlice(path=path, added_lines=sorted(added), content=content, skipped_reason=skipped)


def _empty_review(title: str, filename: str, source: str, mode: str) -> Review:
    return Review(
        id="r_" + uuid.uuid4().hex[:12],
        title=title,
        filename=filename,
        source=source,  # type: ignore[arg-type]
        created_at=_now(),
        mode=mode,  # type: ignore[arg-type]
        stages=[],
        files=[],
        findings=[],
        pre_existing=[],
        ai_status="off",
        ai_message="",
        notes=[],
        rules_checked=len(RULES),
    )


def review_diff(text: str, *, title: str = "Diff review", filename: str = "upload.diff", source: str = "paste", enrich: bool = False) -> Review:
    started = time.perf_counter()
    parsed = parse_unified_diff(text)
    parse_ms = int((time.perf_counter() - started) * 1000)
    review = _empty_review(title, filename, source, "diff")
    review.stages.append(Stage(name="Parse diff", ms=parse_ms, status="ok", detail=f"{len(parsed)} file(s)"))
    _fill_from_diff_files(review, parsed, enrich)
    return review


def review_files(files: list[tuple[str, str]], *, title: str, filename: str, source: str, enrich: bool = False) -> Review:
    review = _empty_review(title, filename, source, "snapshot")
    review.notes.append("Full-file upload: every line is in scope. This is not a diff, so nothing is labelled pre-existing.")
    pseudo = []
    for path, content in files:
        added = set(range(1, content.count("\n") + 1)) or {1}
        item = DiffFile(path=path, added_lines=added, new_content=content, saw_hunk=True, gaps=False)
        item.line_text = {i + 1: line for i, line in enumerate(content.splitlines())}
        pseudo.append(item)
    review.stages.append(Stage(name="Parse diff", ms=0, status="skipped", detail="Snapshot upload"))
    _fill_from_diff_files(review, pseudo, enrich, snapshot=True)
    return review


def _fill_from_diff_files(review: Review, parsed: list[DiffFile], enrich: bool, snapshot: bool = False) -> None:
    from app.ai_layer import enrich_findings

    t0 = time.perf_counter()
    bandit_inputs: list[tuple[str, str]] = []
    introduced: list[Finding] = []
    preexisting: list[Finding] = []

    for item in parsed:
        if item.is_deleted:
            review.files.append(_slice(item.path, "", set(), "Deleted file. Not scanned."))
            review.notes.append(f"{item.path} was deleted. PatchProof does not scan removed code.")
            continue
        if not item.path.endswith(".py"):
            review.files.append(_slice(item.path, item.new_content, item.added_lines, "Not Python. Skipped."))
            continue
        content = item.new_content
        if item.gaps:
            findings = scan_added_lines(item.path, item.line_text, item.added_lines)
            review.notes.append(
                f"{item.path} is a partial diff. Rules ran on added lines only, because omitted context was not reconstructed."
            )
        else:
            findings = _analyze_file(item.path, content, item.added_lines)
            bandit_inputs.append((item.path, content))
        scoped_in: list[Finding] = []
        scoped_out: list[Finding] = []
        for finding in findings:
            if _retarget(finding, item.added_lines, snapshot):
                scoped_in.append(finding)
            else:
                scoped_out.append(finding)
        introduced.extend(scoped_in)
        preexisting.extend(scoped_out)
        review.files.append(_slice(item.path, content if not item.gaps else _materialize(item), item.added_lines))

    static_ms = int((time.perf_counter() - t0) * 1000)
    review.stages.append(Stage(name="Static analysis", ms=static_ms, status="ok", detail="AST rules"))

    t1 = time.perf_counter()
    if bandit_inputs:
        extra, detail = run_bandit(bandit_inputs)
        # Split bandit hits with the same changed-line rule, then absorb per side.
        extra_in: list[Finding] = []
        extra_out: list[Finding] = []
        added_by_file = {f.path: set(f.added_lines) for f in review.files}
        for finding in extra:
            added = added_by_file.get(finding.file, set())
            if _retarget(finding, added, snapshot):
                extra_in.append(finding)
            else:
                extra_out.append(finding)
        introduced = absorb(introduced, extra_in)
        preexisting = absorb(preexisting, extra_out)
        for finding in introduced:
            _retarget(finding, added_by_file.get(finding.file, set()), snapshot)
        for finding in preexisting:
            _retarget(finding, added_by_file.get(finding.file, set()), snapshot)
        review.stages.append(Stage(name="Bandit", ms=int((time.perf_counter() - t1) * 1000), status="ok", detail=detail))
    else:
        review.stages.append(Stage(name="Bandit", ms=0, status="skipped", detail="No complete Python file to scan."))

    introduced = dedupe(introduced)
    preexisting = dedupe(preexisting)
    # A line cannot be both introduced and pre-existing.
    intro_keys = {(f.rule_id, f.file, f.line) for f in introduced}
    preexisting = [f for f in preexisting if (f.rule_id, f.file, f.line) not in intro_keys]

    t2 = time.perf_counter()
    if enrich:
        introduced, status, message = enrich_findings(introduced, review.files)
        review.ai_status = status  # type: ignore[assignment]
        review.ai_message = message
        review.stages.append(Stage(name="AI explanation", ms=int((time.perf_counter() - t2) * 1000), status="ok" if status == "ok" else "error", detail=message[:180]))
    else:
        review.ai_status = "off"
        review.ai_message = "AI enrichment was not requested. Findings below are from static analysis only."
        review.stages.append(Stage(name="AI explanation", ms=0, status="skipped", detail=review.ai_message))

    review.findings = _sort(introduced)
    review.pre_existing = _sort(preexisting)


def _materialize(item: DiffFile) -> str:
    if not item.line_text:
        return item.new_content
    last = max(item.line_text)
    return "\n".join(item.line_text.get(i, "") for i in range(1, last + 1)) + "\n"


def _sort(findings: list[Finding]) -> list[Finding]:
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return sorted(findings, key=lambda f: (rank.get(f.severity, 9), f.file, f.line, f.rule_id))


def summarize(review: Review) -> dict:
    open_findings = [f for f in review.findings if not f.resolved]
    return {
        "introduced": len(review.findings),
        "pre_existing": len(review.pre_existing),
        "unresolved": len(open_findings),
        "resolved": len(review.findings) - len(open_findings),
        "critical": sum(1 for f in open_findings if f.severity == "critical"),
        "high": sum(1 for f in open_findings if f.severity == "high"),
        "by_severity": {
            name: sum(1 for f in review.findings if f.severity == name)
            for name in ("critical", "high", "medium", "low")
        },
    }

