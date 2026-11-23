"""Hospital pre-check (app/precheck.py): exact rupee amounts for every check."""
import pytest

from app.precheck import PrecheckRequest, run_precheck

LIMIT = 5000
DAYS = 5

# Same knee-replacement bill as the seed data in web/hospital.html (room rent is not a line).
KNEE_LINES = [
    {"description": "Surgeon fee - total knee replacement (right)", "category": "procedure", "amount": 75000},
    {"description": "OT package (theatre, anaesthesia, surgical team)", "category": "procedure", "amount": 45000},
    {"description": "Nursing charges", "category": "nursing", "amount": 6000},
    {"description": "Doctor visits (orthopaedics, physician)", "category": "doctor_fees", "amount": 8000},
    {"description": "Pharmacy - medicines", "category": "pharmacy", "amount": 32000},
    {"description": "Diagnostics - X-ray, blood tests, ECG", "category": "diagnostics", "amount": 9500},
    {"description": "Knee implant (prosthesis)", "category": "implants", "amount": 95000},
    {"description": "Physiotherapy sessions", "category": "other", "amount": 3000},
    {"description": "Surgical gloves, drapes, syringes (consumables)", "category": "consumables", "amount": 18000},
]
CONSUMABLES = 8
OT = 1


def policy(**kw):
    p = {"insurer_name": "Demo Suraksha Health Insurance Ltd", "policy_number": "DSH-TEST-1",
         "sum_insured": 500000, "room_rent_limit_per_day": LIMIT, "consumables_cover": False,
         "co_pay_percent": 0, "sub_limits": []}
    p.update(kw)
    return p


def check(rent, lines=None, pol=None, **kw):
    req = PrecheckRequest(policy=pol or policy(), room_category="Room", room_rent_per_day=rent, days=DAYS,
                          lines=lines if lines is not None else KNEE_LINES, **kw)
    res = run_precheck(req)
    return res, {i.id: i for i in res.issues}


def merged_lines():
    lines = [dict(l) for l in KNEE_LINES]
    lines[OT]["amount"] += lines[CONSUMABLES]["amount"]
    del lines[CONSUMABLES]
    return lines


# a. Room rent above the limit (R1 proportionate deduction + R7 excess room rent)
def test_deluxe_room_r1_and_r7():
    res, by_id = check(8000)
    # factor = 1 - 5000/8000 = 0.375; associated = 75000 + 45000 + 6000 + 8000 + 3000 = 137000
    assert by_id["R1"].amount_at_risk == 51375.0
    assert by_id["R1"].severity == "high"
    assert "₹5,000/day" in by_id["R1"].fix and "twin sharing" in by_id["R1"].fix
    assert by_id["R7"].amount_at_risk == 15000.0          # (8000 - 5000) x 5
    assert res.total_at_risk == 84375.0                   # + 18000 consumables
    assert res.display["total_at_risk"] == "₹84,375"


def test_private_room_factor():
    _, by_id = check(6500)
    assert by_id["R1"].amount_at_risk == pytest.approx(137000 * (1 - 5000 / 6500), abs=0.01)  # 31615.38
    assert by_id["R7"].amount_at_risk == 7500.0


def test_room_within_limit_has_no_room_issue():
    res, by_id = check(4500)
    assert "R1" not in by_id and "R7" not in by_id
    assert res.total_at_risk == 18000.0


def test_protected_heads_and_icu_not_in_r1_base():
    lines = KNEE_LINES + [{"description": "ICU stay (1 day)", "category": "icu", "amount": 20000}]
    _, by_id = check(8000, lines)
    assert by_id["R1"].amount_at_risk == 51375.0          # ICU (R1-ICU), pharmacy, implants, tests excluded


def test_no_room_limit_in_policy():
    res, by_id = check(8000, pol=policy(room_rent_limit_per_day=None))
    assert "R1" not in by_id and "R7" not in by_id
    assert res.total_at_risk == 18000.0


def test_no_differential_billing_means_no_proportionate_deduction():
    res, by_id = check(8000, follows_differential_billing=False)
    assert by_id["R1-DB"].severity == "info" and by_id["R1-DB"].amount_at_risk == 0
    assert "R1" not in by_id
    assert res.total_at_risk == 33000.0                   # 15000 excess room rent + 18000 consumables


# b. Items insurers commonly treat as non-payable
def test_consumables_flagged_without_cover():
    _, by_id = check(4500)
    issue = by_id[f"R2-line-{CONSUMABLES}"]
    assert issue.severity == "high" and issue.line_index == CONSUMABLES
    assert issue.amount_at_risk == 18000.0
    assert "procedure/OT package" in issue.fix and "written consent" in issue.fix


def test_consumables_info_with_cover():
    res, by_id = check(4500, pol=policy(consumables_cover=True))
    issue = by_id[f"R2-covered-{CONSUMABLES}"]
    assert issue.severity == "info" and issue.amount_at_risk == 0
    assert "consumables benefit" in issue.detail
    assert res.total_at_risk == 0.0


def test_non_medical_item_flagged_and_not_double_counted():
    lines = KNEE_LINES + [{"description": "Admission kit", "category": "other", "amount": 1500}]
    res, by_id = check(8000, lines)
    assert by_id["R2-line-9"].severity == "medium" and by_id["R2-line-9"].amount_at_risk == 1500.0
    assert by_id["R1"].amount_at_risk == 51375.0          # admission kit not also in the R1 base
    assert res.total_at_risk == 85875.0


def test_demo_flow_merge_into_ot_package_reaches_zero():
    res, _ = check(4500, merged_lines())
    assert res.issues == [] and res.total_at_risk == 0.0
    assert res.display["total_at_risk"] == "₹0"
    res, by_id = check(8000, merged_lines())               # merged amount is now an associated charge
    assert by_id["R1"].amount_at_risk == 58125.0           # 0.375 x 155000


# c. Sub-limits
def test_sub_limit_excess():
    pol = policy(sub_limits=[{"name": "Knee replacement", "limit": 60000}])
    res, by_id = check(4500, pol=pol)
    issue = by_id["R6-sublimit-knee-replacement"]
    assert issue.amount_at_risk == 15000.0                 # 75000 - 60000
    assert res.total_at_risk == 33000.0


def test_sub_limit_not_exceeded():
    pol = policy(sub_limits=[{"name": "Knee replacement", "limit": 100000}])
    _, by_id = check(4500, pol=pol)
    assert not any(k.startswith("R6-sublimit") for k in by_id)


# d. Co-pay
def test_co_pay_info():
    res, by_id = check(4500, pol=policy(co_pay_percent=10))
    issue = by_id["R6-copay"]
    # gross = 4500 x 5 + 291500 = 314000; payable = 314000 - 18000 = 296000; 10% = 29600
    assert issue.severity == "info" and issue.amount_at_risk == 29600.0
    assert res.total_at_risk == 18000.0                    # info is not added to the total


def test_api_endpoint():
    from fastapi.testclient import TestClient
    from app.main import app
    body = {"policy": policy(), "room_category": "Deluxe", "room_rent_per_day": 8000, "days": DAYS,
            "lines": KNEE_LINES}
    r = TestClient(app).post("/api/precheck", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["total_at_risk"] == 84375.0 and data["display"]["total_at_risk"] == "₹84,375"
    assert {"id", "severity", "line_index", "title", "detail", "rule_id", "amount_at_risk", "fix"} <= set(data["issues"][0])
    assert data["issues"][0]["rule_id"] == "R1"
