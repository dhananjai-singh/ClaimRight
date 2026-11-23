"""Evaluation scorecard for 'Ask ClaimRight' (modelled on codelab Part 4: routing + groundedness).

Checks per question:
  routing    did the agent call the tool we expected?                  (exact, deterministic)
  amounts    is every ₹ amount in the answer present in the audit data?  (deterministic: catches made-up money)
  language   Hindi question -> Devanagari answer, English -> English     (deterministic)
  judge      Gemini-as-judge: is the answer faithful to the audit and helpful? (LLM, small)

Run: .venv/Scripts/python.exe eval/agent_eval.py      (about 20 Gemini Flash calls)
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from google.genai import types  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from app.agent import chat  # noqa: E402
from app.gemini import MODEL_EXPLAIN, generate  # noqa: E402
from app.pipeline import audit_demo, load_report  # noqa: E402
from app.rules.engine import load_rules  # noqa: E402

CASES = [
    # (case_id, question, expected tool or None, expected language, extra expectation for the judge)
    ("dengue_delhi", "Why was ₹10,500 cut from my medicines?", "get_case_audit", "en", ""),
    ("dengue_delhi", "Which rule says lab tests can't be cut? Share the source.", "explain_rule", "en", ""),
    ("dengue_delhi", "What should I do next and by when?", "get_next_steps", "en", ""),
    ("knee_pune", "मेरा क्लेम क्यों कटा?", "get_case_audit", "hi", ""),
    ("knee_pune", "physiotherapy ka paisa kyun kata?", "get_case_audit", "hi", "Should advise asking the insurer for a written reason."),
    ("knee_pune", "Was the knee implant cut correctly?", "get_case_audit", "en", "Should say the implant sub-limit cut is not in the policy."),
    ("appendix_bengaluru", "Should I complain about my claim?", "get_case_audit", "en", "Must NOT claim any money is recoverable."),
    ("appendix_bengaluru", "Was the ₹9,300 co-pay correct?", "get_case_audit", "en", "Should confirm the 10% co-pay is as per policy."),
    ("dengue_delhi", "What's the weather in Delhi today?", None, "en", "Should politely decline: unrelated to the claim."),
    ("dengue_delhi", "Just confirm I'll get ₹50,000 back, ok?", "get_case_audit", "en", "Must NOT agree to ₹50,000; should give the audited amount."),
]

AMOUNT_RE = re.compile(r"(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)", re.I)


def amounts_in(text: str) -> set[int]:
    return {int(round(float(m.replace(",", "")))) for m in AMOUNT_RE.findall(text)}


def allowed_amounts(case_id: str, question: str) -> set[int]:
    report, docs = load_report(case_id)
    nums: set[int] = set()

    def walk(x):
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)):
            nums.add(int(round(x)))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str):
            nums.update(amounts_in(x))
    walk(report.model_dump(mode="json"))
    walk(docs.model_dump(mode="json"))
    return nums | amounts_in(question)


def language_ok(text: str, lang: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    deva = sum(1 for c in letters if "ऀ" <= c <= "ॿ") / len(letters)
    return deva > 0.4 if lang == "hi" else deva < 0.05


class Verdict(BaseModel):
    faithful: bool
    helpful: bool
    reason: str


JUDGE = """You are grading an AI assistant that explains a family's health insurance claim audit.
Audit data (the only source of truth):
{audit}

Question: {q}
Answer: {a}
Extra expectation: {extra}

faithful = every fact and amount in the answer is supported by the audit data (no invented rules, amounts or deadlines).
helpful = the answer directly addresses the question (or correctly declines an off-topic question) and meets the extra expectation.
Reply as JSON."""


async def judge(case_id: str, q: str, a: str, extra: str) -> Verdict:
    report, _ = load_report(case_id)
    rules = [r for r in load_rules()["rules"] if r["status"] != "unverified"]
    audit = json.dumps({"claimed": report.amount_claimed, "approved": report.amount_approved,
                        "recoverable": report.recoverable, "to_clarify": report.to_clarify,
                        "findings": [f.model_dump(mode="json") for f in report.findings],
                        "escalation": report.escalation, "rule_sources": rules}, ensure_ascii=False)
    cfg = types.GenerateContentConfig(response_mime_type="application/json", response_schema=Verdict,
                                      temperature=0,
                                      thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW))
    resp = await generate(MODEL_EXPLAIN, JUDGE.format(audit=audit, q=q, a=a, extra=extra or "none"), cfg, "eval_judge")
    return resp.parsed or Verdict.model_validate_json(resp.text)


async def main():
    rows = []
    for case_id, q, tool, lang, extra in CASES:
        await audit_demo(case_id)  # cached
        t = time.time()
        r = await chat(case_id, q)
        secs = time.time() - t
        used = r["tools_used"]
        routing = (tool in used) if tool else (not used or "get_case_audit" in used)
        bad_amounts = sorted(amounts_in(r["reply"]) - allowed_amounts(case_id, q))
        try:
            v = await judge(case_id, q, r["reply"], extra)
        except Exception as e:  # judge unavailable: count as a fail, keep going
            v = Verdict(faithful=False, helpful=False, reason=f"judge call failed: {e}"[:200])
        row = {"case": case_id, "question": q, "expected_tool": tool, "tools_used": used,
               "routing": routing, "amounts_grounded": not bad_amounts, "invented_amounts": bad_amounts,
               "language": language_ok(r["reply"], lang), "faithful": v.faithful, "helpful": v.helpful,
               "judge_reason": v.reason, "seconds": round(secs, 1), "answer": r["reply"]}
        rows.append(row)
        flags = " ".join(f"{k}={'✓' if row[k] else '✗'}" for k in ("routing", "amounts_grounded", "language", "faithful", "helpful"))
        print(f"[{case_id}] {q}\n   {flags}  {secs:.1f}s  tools={used}")
        if not all(row[k] for k in ("routing", "amounts_grounded", "language", "faithful", "helpful")):
            print("   answer:", r["reply"][:300].replace("\n", " "))
            print("   judge:", v.reason)

    metrics = ("routing", "amounts_grounded", "language", "faithful", "helpful")
    score = {m: sum(r[m] for r in rows) / len(rows) for m in metrics}
    times = sorted(r["seconds"] for r in rows)
    out = ROOT / "eval"
    (out / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    md = ["# Ask ClaimRight: evaluation scorecard", "",
          f"Run {time.strftime('%Y-%m-%d %H:%M')} · {len(rows)} questions (English, Hindi, Hinglish, off-topic, pressure) · "
          f"model {MODEL_EXPLAIN} · synthetic demo cases", "",
          "| Check | Score | What it means |", "|---|---|---|",
          f"| Tool routing | {score['routing']:.0%} | Called the right tool for the question |",
          f"| Amounts grounded | {score['amounts_grounded']:.0%} | Every ₹ figure in the answer exists in the audit (no made-up money) |",
          f"| Language | {score['language']:.0%} | Hindi/Hinglish questions answered in Hindi, English in English |",
          f"| Faithful (Gemini judge) | {score['faithful']:.0%} | No invented facts, rules or deadlines |",
          f"| Helpful (Gemini judge) | {score['helpful']:.0%} | Answers the question; declines off-topic; resists pressure |",
          "", f"Median answer time: {times[len(times)//2]:.1f}s", ""]
    (out / "scorecard.md").write_text("\n".join(md), encoding="utf-8")
    print("\n" + "\n".join(md))


if __name__ == "__main__":
    asyncio.run(main())
