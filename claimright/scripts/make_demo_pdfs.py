"""Render the synthetic demo cases (demo/cases/*/truth.json) into realistic PDFs:
bill.pdf, settlement.pdf and policy.pdf. Every page is stamped SYNTHETIC DEMO.

Run: .venv/Scripts/python.exe scripts/make_demo_pdfs.py
"""
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

CASES = Path(__file__).resolve().parents[1] / "demo" / "cases"
styles = getSampleStyleSheet()
H1, H2, P = styles["Title"], styles["Heading3"], styles["BodyText"]


def rs(x):
    return f"Rs {x:,.2f}"


def stamp(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica-Bold", 46)
    canvas.setFillColor(colors.Color(0.85, 0.1, 0.1, alpha=0.12))
    canvas.translate(A4[0] / 2, A4[1] / 2)
    canvas.rotate(35)
    canvas.drawCentredString(0, 0, "SYNTHETIC DEMO")
    canvas.restoreState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.grey)
    canvas.drawString(15 * mm, 10 * mm, "Fictional document created for the ClaimRight demo. Not a real hospital, insurer or patient.")


def table(rows, widths, header=True):
    t = Table(rows, colWidths=widths)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef7")),
                  ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    t.setStyle(TableStyle(style))
    return t


def build(path, story):
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                      topMargin=15 * mm, bottomMargin=18 * mm).build(story, onFirstPage=stamp, onLaterPages=stamp)


def bill_pdf(case, out):
    b = case["bill"]
    s = case["settlement"]
    story = [
        Paragraph(b["hospital_name"], H1),
        Paragraph("FINAL IN-PATIENT BILL", H2),
        table([
            ["Patient", b["patient_name"], "Bill no.", f"IP/{s['claim_number'][-6:]}"],
            ["Admitted", b["admission_date"], "Discharged", b["discharge_date"]],
            ["Room category", b["room_category"], "Room tariff / day", rs(b["room_rent_per_day"])],
            ["Payer", s["insurer_name"], "Length of stay", f"{b['days']} days"],
        ], [30 * mm, 60 * mm, 35 * mm, 55 * mm], header=False),
        Spacer(1, 8),
    ]
    rows = [["#", "Particulars", "Amount"]]
    rows += [[str(i + 1), l["description"], rs(l["amount"])] for i, l in enumerate(b["lines"])]
    rows += [["", "Gross total", rs(b["gross_total"])]]
    if b["discount"]:
        rows += [["", "Less: hospital discount (network tariff)", "- " + rs(b["discount"])]]
    rows += [["", "NET BILL AMOUNT", rs(b["net_total"])]]
    story += [table(rows, [10 * mm, 130 * mm, 40 * mm]), Spacer(1, 10)]
    note = ("Charges for doctor visits, nursing and procedures at this hospital vary by room category."
            if b["follows_differential_billing"] else
            "This hospital charges the same tariff for all services irrespective of room category.")
    story += [Paragraph(note, P), Spacer(1, 18), Paragraph("Authorised signatory, Billing Department", P)]
    build(out, story)


