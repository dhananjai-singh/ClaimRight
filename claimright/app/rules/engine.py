"""ClaimRight rules engine: plain Python, no AI.

Input: ClaimDocs (bill, settlement letter, policy) already extracted.
Output: AuditReport with one finding per deduction plus case-level checks.
Every rupee figure in the report is computed here.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from app.money import inr
from app.schemas import (
    AuditReport, Category, ClaimDocs, Deduction, Finding, ReasonType, Verdict,
)

RULES_PATH = Path(__file__).with_name("irdai_rules.json")
TOLERANCE = 1.0  # rupees; ignore rounding differences

# R1: IRDAI circular 151/06/2020 clause 4: never part of "associate medical expenses"
# (a) pharmacy and consumables, (b) implants and medical devices, (c) diagnostics
PD_PROTECTED = {Category.pharmacy, Category.consumables, Category.implants, Category.diagnostics}
PD_PROTECTED_NAMES = {
    Category.pharmacy: "Medicines (pharmacy)", Category.consumables: "Consumables",
    Category.implants: "Implants and medical devices", Category.diagnostics: "Diagnostic tests",
}

# Items that are commonly non-payable (non-medical). Used only to say
# "looks right", never to say "wrong".
NON_MEDICAL_HINTS = (
    "toiletr", "soap", "toothpaste", "toothbrush", "comb", "diaper", "attendant",
    "visitor", "telephone", "tv ", "television", "laundry", "admission kit",
    "registration", "food", "mineral water", "slipper", "tissue", "baby",
    "certificate", "courier", "photocop", "medical record",
)


def load_rules() -> dict:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def _r(x: float) -> float:
    return round(float(x), 2)


def _bill_total(docs: ClaimDocs, cat: Category) -> float:
    return sum(l.amount for l in docs.bill.lines if l.category == cat)


def _check_deduction(i: int, d: Deduction, docs: ClaimDocs) -> Finding:
    bill, policy = docs.bill, docs.policy
    limit = policy.room_rent_limit_per_day
    rent = bill.room_rent_per_day

    def f(verdict, rule, title, amount, why, cited=None):
        return Finding(rule_id=rule, verdict=verdict, title=title, amount=_r(amount),
                       deduction_index=i, why=why, rule_ids_cited=cited or [rule])

    rt = d.reason_type

    # ---- Proportionate deduction ----
    if rt == ReasonType.proportionate:
        if not bill.follows_differential_billing:
            return f(Verdict.wrong, "R1-DB", f"Proportionate cut on {d.description}", d.amount,
                     "The hospital does not bill differently by room category, so no proportionate deduction is allowed.")
        if d.category in PD_PROTECTED:
            return f(Verdict.wrong, "R1", f"Proportionate cut on {d.description}", d.amount,
                     f"{PD_PROTECTED_NAMES[d.category]} can never be part of a proportionate deduction.")
        if d.category == Category.icu:
            return f(Verdict.wrong, "R1-ICU", f"Proportionate cut on {d.description}", d.amount,
                     "ICU charges cannot be proportionately deducted.")
        if limit is None:
            return f(Verdict.wrong, "R6", f"Proportionate cut on {d.description}", d.amount,
                     "Your policy has no room rent limit, so there is nothing to apply a proportionate deduction for.")
        if rent <= limit + TOLERANCE:
            return f(Verdict.wrong, "R7", f"Proportionate cut on {d.description}", d.amount,
                     f"Room rent {inr(rent)}/day is within your limit of {inr(limit)}/day, so no proportionate deduction applies.")
        ratio = 1 - limit / rent
        expected = _bill_total(docs, d.category) * ratio
        if d.amount > expected + TOLERANCE:
            return f(Verdict.wrong, "R7", f"Proportionate cut on {d.description} is too high", d.amount - expected,
                     f"At most {ratio:.0%} of this head ({inr(expected)}) could be cut; the insurer cut {inr(d.amount)}.")
        return f(Verdict.looks_right, "R7", f"Proportionate cut on {d.description}", d.amount,
                 f"Room cost {inr(rent)}/day vs your {inr(limit)}/day limit, so {ratio:.0%} of this head can be cut. The maths checks out.")

    # ---- Excess room rent ----
    if rt == ReasonType.excess_room_rent:
        if limit is None:
            return f(Verdict.wrong, "R6", "Room rent cut", d.amount,
                     "Your policy has no room rent limit.")
        expected = max(0.0, rent - limit) * bill.days
        if d.amount > expected + TOLERANCE:
            return f(Verdict.wrong, "R7", "Excess room rent cut is too high", d.amount - expected,
                     f"({inr(rent)} − {inr(limit)}) × {bill.days} days = {inr(expected)}, but {inr(d.amount)} was cut.")
        return f(Verdict.looks_right, "R7", "Excess room rent", d.amount,
                 f"({inr(rent)} − {inr(limit)}) × {bill.days} days = {inr(expected)}. Correct as per your policy.")

    # ---- Non-payable ----
    if rt == ReasonType.non_payable:
        if d.category == Category.consumables and policy.consumables_cover:
            return f(Verdict.wrong, "R2", f"{d.description} cut as non-payable", d.amount,
                     "Your policy has a consumables benefit, so this should be paid.")
        if d.category in (Category.pharmacy, Category.implants, Category.diagnostics,
                          Category.procedure, Category.icu, Category.doctor_fees):
            return f(Verdict.ask, "R4", f"Medical item {d.description} cut as non-payable", d.amount,
                     "This is a medical cost, not a non-medical item. Ask the insurer for the exact policy clause.")
        if any(h in d.description.lower() for h in NON_MEDICAL_HINTS) or d.category == Category.consumables:
            return f(Verdict.looks_right, "R2", f"{d.description} (non-medical)", d.amount,
                     "Commonly excluded non-medical item, and your policy has no consumables benefit.")
        return f(Verdict.ask, "R4", f"{d.description} cut as non-payable", d.amount,
                 "Not clearly a non-medical item. Ask the insurer for the exact clause.")

    # ---- Sub-limit ----
    if rt == ReasonType.sub_limit:
        desc = d.description.lower()
        match = next((s for s in policy.sub_limits
                      if s.name.lower() in desc or desc in s.name.lower()), None)
        if match is None:
            return f(Verdict.wrong, "R6", f"Sub-limit applied on {d.description}", d.amount,
                     "Your policy wording has no sub-limit for this.")
        return f(Verdict.looks_right, "R6", f"Sub-limit on {d.description}", d.amount,
                 f"Your policy caps {match.name} at {inr(match.limit)}.")

    # ---- Co-pay listed as a deduction line ----
    if rt == ReasonType.co_pay:
        if policy.co_pay_percent <= 0:
            return f(Verdict.wrong, "R6", "Co-pay deducted", d.amount,
                     "Your policy has no co-pay.")
        return f(Verdict.looks_right, "R6", "Co-pay", d.amount,
                 f"Your policy has a {policy.co_pay_percent:g}% co-pay.")

    # ---- No reason / other ----
    if rt == ReasonType.no_reason:
        return f(Verdict.ask, "R4", f"{d.description} cut with no reason", d.amount,
                 "No reason was given. The insurer must explain this deduction in writing.")
    return f(Verdict.ask, "R4", f"{d.description} cut", d.amount,
             f"Reason given: “{d.reason_text}”. Ask the insurer for the exact policy clause.")


def _check_co_pay(docs: ClaimDocs) -> Finding | None:
    s, p = docs.settlement, docs.policy
    if s.co_pay_amount <= TOLERANCE:
        return None
    if p.co_pay_percent <= 0:
        return Finding(rule_id="R6", verdict=Verdict.wrong, title="Co-pay applied", amount=_r(s.co_pay_amount),
                       why="Your policy has no co-pay, but the insurer applied one.")
    admissible = s.amount_claimed - sum(d.amount for d in s.deductions)
    expected = admissible * p.co_pay_percent / 100
    if s.co_pay_amount > expected + TOLERANCE:
        return Finding(rule_id="R6", verdict=Verdict.wrong, title="Co-pay is too high",
                       amount=_r(s.co_pay_amount - expected),
                       why=f"{p.co_pay_percent:g}% of the admissible {inr(admissible)} is {inr(expected)}, but {inr(s.co_pay_amount)} was taken.")
    return Finding(rule_id="R6", verdict=Verdict.looks_right, title="Co-pay", amount=_r(s.co_pay_amount),
                   why=f"{p.co_pay_percent:g}% co-pay as per your policy.")


def _check_discount(docs: ClaimDocs, total_deducted: float) -> Finding | None:
    b = docs.bill
    if b.discount <= TOLERANCE or b.gross_total <= 0:
        return None
    share = b.discount * total_deducted / b.gross_total
    if share <= TOLERANCE:
        return None
    return Finding(rule_id="R3", verdict=Verdict.ask, title="Hospital discount on the cut portion",
                   amount=_r(share),
                   why=(f"The hospital gave a {inr(b.discount)} discount on a {inr(b.gross_total)} bill. "
                        f"Your proportional share on the {inr(total_deducted)} that was cut is about {inr(share)}. "
                        "Ask the insurer to show the discount was passed on to you."))


def _check_arithmetic(docs: ClaimDocs) -> Finding:
    s = docs.settlement
    expected = s.amount_claimed - sum(d.amount for d in s.deductions) - s.co_pay_amount
    gap = expected - s.amount_approved
    if gap > TOLERANCE:
        return Finding(rule_id="R5", verdict=Verdict.wrong, title="Settlement doesn't add up", amount=_r(gap),
                       why=(f"{inr(s.amount_claimed)} claimed − {inr(sum(d.amount for d in s.deductions))} deductions "
                            f"− {inr(s.co_pay_amount)} co-pay = {inr(expected)}, but only {inr(s.amount_approved)} was approved."))
    return Finding(rule_id="R5", verdict=Verdict.looks_right, title="Settlement adds up", amount=0.0,
                   why=f"Claimed − deductions − co-pay = {inr(s.amount_approved)}, matching the approved amount.")


def escalation_plan(settlement_date: str, today: date | None = None) -> list[dict]:
    """Dated escalation steps. Starts from today (or the settlement date, if later)."""
    rules = load_rules()["escalation"]
    start = max(date.fromisoformat(settlement_date), today or date.today())
    out, d = [], start
    for step in rules:
        d = d + timedelta(days=step["days_after_previous"])
        out.append({**step, "date": d.isoformat()})
    return out


def run_audit(docs: ClaimDocs, case_id: str, today: date | None = None) -> AuditReport:
    s = docs.settlement
    findings = [_check_deduction(i, d, docs) for i, d in enumerate(s.deductions)]
    total_deducted = s.amount_claimed - s.amount_approved
    for extra in (_check_co_pay(docs), _check_arithmetic(docs), _check_discount(docs, total_deducted)):
        if extra is not None:
            findings.append(extra)

    recoverable = sum(f.amount for f in findings if f.verdict == Verdict.wrong)
    to_clarify = sum(f.amount for f in findings if f.verdict == Verdict.ask)
    recoverable = min(recoverable, max(total_deducted, 0.0))

    return AuditReport(
        case_id=case_id,
        insurer_name=s.insurer_name,
        claim_number=s.claim_number,
        patient_name=docs.bill.patient_name,
        hospital_name=docs.bill.hospital_name,
        amount_claimed=_r(s.amount_claimed),
        amount_approved=_r(s.amount_approved),
        total_deducted=_r(total_deducted),
        recoverable=_r(recoverable),
        to_clarify=_r(to_clarify),
        findings=findings,
        escalation=escalation_plan(s.settlement_date, today),
    )
