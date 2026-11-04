"""Optional explanations. Static findings stay as the analysis recorded them."""

from __future__ import annotations

import json
import os

import httpx

from app.models import AINote, FileSlice, Finding


def configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())


def enrich_findings(findings: list[Finding], files: list[FileSlice]) -> tuple[list[Finding], str, str]:
    if not configured():
        return findings, "unavailable", "No OPENAI_API_KEY. Deterministic findings are unchanged."
    targets = [item for item in findings if item.origin == "confirmed"][:8]
    if not targets:
        return findings, "ok", "No confirmed findings to explain."
    try:
        payload = _complete(_prompt(targets, files))
    except Exception as exc:
        reason = exc.__class__.__name__
        return findings, "unavailable", f"AI enrichment failed ({reason}). Deterministic findings are unchanged."
    notes = _parse(payload)
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    applied = 0
    for finding in findings:
        raw = notes.get(finding.id)
        if not raw:
            continue
        finding.ai = AINote(
            explanation=_clip(raw.get("explanation")),
            why_risky=_clip(raw.get("why_risky")),
            scenario=_clip(raw.get("scenario")),
            recommended_fix=_clip(raw.get("recommended_fix")),
            corrected_code=_clip(raw.get("corrected_code"), 1200),
            model=model,
        )
        applied += 1
    if applied == 0:
        return findings, "unavailable", "AI response did not include explanations. Deterministic findings are unchanged."
    return findings, "ok", f"Explained {applied} confirmed finding(s). Severity and evidence were not modified."


def _clip(value, limit: int = 700) -> str:
    text = str(value or "").strip()
    return text[:limit]


def _prompt(findings: list[Finding], files: list[FileSlice]) -> list[dict]:
    items = []
    by_path = {item.path: item.content for item in files}
    for finding in findings:
        content = by_path.get(finding.file, "")
        lines = content.splitlines()
        start = max(1, finding.line - 3)
        end = min(len(lines), finding.line + 3)
        context = "\n".join(f"{i}: {lines[i - 1]}" for i in range(start, end + 1))
        items.append(
            {
                "id": finding.id,
                "rule_id": finding.rule_id,
                "title": finding.title,
                "severity": finding.severity,
                "file": finding.file,
                "line": finding.line,
                "evidence": finding.evidence,
                "context": context,
            }
        )
    return [
        {
            "role": "system",
            "content": (
                "You explain confirmed static-analysis findings for a code review. "
                "Do not change severity, do not invent CVEs, and do not claim the issue is exploitable "
                "unless the evidence shows caller-controlled input. Return JSON only with the shape "
                '{"items":[{"id":"","explanation":"","why_risky":"","scenario":"","recommended_fix":"","corrected_code":""}]}'
            ),
        },
        {"role": "user", "content": json.dumps({"findings": items})},
    ]


def _complete(messages: list[dict]) -> dict:
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    key = os.environ["OPENAI_API_KEY"].strip()
    response = httpx.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": model,
            "temperature": 0,
            "messages": messages,
            "response_format": {"type": "json_object"},
        },
        timeout=25.0,
    )
    response.raise_for_status()
    body = response.json()
    content = body["choices"][0]["message"]["content"]
    return json.loads(content)


def _parse(payload: dict) -> dict[str, dict]:
    rows = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return {}
    out: dict[str, dict] = {}
    for row in rows:
        if isinstance(row, dict) and row.get("id"):
            out[str(row["id"])] = row
    return out
