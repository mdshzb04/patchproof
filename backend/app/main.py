"""PatchProof HTTP API."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.diff_parser import DiffParseError
from app.engine import review_diff, review_files, summarize
from app.evaluation import score_cases
from app.ingest import UploadError, classify, reject_oversized_text
from app.samples import demo_diff, safe_fix_diff
from app.store import get_review, list_reviews, save_review, set_resolved, stats
from app.ai_layer import configured


class TextReview(BaseModel):
    text: str
    filename: str = "paste.diff"
    title: str = "Pasted diff"
    enrich: bool = False


class ResolveBody(BaseModel):
    resolved: bool = True


def load_env_file() -> None:
    path = Path(__file__).resolve().parents[1] / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_env_file()


def seed() -> None:
    if os.environ.get("PATCHPROOF_NO_SEED") == "1":
        return
    if list_reviews():
        return
    risky = review_diff(
        demo_diff(),
        title="Sample: backup job patch",
        filename="demo_pr.diff",
        source="sample",
        enrich=False,
    )
    fixed = review_diff(
        safe_fix_diff(),
        title="Sample: backup job fixed",
        filename="safe_fix.diff",
        source="sample",
        enrich=False,
    )
    save_review(risky)
    save_review(fixed)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    seed()
    yield


app = FastAPI(title="PatchProof", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "ai_configured": configured(), "product": "PatchProof"}


@app.get("/api/stats")
def review_stats() -> dict:
    return stats()


@app.get("/api/reviews")
def reviews() -> list[dict]:
    return [review.model_dump() for review in list_reviews()]


@app.get("/api/reviews/{review_id}")
def review_detail(review_id: str) -> dict:
    review = get_review(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found.")
    payload = review.model_dump()
    payload["summary"] = summarize(review)
    return payload


@app.post("/api/reviews/{review_id}/findings/{finding_id}/resolve")
def resolve(review_id: str, finding_id: str, body: ResolveBody) -> dict:
    review = set_resolved(review_id, finding_id, body.resolved)
    if review is None:
        raise HTTPException(status_code=404, detail="Finding not found.")
    payload = review.model_dump()
    payload["summary"] = summarize(review)
    return payload


@app.get("/api/examples/demo")
def example_demo() -> dict:
    return {"filename": "demo_pr.diff", "text": demo_diff()}


@app.get("/api/examples/safe-fix")
def example_fix() -> dict:
    return {"filename": "safe_fix.diff", "text": safe_fix_diff()}


@app.post("/api/reviews/text")
def review_text(body: TextReview) -> dict:
    try:
        reject_oversized_text(body.text)
        review = review_diff(body.text, title=body.title, filename=body.filename, source="paste", enrich=body.enrich)
    except DiffParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    save_review(review)
    payload = review.model_dump()
    payload["summary"] = summarize(review)
    return payload


@app.post("/api/reviews")
async def review_upload(
    file: UploadFile = File(...),
    enrich: bool = Form(False),
    title: str = Form(""),
) -> dict:
    data = await file.read()
    filename = file.filename or "upload.txt"
    try:
        kind, payload = classify(filename, data)
        label = title.strip() or filename
        if kind == "diff":
            review = review_diff(str(payload), title=label, filename=filename, source="upload", enrich=enrich)
        else:
            review = review_files(
                list(payload),  # type: ignore[arg-type]
                title=label,
                filename=filename,
                source="zip" if kind == "zip" else "files",
                enrich=enrich,
            )
    except (UploadError, DiffParseError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    save_review(review)
    body = review.model_dump()
    body["summary"] = summarize(review)
    return body


@app.get("/api/evaluation")
def evaluation() -> dict:
    return score_cases()
