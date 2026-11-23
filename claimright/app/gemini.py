"""Gemini client, model config, retries and token/cost logging.

Auth comes from env vars read by google-genai / ADK:
  Vertex AI (credits):   GOOGLE_GENAI_USE_VERTEXAI=TRUE, GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION
  AI Studio (free tier): GOOGLE_GENAI_USE_VERTEXAI=FALSE, GOOGLE_API_KEY
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time

import httpx
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_ROOT / ".env")
# Free laptop backup (start_local_demo.ps1 sets CLAIMRIGHT_MODE=free): Gemini through a free AI Studio key,
# no Google Cloud billing needed. .env.free holds GOOGLE_API_KEY and overrides the Vertex settings above.
if os.getenv("CLAIMRIGHT_MODE", "").lower() == "free":
    load_dotenv(_ROOT / ".env.free", override=True)
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"

MODEL_EXTRACT = os.getenv("MODEL_EXTRACT", "gemini-3.8-flash")
MODEL_EXPLAIN = os.getenv("MODEL_EXPLAIN", "gemini-3.8-flash")
# gemini-4-argon returned 429 (no capacity) for this project on 19 Nov; switch via env if it frees up.
MODEL_DRAFT = os.getenv("MODEL_DRAFT", "gemini-3.1-pro-preview")
MODEL_DRAFT_FALLBACK = os.getenv("MODEL_DRAFT_FALLBACK", "gemini-3.8-flash")

TIMEOUT_MS = int(os.getenv("GEMINI_TIMEOUT_MS", "45000"))

log = logging.getLogger("claimright.gemini")
USAGE_LOG = Path(os.getenv("USAGE_LOG", Path(__file__).resolve().parents[1] / "data" / "usage.jsonl"))

_client: genai.Client | None = None


def client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client()
    return _client


def backend() -> str:
    return "vertex" if os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true", "yes") else "ai_studio"


def _log_usage(model: str, purpose: str, resp, seconds: float) -> None:
    u = getattr(resp, "usage_metadata", None)
    row = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "backend": backend(),
        "model": model,
        "purpose": purpose,
        "input_tokens": getattr(u, "prompt_token_count", None),
        "output_tokens": getattr(u, "candidates_token_count", None),
        "thinking_tokens": getattr(u, "thoughts_token_count", None),
        "seconds": round(seconds, 1),
    }
    log.info("gemini %s", row)
    try:
        USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with USAGE_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError:
        pass


async def generate(model: str, contents, config: types.GenerateContentConfig, purpose: str,
                   fallback: str | None = None, attempts: int = 3):
    """generate_content with retry on 429/503 and an optional fallback model."""
    models = [model] + ([fallback] if fallback else [])
    if config.http_options is None:  # a stuck call gets retried instead of hanging the demo
        config = config.model_copy(update={"http_options": types.HttpOptions(timeout=TIMEOUT_MS)})
    last_err: Exception | None = None
    for m in models:
        for i in range(attempts):
            t = time.time()
            try:
                resp = await client().aio.models.generate_content(model=m, contents=contents, config=config)
                _log_usage(m, purpose, resp, time.time() - t)
                return resp
            except errors.APIError as e:
                last_err = e
                if getattr(e, "code", None) in (429, 500, 503, 504):
                    await asyncio.sleep(2 * (i + 1))
                    continue
                # e.g. 404/403: model not available on this backend or tier. Try the fallback model, if any.
                log.warning("gemini %s failed with %s (%s); trying fallback", m, getattr(e, "code", "?"), purpose)
                break
            except (httpx.TimeoutException, asyncio.TimeoutError) as e:
                last_err = e
                log.warning("gemini %s timed out (%s)", m, purpose)
    raise last_err  # type: ignore[misc]


def doc_part(data: bytes, mime: str) -> types.Part:
    return types.Part.from_bytes(data=data, mime_type=mime)