def settlement_pdf(case, out):
    s, b, p = case["settlement"], case["bill"], case["policy"]
    story = [
        Paragraph(s["insurer_name"], H1),
        Paragraph("CLAIM SETTLEMENT LETTER", H2),
        Paragraph(f"Date: {s['settlement_date']}", P),
        Paragraph(f"To: {b['patient_name']}", P),
        Spacer(1, 6),
        Paragraph(f"Sub: Settlement of claim no. {s['claim_number']} under policy no. {p['policy_number']}", P),
        Spacer(1, 6),
        Paragraph(f"Dear {b['patient_name']}, we have processed your claim for hospitalisation at "
                  f"{b['hospital_name']} from {b['admission_date']} to {b['discharge_date']}. "
                  "The details of the amount approved are given below.", P),
        Spacer(1, 8),
    ]
    rows = [["#", "Bill head", "Amount deducted", "Reason for deduction"]]
    for i, d in enumerate(s["deductions"]):
        rows.append([str(i + 1), Paragraph(d["description"], P), rs(d["amount"]),
                     Paragraph(d["reason_text"] or "-", P)])
    t = table(rows, [8 * mm, 62 * mm, 32 * mm, 78 * mm])
    t.setStyle(TableStyle([("ALIGN", (2, 0), (2, -1), "RIGHT"), ("ALIGN", (3, 0), (3, -1), "LEFT")]))
    story += [t, Spacer(1, 8)]
    total_ded = sum(d["amount"] for d in s["deductions"])
    summary = [
        ["Amount claimed", rs(s["amount_claimed"])],
        ["Total deductions", rs(total_ded)],
        ["Co-payment", rs(s["co_pay_amount"])],
        ["AMOUNT APPROVED", rs(s["amount_approved"])],
    ]
    story += [table(summary, [80 * mm, 50 * mm], header=False), Spacer(1, 10),
              Paragraph("The approved amount will be paid to the hospital / credited to your registered account. "
                        "If you are not satisfied, you may write to our Grievance Redressal Officer.", P),
              Spacer(1, 14), Paragraph("Claims Department", P)]
    build(out, story)


def policy_pdf(case, out):
    p = case["policy"]
    b = case["bill"]
    clauses = [
        ("1. Room rent", (f"Room rent, boarding and nursing charges are payable up to Rs {p['room_rent_limit_per_day']:,.0f} per day. "
                          "If the insured occupies a room above this limit, associated medical expenses shall be paid in the "
                          "proportion that the eligible room rent bears to the actual room rent. Associated medical expenses "
                          "exclude the cost of pharmacy, implants and medical devices, and diagnostics.")
         if p["room_rent_limit_per_day"] else "There is no limit on room rent."),
        ("2. Consumables benefit",
         "The Company will pay for consumables and non-medical items used during hospitalisation (such as gloves, "
         "drapes, bandages and similar items) that are otherwise excluded."
         if p["consumables_cover"] else
         "Non-medical items and consumables listed as excluded under the IRDAI list of non-medical items are not payable."),
        ("3. Co-payment",
         f"Each admissible claim is subject to a co-payment of {p['co_pay_percent']:g}% of the admissible amount."
         if p["co_pay_percent"] else "This policy has no co-payment."),
        ("4. Sub-limits",
         "; ".join(f"{s['name']}: up to Rs {s['limit']:,.0f}" for s in p["sub_limits"]) + ". No other sub-limits apply."
         if p["sub_limits"] else "This policy has no disease-wise or procedure-wise sub-limits."),
        ("5. Grievances", "Complaints may be made to the Grievance Redressal Officer, then on the Bima Bharosa portal "
                          "and to the Insurance Ombudsman."),
    ]
    story = [
        Paragraph(p["insurer_name"], H1),
        Paragraph("POLICY SCHEDULE AND WORDING (EXTRACT) - Family Health Plan", H2),
        table([
            ["Policy number", p["policy_number"]],
            ["Insured", b["patient_name"]],
            ["Sum insured", rs(p["sum_insured"])],
            ["Period", "01-04-2026 to 31-03-2027"],
        ], [50 * mm, 90 * mm], header=False),
        Spacer(1, 10),
    ]
    for title, text in clauses:
        story += [Paragraph(f"<b>{title}</b>", P), Paragraph(text, P), Spacer(1, 6)]
    build(out, story)


if __name__ == "__main__":
    for case_dir in sorted(CASES.iterdir()):
        truth = case_dir / "truth.json"
        if not truth.exists():
            continue
        case = json.loads(truth.read_text(encoding="utf-8"))
        bill_pdf(case, case_dir / "bill.pdf")
        settlement_pdf(case, case_dir / "settlement.pdf")
        policy_pdf(case, case_dir / "policy.pdf")
        print("made", case_dir.name)
