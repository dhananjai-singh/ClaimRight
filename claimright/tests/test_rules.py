import json
from datetime import date
from pathlib import Path

import pytest

from app.rules.engine import run_audit, load_rules
from app.schemas import ClaimDocs, Verdict

CASES = Path(__file__).resolve().parents[1] / "demo" / "cases"
CASE_IDS = sorted(p.name for p in CASES.iterdir() if (p / "truth.json").exists())


def load(case_id):
    raw = json.loads((CASES / case_id / "truth.json").read_text(encoding="utf-8"))
    docs = ClaimDocs(bill=raw["bill"], settlement=raw["settlement"], policy=raw["policy"])
    return docs, raw["expected"]


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_demo_case_totals(case_id):
    docs, exp = load(case_id)
    report = run_audit(docs, case_id, today=date(2026, 11, 20))
    assert report.recoverable == pytest.approx(exp["recoverable"])
    assert report.to_clarify == pytest.approx(exp["to_clarify"])
    wrong = sorted(f.rule_id for f in report.findings if f.verdict == Verdict.wrong)
    assert wrong == sorted(exp["wrong_rules"])


def test_bill_totals_are_consistent():
    for case_id in CASE_IDS:
        docs, _ = load(case_id)
        b = docs.bill
        assert sum(l.amount for l in b.lines) == pytest.approx(b.gross_total)
        assert b.gross_total - b.discount == pytest.approx(b.net_total)


def test_every_cited_rule_exists():
    known = {r["id"] for r in load_rules()["rules"]}
    for case_id in CASE_IDS:
        docs, _ = load(case_id)
        for f in run_audit(docs, case_id).findings:
            assert set(f.rule_ids_cited) <= known


def test_clean_claim_has_no_wrong_findings():
    docs, _ = load("appendix_bengaluru")
    report = run_audit(docs, "appendix_bengaluru")
    assert all(f.verdict == Verdict.looks_right for f in report.findings)


@pytest.mark.parametrize("category,rule", [
    ("consumables", "R1"), ("pharmacy", "R1"), ("implants", "R1"), ("diagnostics", "R1"), ("icu", "R1-ICU"),
])
def test_protected_heads_never_proportionately_deducted(category, rule):
    # IRDAI circular 151/06/2020 clauses 4 and 7
    docs, _ = load("dengue_delhi")
    docs.settlement.deductions[3].category = category
    report = run_audit(docs, "x")
    finding = report.findings[3]
    assert finding.verdict == Verdict.wrong and finding.rule_id == rule


def test_no_proportionate_deduction_without_differential_billing():
    docs, _ = load("dengue_delhi")
    docs.bill.follows_differential_billing = False
    report = run_audit(docs, "x")
    assert report.findings[1].rule_id == "R1-DB" and report.findings[1].verdict == Verdict.wrong


def test_escalation_dates():
    docs, _ = load("dengue_delhi")
    steps = run_audit(docs, "x", today=date(2026, 11, 20)).escalation
    assert [s["date"] for s in steps] == ["2026-11-20", "2026-12-04", "2026-12-20"]
