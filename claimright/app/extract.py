"""Gemini reads the three documents into strict, schema-enforced JSON.

Gemini only reads and classifies. It does no arithmetic that the audit relies on;
the rules engine recomputes everything.
"""
from __future__ import annotations

import asyncio

from google.genai import types

from app.gemini import MODEL_EXTRACT, doc_part, generate
from app.schemas import Bill, ClaimDocs, Policy, Settlement

COMMON = """You are a careful data-entry assistant for Indian health insurance documents.
Copy values exactly as printed. Amounts are plain numbers in rupees (no commas, no 'Rs').
Dates must be YYYY-MM-DD. Never invent values: if something is not in the document use 0, false or an empty string.
Category meanings: room = room rent/boarding; icu = ICU charges; doctor_fees = consultations/visits;
nursing = nursing charges; pharmacy = medicines, drugs, IV fluids; consumables = gloves, syringes, drapes,
bandages, cannula and similar disposables; implants = implants, stents, prostheses, medical devices;
diagnostics = lab tests, scans, X-ray, ECG; procedure = surgeon, anaesthetist, OT, package charges; other = anything else."""

BILL_PROMPT = COMMON + """
This is a hospital final bill. Extract every line item with its category. 'days' is the length of stay.
follows_differential_billing is false only if the bill says charges are the same for every room category."""

SETTLEMENT_PROMPT = COMMON + """
This is an insurer's claim settlement letter. Extract every deduction row. For each deduction, set category to
the bill head it refers to, copy reason_text exactly, and classify reason_type:
proportionate = proportionate deduction / room rent ratio / 'PD';
excess_room_rent = room rent above eligibility or limit;
non_payable = non-medical, not payable, NME, excluded items;
co_pay = co-payment; sub_limit = capped as per sub-limit or limit;
no_reason = reason empty, '-', or only 'as per policy' without any clause;
other = any other reason."""

POLICY_PROMPT = COMMON + """
This is a health insurance policy schedule/wording. room_rent_limit_per_day is null if there is no room rent limit.
consumables_cover is true only if the policy says it pays for consumables / non-medical items.
co_pay_percent is 0 if there is no co-payment. List only sub-limits the wording actually states."""


def _cfg(schema) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema,
        temperature=0,
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
    )


async def _one(prompt: str, data: bytes, mime: str, schema, purpose: str):
    resp = await generate(MODEL_EXTRACT, [doc_part(data, mime), prompt], _cfg(schema), purpose)
    if resp.parsed is not None:
        return resp.parsed
    return schema.model_validate_json(resp.text)


async def extract_documents(bill: tuple[bytes, str], settlement: tuple[bytes, str],
                            policy: tuple[bytes, str]) -> ClaimDocs:
    b, s, p = await asyncio.gather(
        _one(BILL_PROMPT, *bill, Bill, "extract_bill"),
        _one(SETTLEMENT_PROMPT, *settlement, Settlement, "extract_settlement"),
        _one(POLICY_PROMPT, *policy, Policy, "extract_policy"),
    )
    return ClaimDocs(bill=b, settlement=s, policy=p)
