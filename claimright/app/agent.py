"""'Ask ClaimRight': an ADK agent that answers a family's questions about THEIR audited claim.

It never calculates money and never guesses: every answer comes from its tools, which read the
audit produced by the rules engine (app/rules/engine.py) and the rule sources.
"""
from __future__ import annotations

import json
import logging
import time
import uuid

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import ToolContext
from google.genai import types

from app import bq, pipeline
from app.gemini import MODEL_EXPLAIN, USAGE_LOG, backend
from app.money import inr
from app.rules.engine import load_rules

log = logging.getLogger("claimright.agent")
APP_NAME = "claimright"


# ---------------- tools ----------------

def _case(tool_context: ToolContext):
    case_id = tool_context.state.get("case_id")
    loaded = pipeline.load_report(case_id) if case_id else None
    if loaded is None:
        return None, None
    return loaded


def get_case_audit(tool_context: ToolContext) -> dict:
    """Get the audit of this family's claim: amounts claimed/approved, how much can be claimed back,
    and every deduction with its verdict (wrong / ask / looks_right), amount, reason and rule IDs.
    Use this for any question about why money was cut, how much can be recovered, or a specific item."""
    report, docs = _case(tool_context)
    if report is None:
        return {"error": "No audited claim is open."}
    return {
        "patient": report.patient_name, "hospital": report.hospital_name, "insurer": report.insurer_name,
        "claim_number": report.claim_number,
        "amount_claimed": inr(report.amount_claimed), "amount_approved": inr(report.amount_approved),
        "total_deducted": inr(report.total_deducted),
        "can_claim_back": inr(report.recoverable), "ask_insurer_about": inr(report.to_clarify),
        "policy": {"room_rent_limit_per_day": docs.policy.room_rent_limit_per_day,
                   "consumables_cover": docs.policy.consumables_cover,
                   "co_pay_percent": docs.policy.co_pay_percent},
        "findings": [{"verdict": f.verdict.value, "title": f.title, "amount": inr(f.amount),
                      "why": f.why, "rule_ids": f.rule_ids_cited} for f in report.findings],
    }


def explain_rule(rule_id: str) -> dict:
    """Get the exact text and official source of a rule cited in the audit, e.g. 'R1', 'R1-ICU', 'R2', 'R6'.
    Use this when the family asks which rule or law says so, or wants the source."""
    rules = {r["id"]: r for r in load_rules()["rules"]}
    r = rules.get(rule_id.strip().upper())
    if r is None:
        return {"error": f"Unknown rule {rule_id}", "known_rules": sorted(rules)}
    if r["status"] == "unverified":
        return {"error": "This rule is not yet verified, so ClaimRight does not rely on it."}
    return {k: r[k] for k in ("id", "title", "text", "source_title", "source_url", "status")}


def get_next_steps(tool_context: ToolContext) -> dict:
    """Get the dated escalation plan for this claim: complaint to the insurer, then Bima Bharosa,
    then the Insurance Ombudsman. Use this when the family asks what to do next, by when, or what if
    the insurer does not reply."""
    report, _ = _case(tool_context)
    if report is None:
        return {"error": "No audited claim is open."}
    if report.recoverable + report.to_clarify <= 0:
        return {"note": "Nothing to dispute: every deduction in this claim looks correct."}
    return {"steps": [{"date": s["date"], "step": s["step"], "detail": s["text"],
                       "source": s["source_title"]} for s in report.escalation]}


async def draft_complaint_letter(language: str, tool_context: ToolContext) -> dict:
    """Prepare the complaint letter to the insurer's Grievance Redressal Officer.
    language must be 'en' (English) or 'hi' (Hindi). Use only when the family asks for the letter."""
    report, _ = _case(tool_context)
    if report is None:
        return {"error": "No audited claim is open."}
    if report.recoverable + report.to_clarify <= 0:
        return {"note": "No letter needed: nothing in this claim looks wrong."}
    lang = "hi" if language.lower().startswith("h") else "en"
    text = await pipeline.draft_letter(report.case_id, lang)
    return {"ready": True, "language": lang, "opening_lines": text[:400],
            "how_to_open": "Tap 'Write my complaint letter' on the report to see, copy or download the full letter."}


async def insurer_track_record(rule_id: str, tool_context: ToolContext) -> dict:
    """Get how often THIS claim's insurer breaks a given rule across all claims ClaimRight has audited,
    compared with all insurers (from BigQuery, via the MCP Toolbox). rule_id e.g. 'R1', 'R1-ICU', 'R2'.
    Use this when the family asks whether the insurer does this often / to other people too, or how
    their insurer compares with others."""
    report, _ = _case(tool_context)
    if report is None:
        return {"error": "No audited claim is open."}
    try:
        row = await bq.toolbox_call("insurer_track_record",
                                    {"insurer": report.insurer_name, "rule_id": rule_id.strip().upper()})
    except Exception as e:  # noqa: BLE001
        log.warning("toolbox call failed: %s", e)
        return {"error": "The insurer track record is not available right now."}
    if isinstance(row, list):
        row = row[0] if row else {}
    if not row.get("num_audits"):
        return {"note": f"ClaimRight has no past audits of {report.insurer_name} for rule {rule_id} yet."}
    return {
        "insurer": report.insurer_name, "rule_id": row.get("rule_id"),
        "claims_audited": row.get("num_audits"), "times_this_rule_was_broken": row.get("wrong_count"),
        "money_wrongly_cut": inr(row.get("total_rupees_wrongly_cut") or 0),
        "this_insurer_wrong_rate": f"{row.get('insurer_wrong_rate_pct')}%",
        "all_insurers_wrong_rate": f"{row.get('all_insurers_wrong_rate_pct')}%",
        "data_note": "Based on ClaimRight's demo dataset (synthetic data), not official statistics.",
    }


