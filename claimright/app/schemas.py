"""Data shapes for ClaimRight.

Gemini fills Bill / Settlement / Policy from documents (schema-enforced).
The rules engine reads them and produces an AuditReport. All rupee maths
happens in Python, never inside the model.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Category(str, Enum):
    room = "room"
    icu = "icu"
    doctor_fees = "doctor_fees"
    nursing = "nursing"
    pharmacy = "pharmacy"          # medicines
    consumables = "consumables"
    implants = "implants"          # implants and medical devices
    diagnostics = "diagnostics"    # lab tests, scans, X-ray
    procedure = "procedure"        # OT, surgeon, anaesthesia, package
    other = "other"


class ReasonType(str, Enum):
    proportionate = "proportionate"        # "proportionate deduction", "room rent ratio", "PD"
    excess_room_rent = "excess_room_rent"  # room charged above the policy limit
    non_payable = "non_payable"            # "non-medical", "not payable", "NME"
    co_pay = "co_pay"
    sub_limit = "sub_limit"                # "capped as per sub-limit"
    no_reason = "no_reason"                # empty or only "as per policy" with no clause
    other = "other"


# ---------- Extracted documents ----------

class BillLine(BaseModel):
    description: str
    category: Category
    amount: float = Field(description="Rupees, as printed on the bill")


class Bill(BaseModel):
    hospital_name: str
    patient_name: str
    admission_date: str = Field(description="YYYY-MM-DD")
    discharge_date: str = Field(description="YYYY-MM-DD")
    days: int
    room_category: str
    room_rent_per_day: float
    follows_differential_billing: bool = Field(
        True, description="False only if the bill says charges don't depend on room category")
    lines: list[BillLine]
    gross_total: float
    discount: float = 0.0
    net_total: float


class Deduction(BaseModel):
    description: str = Field(description="The item or bill head that was cut")
    category: Category
    amount: float
    reason_text: str = Field(description="Exact reason printed by the insurer, or empty")
    reason_type: ReasonType


class Settlement(BaseModel):
    insurer_name: str
    claim_number: str
    settlement_date: str = Field(description="YYYY-MM-DD")
    amount_claimed: float
    deductions: list[Deduction]
    co_pay_amount: float = 0.0
    amount_approved: float


class SubLimit(BaseModel):
    name: str = Field(description="Procedure or head, e.g. 'cataract', 'knee replacement'")
    limit: float


class Policy(BaseModel):
    insurer_name: str
    policy_number: str
    sum_insured: float
    room_rent_limit_per_day: Optional[float] = Field(
        None, description="Rupees per day; null if no room rent cap")
    consumables_cover: bool = Field(False, description="True if an add-on/benefit covers consumables / non-medical items")
    co_pay_percent: float = Field(0.0, description="0 if the policy has no co-pay")
    sub_limits: list[SubLimit] = Field(default_factory=list)


class ClaimDocs(BaseModel):
    bill: Bill
    settlement: Settlement
    policy: Policy


# ---------- Audit output ----------

class Verdict(str, Enum):
    wrong = "wrong"            # breaks a cited rule: money is recoverable
    ask = "ask"                # needs a written answer / human review
    looks_right = "looks_right"


class Finding(BaseModel):
    rule_id: str
    verdict: Verdict
    title: str
    amount: float = Field(description="Rupees at stake for this finding")
    deduction_index: Optional[int] = None
    why: str
    rule_ids_cited: list[str] = Field(default_factory=list)


class AuditReport(BaseModel):
    case_id: str
    insurer_name: str
    claim_number: str
    patient_name: str
    hospital_name: str
    amount_claimed: float
    amount_approved: float
    total_deducted: float
    recoverable: float = Field(description="Sum of 'wrong' findings")
    to_clarify: float = Field(description="Sum of 'ask' findings")
    findings: list[Finding]
    explanations_en: dict[str, str] = Field(default_factory=dict)
    explanations_hi: dict[str, str] = Field(default_factory=dict)
    escalation: list[dict] = Field(default_factory=list)
    synthetic: bool = True
