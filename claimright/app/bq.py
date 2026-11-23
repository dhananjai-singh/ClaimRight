"""BigQuery side of ClaimRight.

* insurer_track_record(): asks the private MCP Toolbox service (Cloud Run "claimright-toolbox", built with
  Antigravity + Data Agent Kit) how often an insurer gets a rule wrong, across all ClaimRight audits.
* record_audit(): saves every new audit's findings to the BigQuery table claimright.audits, which feeds the
  Toolbox tools and the "ClaimRight Insurer Report Card" agent in Data Studio.

Both are best-effort: if BigQuery or the Toolbox is unreachable the audit and chat still work.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
import shutil
import subprocess
import time

import httpx

from app import gemini as _env  # noqa: F401  (loads .env before the settings below are read)
from app.schemas import AuditReport, ClaimDocs

log = logging.getLogger("claimright.bq")

TOOLBOX_URL = os.getenv("TOOLBOX_URL", "").rstrip("/")
TOOLSET = os.getenv("TOOLBOX_TOOLSET", "claimright")
BQ_PROJECT = os.getenv("BQ_PROJECT", os.getenv("GOOGLE_CLOUD_PROJECT", "claimright-aviti"))
BQ_TABLE = os.getenv("BQ_AUDITS_TABLE", f"{BQ_PROJECT}.claimright.audits")
RECORD_AUDITS = os.getenv("RECORD_AUDITS", "true").lower() == "true"

_token: tuple[str, float] | None = None
_recorded: set[str] = set()


# ---------------- MCP Toolbox (private Cloud Run service) ----------------

def _id_token() -> str:
    """Identity token for the private Toolbox service: the Cloud Run service account in production,
    the developer's gcloud login on a laptop."""
    global _token
    if _token and _token[1] > time.time():
        return _token[0]
    try:
        import google.auth.transport.requests
        import google.oauth2.id_token
        tok = google.oauth2.id_token.fetch_id_token(google.auth.transport.requests.Request(), TOOLBOX_URL)
    except Exception:  # noqa: BLE001 - user credentials can't mint audience tokens; use gcloud
        gcloud = shutil.which("gcloud") or shutil.which("gcloud.cmd")
        if not gcloud:
            raise
        tok = subprocess.run([gcloud, "auth", "print-identity-token"], capture_output=True, text=True,
                             check=True, timeout=30).stdout.strip()
    _token = (tok, time.time() + 45 * 60)
    return tok


async def toolbox_call(tool: str, args: dict) -> dict | list:
    """Call one Toolbox tool over MCP (JSON-RPC tools/call on /mcp/<toolset>)."""
    if not TOOLBOX_URL:
        raise RuntimeError("TOOLBOX_URL is not set")
    token = await asyncio.to_thread(_id_token)
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": args}}
    async with httpx.AsyncClient(timeout=20) as http:
        r = await http.post(f"{TOOLBOX_URL}/mcp/{TOOLSET}", json=body,
                            headers={"Authorization": f"Bearer {token}",
                                     "Accept": "application/json, text/event-stream"})
    r.raise_for_status()
    text = r.text.strip()
    if not text.startswith("{"):  # server-sent events: take the data line
        text = next(line[5:].strip() for line in text.splitlines() if line.startswith("data:"))
    msg = json.loads(text)
    if "error" in msg:
        raise RuntimeError(msg["error"].get("message", "toolbox error"))
    result = msg["result"]
    if result.get("isError"):
        raise RuntimeError(result["content"][0].get("text", "toolbox error"))
    rows = [json.loads(c["text"]) for c in result.get("content", []) if c.get("type") == "text"]
    return rows[0] if len(rows) == 1 else rows


# ---------------- audit log in BigQuery ----------------

def _rows(report: AuditReport, docs: ClaimDocs, synthetic: bool) -> list[dict]:
    city = report.case_id.rsplit("_", 1)[-1].title() if "_" in report.case_id else None
    today = dt.date.today().isoformat()
    rows = []
    for i, f in enumerate(report.findings):
        category = None
        if f.deduction_index is not None and f.deduction_index < len(docs.settlement.deductions):
            category = docs.settlement.deductions[f.deduction_index].category.value
        rows.append({"audit_id": f"{report.case_id}-{i:02d}", "case_id": report.case_id, "audit_date": today,
                     "insurer": report.insurer_name, "city": city, "rule_id": f.rule_id,
                     "verdict": f.verdict.value, "category": category, "amount": float(f.amount),
                     "synthetic": synthetic})
    return rows


def _insert(rows: list[dict]) -> None:
    from google.cloud import bigquery
    errors = bigquery.Client(project=BQ_PROJECT).insert_rows_json(
        BQ_TABLE, rows, row_ids=[r["audit_id"] for r in rows])
    if errors:
        raise RuntimeError(str(errors)[:500])


async def record_audit(report: AuditReport, docs: ClaimDocs, synthetic: bool) -> None:
    """Save this audit's findings to BigQuery once per case (never blocks or breaks the audit)."""
    if not RECORD_AUDITS or report.case_id in _recorded or not report.findings:
        return
    _recorded.add(report.case_id)
    try:
        await asyncio.wait_for(asyncio.to_thread(_insert, _rows(report, docs, synthetic)), timeout=20)
        log.info("bigquery: saved %d findings for %s", len(report.findings), report.case_id)
    except Exception as e:  # noqa: BLE001
        _recorded.discard(report.case_id)
        log.warning("bigquery: could not save %s: %s", report.case_id, e)