# ---------------- agent ----------------

INSTRUCTION = """You are ClaimRight, a friendly assistant that helps an Indian family understand the audit of
THEIR health insurance claim and what to do next.

How to answer:
- Always call get_case_audit before answering anything about this claim. Call explain_rule when asked
  which rule/law/source applies, get_next_steps for what to do next, and draft_complaint_letter only when
  the family asks for the letter. Call insurer_track_record (with the rule ID from the audit) when they ask
  whether their insurer does this often or to others too; then say it is ClaimRight's demo data.
- Use only facts and rupee amounts returned by the tools, copied exactly (e.g. ₹10,500). Never calculate,
  estimate or invent amounts, rules, clause numbers or deadlines. Never add, subtract or combine amounts
  yourself: list each amount separately exactly as the tool gives it.
- Reply in the language the user writes in: Hindi (Devanagari) if they write Hindi or Hinglish, otherwise English.
- Keep answers short: at most 5 short sentences or bullets. Simple words, no jargon.
- Never show internal labels such as "verdict", "wrong", "looks_right", "rule_ids" or field names.
  Mention a rule as e.g. "(rule R1)".
- When something is 'wrong', say they can ask for that money back and name the rule ID. When it is 'ask',
  say they should ask the insurer for a written reason. When it 'looks_right', say so honestly.
- You are not a lawyer. For disputes that need medical or legal judgement, suggest a lawyer or the free
  Insurance Ombudsman. Politely decline questions unrelated to this claim or Indian health insurance claims.
"""

root_agent = Agent(
    name="ask_claimright",
    model=MODEL_EXPLAIN,
    description="Answers a family's questions about their audited health insurance claim.",
    instruction=INSTRUCTION,
    tools=[get_case_audit, explain_rule, get_next_steps, draft_complaint_letter, insurer_track_record],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
        # Vertex occasionally hangs on a call; cut it at 40 s and retry busy (429/5xx) responses.
        http_options=types.HttpOptions(
            timeout=40000,
            retry_options=types.HttpRetryOptions(attempts=3, http_status_codes=[429, 500, 503, 504]),
        ),
    ),
)

_sessions = InMemorySessionService()
_runner = Runner(app_name=APP_NAME, agent=root_agent, session_service=_sessions)


def _log_usage(events_usage: list, seconds: float, tools: list[str]) -> None:
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "backend": backend(), "model": MODEL_EXPLAIN,
           "purpose": "agent_chat", "input_tokens": sum(u[0] for u in events_usage),
           "output_tokens": sum(u[1] for u in events_usage), "thinking_tokens": sum(u[2] for u in events_usage),
           "seconds": round(seconds, 1), "tools": tools}
    log.info("agent %s", row)
    try:
        USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with USAGE_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass


async def chat(case_id: str, message: str, session_id: str | None = None) -> dict:
    """One chat turn. Returns {session_id, reply, tools_used}."""
    user_id = "family"
    if session_id:
        session = await _sessions.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
        if session is None or session.state.get("case_id") != case_id:
            session_id = None
    if not session_id:
        session_id = uuid.uuid4().hex
        await _sessions.create_session(app_name=APP_NAME, user_id=user_id, session_id=session_id,
                                       state={"case_id": case_id})

    t = time.time()
    reply, tools_used, usage = "", [], []
    content = types.Content(role="user", parts=[types.Part(text=message[:1000])])
    for attempt in range(3):  # a timed-out Gemini call raises; try the turn again
        try:
            async for event in _runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
                for call in event.get_function_calls() or []:
                    tools_used.append(call.name)
                u = getattr(event, "usage_metadata", None)
                if u:
                    usage.append((u.prompt_token_count or 0, u.candidates_token_count or 0,
                                  u.thoughts_token_count or 0))
                if event.is_final_response() and event.content and event.content.parts:
                    reply = "".join(p.text or "" for p in event.content.parts).strip()
            if reply:
                break
        except Exception as e:  # noqa: BLE001 - timeouts and transient API errors
            log.warning("agent turn failed (attempt %d): %s", attempt + 1, e)
    if not reply:
        reply = ("Sorry, I couldn't get an answer just now. Please try again in a moment. "
                 "Your audit above is complete and correct.")
    _log_usage(usage, time.time() - t, tools_used)
    return {"session_id": session_id, "reply": reply, "tools_used": tools_used}
