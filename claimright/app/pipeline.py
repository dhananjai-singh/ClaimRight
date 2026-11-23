"""Audit pipeline: extract (Gemini) -> check (rules engine) -> explain (Gemini) -> save.

Caching keeps the $5 credit safe:
  * extraction + explanations are cached by a hash of the uploaded files
  * demo cases keep their finished report in demo/cases/<id>/cached_report.json
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from google.genai import types
from pydantic import BaseModel

from app.extract import extract_documents
from app.gemini import MODEL_DRAFT, MODEL_DRAFT_FALLBACK, MODEL_EXPLAIN, generate
from app.money import inr
from app.rules.engine import load_rules, run_audit
from app.schemas import AuditReport, ClaimDocs, Verdict

ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "demo" / "cases"
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT / "data"))
CACHE_DIR = DATA_DIR / "cache"
REPORTS_DIR = DATA_DIR / "reports"

PDF = "application/pdf"


# ---------- storage helpers ----------

def _save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def save_report(report: AuditReport, docs: ClaimDocs) -> None:
    _save_json(REPORTS_DIR / f"{report.case_id}.json",
               {"report": report.model_dump(mode="json"), "docs": docs.model_dump(mode="json")})


def load_report(case_id: str) -> tuple[AuditReport, ClaimDocs] | None:
    for path in (REPORTS_DIR / f"{case_id}.json", DEMO_DIR / case_id / "cached_report.json"):
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            return AuditReport.model_validate(raw["report"]), ClaimDocs.model_validate(raw["docs"])
    return None


# ---------- explanations (EN + HI) ----------

class _Expl(BaseModel):
    index: int
    en: str
    hi: str


class _ExplList(BaseModel):
    items: list[_Expl]


EXPLAIN_PROMPT = """You explain health insurance claim deductions to an ordinary Indian family.
For each finding below, write one or two short, warm, plain sentences in English (en) and in simple
everyday Hindi in Devanagari (hi). Keep every rupee amount EXACTLY as given. Do not add new facts,
rules or numbers. For 'wrong' say clearly that this money can be claimed back; for 'ask' say the family
should ask the insurer for a written reason; for 'looks_right' say this cut is correct.

Findings (JSON):
"""


async def explain(report: AuditReport) -> AuditReport:
    items = [{"index": i, "verdict": f.verdict.value, "title": f.title, "amount": inr(f.amount), "why": f.why}
             for i, f in enumerate(report.findings)]
    cfg = types.GenerateContentConfig(response_mime_type="application/json",
                                      response_schema=_ExplList, temperature=0.2,
                                      thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW))
    resp = await generate(MODEL_EXPLAIN, EXPLAIN_PROMPT + json.dumps(items, ensure_ascii=False), cfg, "explain")
    parsed = resp.parsed or _ExplList.model_validate_json(resp.text)
    report.explanations_en = {str(e.index): e.en for e in parsed.items}
    report.explanations_hi = {str(e.index): e.hi for e in parsed.items}
    return report


# ---------- main entry points ----------

async def audit_files(bill: tuple[bytes, str], settlement: tuple[bytes, str], policy: tuple[bytes, str],
                      case_id: str | None = None, with_explanations: bool = True) -> AuditReport:
    h = hashlib.sha256()
    for data, mime in (bill, settlement, policy):
        h.update(mime.encode())
        h.update(hashlib.sha256(data).digest())
    key = h.hexdigest()[:16]
    case_id = case_id or f"c-{key}"

    cache_path = CACHE_DIR / f"{key}.json"
    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        docs = ClaimDocs.model_validate(cached["docs"])
    else:
        docs = await extract_documents(bill, settlement, policy)
        _save_json(cache_path, {"docs": docs.model_dump(mode="json")})

    report = run_audit(docs, case_id)
    if with_explanations:
        cached_expl = None
        if cache_path.exists():
            cached_expl = json.loads(cache_path.read_text(encoding="utf-8")).get("explanations")
        if cached_expl and len(cached_expl.get("en", {})) == len(report.findings):
            report.explanations_en, report.explanations_hi = cached_expl["en"], cached_expl["hi"]
        else:
            report = await explain(report)
            _save_json(cache_path, {"docs": docs.model_dump(mode="json"),
                                    "explanations": {"en": report.explanations_en, "hi": report.explanations_hi}})
    save_report(report, docs)
    return report


def demo_cases() -> list[dict]:
    out = []
    for d in sorted(DEMO_DIR.iterdir()):
        truth = d / "truth.json"
        if truth.exists():
            out.append({"id": d.name, "title": json.loads(truth.read_text(encoding="utf-8"))["title"],
                        "cached": (d / "cached_report.json").exists()})
    return out


async def audit_demo(case_id: str, fresh: bool = False) -> AuditReport:
    case_dir = DEMO_DIR / case_id
    if not (case_dir / "truth.json").exists():
        raise FileNotFoundError(case_id)
    cached = case_dir / "cached_report.json"
    if cached.exists() and not fresh:
        report, docs = load_report(case_id)  # type: ignore[misc]
        report = run_audit(docs, case_id).model_copy(update={
            "explanations_en": report.explanations_en, "explanations_hi": report.explanations_hi})
        save_report(report, docs)
        return report
    files = [((case_dir / f"{n}.pdf").read_bytes(), PDF) for n in ("bill", "settlement", "policy")]
    report = await audit_files(*files, case_id=case_id)
    _, docs = load_report(case_id)  # type: ignore[misc]
    _save_json(cached, {"report": report.model_dump(mode="json"), "docs": docs.model_dump(mode="json")})
    return report


def audit_demo_offline(case_id: str) -> AuditReport:
    """Zero-cost fallback: run the rules engine on the hand-written truth.json (no Gemini)."""
    raw = json.loads((DEMO_DIR / case_id / "truth.json").read_text(encoding="utf-8"))
    docs = ClaimDocs(bill=raw["bill"], settlement=raw["settlement"], policy=raw["policy"])
    report = run_audit(docs, case_id)
    save_report(report, docs)
    return report


# ---------- complaint letter ----------

LETTER_PROMPT = """Write a formal, polite but firm complaint letter from the policyholder to the insurer's
Grievance Redressal Officer about the claim deductions below. Language: {lang}.
Rules:
- Use ONLY the facts, amounts and rule sources given. Never invent clause numbers, laws or amounts.
- List each 'wrong' finding with its amount and the cited rule/source, and ask for it to be paid.
- List each 'ask' finding and request a written reason with the exact policy clause.
- Do not mention 'looks_right' findings.
- State the total amount requested (recoverable) exactly as given.
- Ask for a reply within 14 days and say the policyholder may escalate to Bima Bharosa and the Insurance Ombudsman.
- Cite each rule source once, briefly (its short title and reference); don't paste the same rule text twice.
- Write amounts exactly as given (e.g. ₹1,01,500).
- Leave [Address], [Phone] and [Date] placeholders for the family to fill. Sign as the patient.
- Keep it under 350 words. Plain text only, no markdown.

