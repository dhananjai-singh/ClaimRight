"""Hospital pre-check: plain Python, no AI, no Gemini call (instant and free).

The hospital's billing desk sends the policy, the room chosen and the bill lines
*before* the claim goes to the insurer. We list every charge the insurer is likely
to cut, the rupees at risk and the payable way to bill it.

Rules are the same as the family audit (app/rules/engine.py):
  R1      proportionate deduction when the room is above the policy limit; never on
          pharmacy, consumables, implants or diagnostics (PD_PROTECTED)
  R1-ICU  never on ICU charges
  R1-DB   never if the hospital does not bill by room category
  R7      excess room rent = (room rent - limit) x days
  R2      consumables / non-medical items, depending on the policy's consumables benefit
  R6      sub-limits and co-pay only as written in the policy

Notes on the input:
  * `lines` should NOT include the room rent itself; it is computed as
    room_rent_per_day x days. Any extra lines in category "room" are left out of R1.
  * total_at_risk counts only "high" and "medium" issues (things the desk can fix).
    "info" issues (co-pay, covered consumables) are shown but not added up.

ClaimRight never gives clinical advice: it only says how an item will be paid.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.money import inr
from app.rules.engine import NON_MEDICAL_HINTS, PD_PROTECTED, PD_PROTECTED_NAMES, TOLERANCE, load_rules
from app.schemas import BillLine, Category, Policy

Severity = Literal["high", "medium", "info"]

# Heads a proportionate deduction may reach: everything R1 does not protect, minus ICU (R1-ICU)
# and the room itself (room rent is handled as excess room rent, R7).
PD_EXCLUDED = PD_PROTECTED | {Category.icu, Category.room}

CATEGORY_NAMES = {
    Category.doctor_fees: "doctor visits", Category.nursing: "nursing",
    Category.procedure: "surgeon/OT/procedure", Category.other: "other charges",
}


class PrecheckRequest(BaseModel):
    policy: Policy
    room_category: str = Field("", max_length=100)
    room_rent_per_day: float = Field(ge=0)
    days: int = Field(ge=1, le=365)
    lines: list[BillLine] = Field(default_factory=list, max_length=300)
    follows_differential_billing: bool = Field(
        True, description="False if the hospital's tariff does not change with room category (R1-DB)")


class PrecheckIssue(BaseModel):
    id: str
    severity: Severity
    line_index: Optional[int] = None
    title: str
    detail: str
    rule_id: str
    amount_at_risk: float
    fix: str


class PrecheckResult(BaseModel):
    issues: list[PrecheckIssue]
    total_at_risk: float
    display: dict[str, str]


def _r(x: float) -> float:
    return round(float(x), 2)


def _rule(rule_id: str) -> dict:
    rule = next(r for r in load_rules()["rules"] if r["id"] == rule_id)
    assert rule["status"] != "unverified", f"{rule_id} is unverified and must not be shown"
    return rule


def _is_non_medical(line: BillLine) -> bool:
    desc = line.description.lower() + " "
    return line.category == Category.consumables or any(h in desc for h in NON_MEDICAL_HINTS)


def run_precheck(req: PrecheckRequest) -> PrecheckResult:
    p = req.policy
    issues: list[PrecheckIssue] = []
    limit = p.room_rent_limit_per_day
    rent = req.room_rent_per_day
    over_limit = limit is not None and rent > limit + TOLERANCE

    # ---- b. Items billed separately that insurers commonly treat as non-payable (R2) ----
    non_payable_idx: set[int] = set()
    for i, line in enumerate(req.lines):
        if line.amount <= 0 or not _is_non_medical(line):
            continue
        is_consumable = line.category == Category.consumables
        if p.consumables_cover:
            issues.append(PrecheckIssue(
                id=f"R2-covered-{i}", severity="info", line_index=i, rule_id="R2",
                title=f"{line.description}: covered", amount_at_risk=0.0,
                detail="Covered by this policy's consumables benefit; keep the itemised bill.",
                fix="No change needed. Keep the itemised bill with the claim."))
            continue
        non_payable_idx.add(i)
        if is_consumable:
            fix = ("Bill this inside the procedure/OT package charge (it is part of the procedure), "
                   "or get the patient's written consent that they will pay it.")
        else:
            fix = ("Tell the patient upfront that this is usually theirs to pay and take written consent, "
                   "or leave it out if your room or package tariff already includes it.")
        issues.append(PrecheckIssue(
            id=f"R2-line-{i}", severity="high" if is_consumable else "medium", line_index=i, rule_id="R2",
            title=f"{line.description}: likely non-payable",
            detail=(f"Billed as a separate line, this is an item insurers commonly treat as non-payable, "
                    f"and this policy has no consumables benefit. {inr(line.amount)} would be cut."),
            amount_at_risk=_r(line.amount), fix=fix))

    # ---- a. Room above the policy limit (R1 proportionate deduction + R7 excess room rent) ----
    if over_limit:
        room_fix = (f"Choose a room within {inr(limit)}/day (e.g. twin sharing), "
                    f"or tell the patient upfront that they will pay the difference.")
        if not req.follows_differential_billing:
            issues.append(PrecheckIssue(
                id="R1-DB", severity="info", rule_id="R1-DB", title="No proportionate deduction expected",
                amount_at_risk=0.0,
                detail=(f"Room {inr(rent)}/day is above the {inr(limit)}/day limit, but the hospital's tariff does "
                        f"not change with room category, so no proportionate deduction can be applied. "
                        f"{_rule('R1-DB')['text']}"),
                fix="Keep the tariff sheet that shows charges are the same for every room category."))
        else:
            factor = 1 - limit / rent
            base_lines = [(i, l) for i, l in enumerate(req.lines)
                          if l.category not in PD_EXCLUDED and i not in non_payable_idx and l.amount > 0]
            base = sum(l.amount for _, l in base_lines)
            heads = sorted({CATEGORY_NAMES.get(l.category, l.category.value) for _, l in base_lines})
            protected = ", ".join(PD_PROTECTED_NAMES[c].lower() for c in
                                  (Category.pharmacy, Category.consumables, Category.implants, Category.diagnostics))
            if base > TOLERANCE:
                issues.append(PrecheckIssue(
                    id="R1", severity="high", rule_id="R1",
                    title=f"Room above policy limit: proportionate deduction ({factor:.1%})",
                    amount_at_risk=_r(factor * base),
                    detail=(f"{req.room_category or 'Room'} at {inr(rent)}/day is above the policy limit of "
                            f"{inr(limit)}/day. The insurer can cut 1 − {inr(limit)}/{inr(rent)} = {factor:.1%} "
                            f"of the associated charges ({', '.join(heads)}: {inr(base)}). "
                            f"Not affected: {protected} (R1) and ICU charges (R1-ICU). "
                            f"Source: {_rule('R1')['source_title']}."),
                    fix=room_fix))
        excess = (rent - limit) * req.days
        issues.append(PrecheckIssue(
            id="R7", severity="high", rule_id="R7", title="Excess room rent",
            amount_at_risk=_r(excess),
            detail=(f"({inr(rent)} − {inr(limit)}) × {req.days} days = {inr(excess)} of room rent "
                    f"above the policy limit is not payable."),
            fix=room_fix))

    # ---- c. Sub-limits written in the policy (R6) ----
    for s in p.sub_limits:
        name = s.name.strip().lower()
        if not name:
            continue
        matched = [l for l in req.lines if name in l.description.lower()]
        total = sum(l.amount for l in matched)
        if total > s.limit + TOLERANCE:
            over = total - s.limit
            issues.append(PrecheckIssue(
                id=f"R6-sublimit-{'-'.join(name.split())}", severity="high", rule_id="R6",
                title=f"Above the policy's {s.name} sub-limit",
                amount_at_risk=_r(over),
                detail=(f"{s.name} charges total {inr(total)}; the policy caps {s.name} at {inr(s.limit)}, "
                        f"so {inr(over)} would not be paid."),
                fix=(f"Tell the patient upfront that {inr(over)} above the {s.name} limit will be theirs "
                     f"to pay, and take written consent.")))

    total_at_risk = _r(sum(i.amount_at_risk for i in issues if i.severity != "info"))

    # ---- d. Co-pay written in the policy (R6): info only ----
    if p.co_pay_percent > 0:
        gross = rent * req.days + sum(l.amount for l in req.lines)
        payable = max(gross - total_at_risk, 0.0)
        co_pay = payable * p.co_pay_percent / 100
        issues.append(PrecheckIssue(
            id="R6-copay", severity="info", rule_id="R6", title=f"{p.co_pay_percent:g}% co-pay",
            amount_at_risk=_r(co_pay),
            detail=(f"The policy has a {p.co_pay_percent:g}% co-pay. On the payable {inr(payable)}, "
                    f"the patient pays about {inr(co_pay)}."),
            fix="Tell the patient this amount at admission and collect it at discharge."))

    order = {"high": 0, "medium": 1, "info": 2}
    issues.sort(key=lambda i: (order[i.severity], -i.amount_at_risk))
    return PrecheckResult(issues=issues, total_at_risk=total_at_risk,
                          display={"total_at_risk": inr(total_at_risk)})
