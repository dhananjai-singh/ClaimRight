"""Generate synthetic audit findings CSV for ClaimRight BigQuery analytics.

Standard library only, random seed 42.
All records are synthetic=true and use fictional insurer names only.
"""

import csv
from datetime import date, timedelta
from pathlib import Path
import random


INSURERS = [
    "Demo Suraksha Health Insurance Ltd",
    "Insurer B",
    "Insurer C",
    "Insurer D",
    "Insurer E",
]

CITIES = [
    "Delhi",
    "Mumbai",
    "Pune",
    "Bengaluru",
    "Chennai",
    "Hyderabad",
    "Kolkata",
    "Lucknow",
    "Jaipur",
    "Ahmedabad",
]

RULES = ["R1", "R1-ICU", "R1-DB", "R2", "R3", "R4", "R5", "R6", "R7"]

CATEGORIES = [
    "room",
    "icu",
    "doctor_fees",
    "nursing",
    "pharmacy",
    "consumables",
    "implants",
    "diagnostics",
    "procedure",
    "other",
]

RULE_CATEGORIES = {
    "R1": ["pharmacy", "consumables", "implants", "diagnostics"],
    "R1-ICU": ["icu"],
    "R1-DB": ["doctor_fees", "nursing", "procedure"],
    "R2": ["consumables"],
    "R3": ["procedure", "room", "other"],
    "R4": ["other", "procedure", "nursing", "doctor_fees"],
    "R5": ["other"],
    "R6": ["procedure", "room", "doctor_fees", "implants"],
    "R7": ["room"],
}


def pick_verdict(rng: random.Random, insurer: str, rule_id: str) -> str:
    """Return 'wrong', 'ask', or 'looks_right' based on insurer and rule profile."""
    if rule_id == "R1":
        if insurer == "Demo Suraksha Health Insurance Ltd":
            weights = [0.68, 0.10, 0.22]  # wrong, ask, looks_right
        elif insurer == "Insurer C":
            weights = [0.58, 0.12, 0.30]
        elif insurer == "Insurer B":
            weights = [0.16, 0.12, 0.72]
        elif insurer == "Insurer D":
            weights = [0.12, 0.10, 0.78]
        else:  # Insurer E (cleanest)
            weights = [0.03, 0.05, 0.92]
    else:
        if insurer == "Demo Suraksha Health Insurance Ltd":
            weights = [0.16, 0.14, 0.70]
        elif insurer == "Insurer C":
            weights = [0.14, 0.14, 0.72]
        elif insurer == "Insurer B":
            weights = [0.12, 0.13, 0.75]
        elif insurer == "Insurer D":
            weights = [0.10, 0.12, 0.78]
        else:  # Insurer E (cleanest)
            weights = [0.03, 0.06, 0.91]

    return rng.choices(["wrong", "ask", "looks_right"], weights=weights, k=1)[0]


def pick_rule(rng: random.Random, insurer: str) -> str:
    """Select a rule_id, giving R1 higher appearance for Demo Suraksha and Insurer C."""
    if insurer in ("Demo Suraksha Health Insurance Ltd", "Insurer C"):
        weights = [0.34, 0.07, 0.07, 0.12, 0.06, 0.10, 0.04, 0.10, 0.10]
    else:
        weights = [0.20, 0.08, 0.07, 0.14, 0.07, 0.12, 0.06, 0.13, 0.13]
    return rng.choices(RULES, weights=weights, k=1)[0]


def pick_amount(rng: random.Random, category: str) -> float:
    """Generate a realistic small-claim finding amount (mostly Rs 1,000 to Rs 50,000)."""
    if category in ("implants", "procedure", "icu"):
        low, high = 3500, 48000
    elif category in ("pharmacy", "diagnostics", "room", "doctor_fees"):
        low, high = 1500, 32000
    else:
        low, high = 1000, 18000
    # Triangular distribution skewed toward smaller everyday deductions
    val = rng.triangular(low, high, low + (high - low) * 0.28)
    return float(round(val / 50.0) * 50)


def main() -> None:
    rng = random.Random(42)

    out_path = Path(__file__).resolve().parent.parent / "data" / "synthetic_audits.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    start_date = date(2026, 1, 1)
    end_date = date(2026, 11, 15)
    total_days = (end_date - start_date).days

    num_cases = 500
    insurer_weights = [0.24, 0.19, 0.22, 0.18, 0.17]

    rows = []
    finding_seq = 1

    for case_idx in range(1, num_cases + 1):
        case_id = f"SYN-2026-{case_idx:04d}"
        insurer = rng.choices(INSURERS, weights=insurer_weights, k=1)[0]
        city = rng.choice(CITIES)
        audit_date = (start_date + timedelta(days=rng.randint(0, total_days))).isoformat()

        # 3 to 5 findings per case -> ~2,000 rows across 500 cases
        num_findings = rng.choices([3, 4, 5], weights=[0.25, 0.50, 0.25], k=1)[0]

        for _ in range(num_findings):
            audit_id = f"AUD-{finding_seq:05d}"
            finding_seq += 1
            rule_id = pick_rule(rng, insurer)
            category = rng.choice(RULE_CATEGORIES[rule_id])
            verdict = pick_verdict(rng, insurer, rule_id)
            amount = pick_amount(rng, category)

            rows.append(
                {
                    "audit_id": audit_id,
                    "case_id": case_id,
                    "audit_date": audit_date,
                    "insurer": insurer,
                    "city": city,
                    "rule_id": rule_id,
                    "verdict": verdict,
                    "category": category,
                    "amount": f"{amount:.2f}",
                    "synthetic": "true",
                }
            )

    fieldnames = [
        "audit_id",
        "case_id",
        "audit_date",
        "insurer",
        "city",
        "rule_id",
        "verdict",
        "category",
        "amount",
        "synthetic",
    ]

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows across {num_cases} cases to {out_path}")


if __name__ == "__main__":
    main()