Case (JSON):
{case}

Rules cited (JSON):
{rules}
"""


def letter_cached(case_id: str, lang: str) -> bool:
    return ((DATA_DIR / "letters" / f"{case_id}.{lang}.txt").exists()
            or (DEMO_DIR / case_id / f"letter.{lang}.txt").exists())


async def draft_letter(case_id: str, lang: str = "en") -> str:
    loaded = load_report(case_id)
    if loaded is None:
        raise FileNotFoundError(case_id)
    report, docs = loaded
    letter_cache = DATA_DIR / "letters" / f"{case_id}.{lang}.txt"
    demo_letter = DEMO_DIR / case_id / f"letter.{lang}.txt"
    for p in (letter_cache, demo_letter):
        if p.exists():
            return p.read_text(encoding="utf-8")

    rules = {r["id"]: r for r in load_rules()["rules"]}
    cited = sorted({rid for f in report.findings if f.verdict != Verdict.looks_right for rid in f.rule_ids_cited})
    case = {
        "patient": docs.bill.patient_name, "hospital": docs.bill.hospital_name,
        "admission": docs.bill.admission_date, "discharge": docs.bill.discharge_date,
        "insurer": report.insurer_name, "claim_number": report.claim_number,
        "policy_number": docs.policy.policy_number,
        "amount_claimed": inr(report.amount_claimed), "amount_approved": inr(report.amount_approved),
        "recoverable": inr(report.recoverable), "to_clarify": inr(report.to_clarify),
        "findings": [{"verdict": f.verdict.value, "title": f.title, "amount": inr(f.amount), "why": f.why,
                      "rules": f.rule_ids_cited}
                     for f in report.findings if f.verdict != Verdict.looks_right],
    }
    rule_info = [{k: rules[r][k] for k in ("id", "title", "text", "source_title")} for r in cited if r in rules]
    prompt = LETTER_PROMPT.format(lang="Hindi (Devanagari)" if lang == "hi" else "English",
                                  case=json.dumps(case, ensure_ascii=False, indent=1),
                                  rules=json.dumps(rule_info, ensure_ascii=False, indent=1))
    cfg = types.GenerateContentConfig(temperature=0.3)
    resp = await generate(MODEL_DRAFT, prompt, cfg, f"letter_{lang}", fallback=MODEL_DRAFT_FALLBACK)
    text = resp.text.strip()
    letter_cache.parent.mkdir(parents=True, exist_ok=True)
    letter_cache.write_text(text, encoding="utf-8")
    if (DEMO_DIR / case_id).exists():
        demo_letter.write_text(text, encoding="utf-8")
    return text
