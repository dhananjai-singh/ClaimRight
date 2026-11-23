"""ClaimRight web app (FastAPI). Serves the API and the static UI in web/.

Run locally:  .venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8080
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import bq, pipeline
from app.gemini import backend
from app.money import inr
from app.precheck import PrecheckRequest, run_precheck
from app.rules.engine import load_rules

logging.basicConfig(level=logging.INFO)
ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
MAX_UPLOAD = 15 * 1024 * 1024  # 15 MB per document
ALLOWED = {"application/pdf", "image/jpeg", "image/png", "image/webp", "image/heic"}
LIVE_UPLOADS = os.getenv("ALLOW_UPLOADS", "true").lower() == "true"
# Protects the $5 credit on a public URL: live Gemini work allowed per server instance.
MAX_LIVE_AUDITS = int(os.getenv("MAX_LIVE_AUDITS", "40"))
MAX_LETTERS = int(os.getenv("MAX_LETTERS", "40"))
MAX_CHAT = int(os.getenv("MAX_CHAT", "150"))
_used = {"audits": 0, "letters": 0, "chat": 0}


def _spend(kind: str, limit: int) -> None:
    if _used[kind] >= limit:
        raise HTTPException(429, "This demo has reached its daily limit for new checks. The demo cases still work.")
    _used[kind] += 1

app = FastAPI(title="ClaimRight", version="0.1")
# The mobile/web app (built separately) calls this API from another origin. No cookies are used.
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


_bg: set[asyncio.Task] = set()


def _save_to_bigquery(case_id: str, synthetic: bool) -> None:
    """Log a new audit's findings to BigQuery in the background (doesn't slow the response)."""
    loaded = pipeline.load_report(case_id)
    if loaded:
        task = asyncio.create_task(bq.record_audit(*loaded, synthetic=synthetic))
        _bg.add(task)
        task.add_done_callback(_bg.discard)


def _report_json(report) -> dict:
    d = report.model_dump(mode="json")
    d["display"] = {k: inr(getattr(report, k)) for k in
                    ("amount_claimed", "amount_approved", "total_deducted", "recoverable", "to_clarify")}
    for f, raw in zip(report.findings, d["findings"]):
        raw["amount_display"] = inr(f.amount)
    return d


@app.get("/api/health")
def healthz():
    return {"ok": True, "backend": backend()}


@app.get("/api/rules")
def rules():
    data = load_rules()
    return {"rules": [r for r in data["rules"] if r["status"] != "unverified"],
            "escalation": data["escalation"]}


@app.get("/api/demo-cases")
def demo_cases():
    return pipeline.demo_cases()


@app.post("/api/demo/{case_id}")
async def run_demo(case_id: str, fresh: bool = Query(False), offline: bool = Query(False)):
    try:
        if offline:
            report = pipeline.audit_demo_offline(case_id)
        else:
            if fresh:
                _spend("audits", MAX_LIVE_AUDITS)
            report = await pipeline.audit_demo(case_id, fresh=fresh)
            if fresh:
                _save_to_bigquery(case_id, synthetic=True)
    except FileNotFoundError:
        raise HTTPException(404, "Unknown demo case")
    return _report_json(report)


async def _read(upload: UploadFile) -> tuple[bytes, str]:
    mime = (upload.content_type or "").split(";")[0]
    if mime not in ALLOWED:
        raise HTTPException(415, f"{upload.filename}: please upload a PDF or a photo (JPG/PNG)")
    data = await upload.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, f"{upload.filename} is larger than 15 MB")
    return data, mime


@app.post("/api/audit")
async def audit(bill: UploadFile = File(...), settlement: UploadFile = File(...), policy: UploadFile = File(...)):
    if not LIVE_UPLOADS:
        raise HTTPException(403, "Live uploads are switched off on this demo. Try a demo case.")
    files = [await _read(f) for f in (bill, settlement, policy)]
    _spend("audits", MAX_LIVE_AUDITS)
    report = await pipeline.audit_files(*files)
    # Our sample documents name fictional 'Demo ...' insurers; anything else is a real upload.
    _save_to_bigquery(report.case_id, synthetic="demo" in report.insurer_name.lower())
    return _report_json(report)


@app.get("/api/report/{case_id}")
def get_report(case_id: str):
    loaded = pipeline.load_report(case_id)
    if loaded is None:
        raise HTTPException(404, "Report not found")
    report, docs = loaded
    out = _report_json(report)
    out["docs"] = docs.model_dump(mode="json")
    return out


@app.post("/api/letter/{case_id}")
async def letter(case_id: str, lang: str = Query("en", pattern="^(en|hi)$")):
    if pipeline.load_report(case_id) is None:
        raise HTTPException(404, "Run the audit first")
    if not pipeline.letter_cached(case_id, lang):
        _spend("letters", MAX_LETTERS)
    try:
        text = await pipeline.draft_letter(case_id, lang)
    except FileNotFoundError:
        raise HTTPException(404, "Run the audit first")
    return {"case_id": case_id, "lang": lang, "text": text}


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    session_id: str | None = None


@app.post("/api/chat/{case_id}")
async def ask(case_id: str, body: ChatIn):
    """'Ask ClaimRight': ADK agent answering questions about this audited claim."""
    if pipeline.load_report(case_id) is None:
        raise HTTPException(404, "Run the audit first")
    _spend("chat", MAX_CHAT)
    from app.agent import chat  # imported lazily so the app starts fast
    return await chat(case_id, body.message, body.session_id)


@app.post("/api/precheck")
def precheck(body: PrecheckRequest):
    """Hospital pre-check: plain Python, no Gemini call (instant, $0)."""
    return run_precheck(body).model_dump(mode="json")


@app.get("/demo-files/{case_id}/{name}")
def demo_file(case_id: str, name: str):
    if name not in ("bill.pdf", "settlement.pdf", "policy.pdf"):
        raise HTTPException(404)
    path = pipeline.DEMO_DIR / case_id / name
    if not path.resolve().is_relative_to(pipeline.DEMO_DIR.resolve()) or not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="application/pdf")


@app.exception_handler(Exception)
async def unhandled(_, exc: Exception):
    logging.exception("unhandled error")
    return JSONResponse(status_code=500, content={"detail": "Something went wrong reading these documents. Please try again."})


app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
