from typing import Literal

from pydantic import BaseModel, Field


Severity = Literal["critical", "high", "medium", "low"]
Confidence = Literal["high", "medium", "low"]
Origin = Literal["confirmed", "needs_investigation"]
Category = Literal["security", "reliability"]


class EvidenceStep(BaseModel):
    step: Literal["changed_line", "rule", "evidence", "risk", "fix"]
    label: str
    detail: str


class AINote(BaseModel):
    explanation: str
    why_risky: str
    scenario: str
    recommended_fix: str
    corrected_code: str
    model: str


class Finding(BaseModel):
    id: str
    rule_id: str
    title: str
    severity: Severity
    confidence: Confidence
    category: Category
    file: str
    line: int
    end_line: int
    snippet: str
    evidence: str
    impact: str
    recommendation: str
    fix_example: str
    origin: Origin
    in_diff: bool = True
    resolved: bool = False
    bandit_id: str | None = None
    evidence_chain: list[EvidenceStep] = Field(default_factory=list)
    ai: AINote | None = None


class FileSlice(BaseModel):
    path: str
    added_lines: list[int]
    content: str
    skipped_reason: str | None = None


class Stage(BaseModel):
    name: str
    ms: int
    status: Literal["ok", "skipped", "error"]
    detail: str = ""


class Review(BaseModel):
    id: str
    title: str
    filename: str
    source: Literal["upload", "paste", "sample", "zip", "files"]
    created_at: str
    mode: Literal["diff", "snapshot"]
    stages: list[Stage]
    files: list[FileSlice]
    findings: list[Finding]
    pre_existing: list[Finding]
    ai_status: Literal["off", "ok", "unavailable"]
    ai_message: str
    notes: list[str] = Field(default_factory=list)
    rules_checked: int = 10
