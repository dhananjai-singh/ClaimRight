"""Fill the Startup Buildathon idea-submission template with our content.

Run:  python -I deck/build_deck.py
Edit TEAM_NAME / TEAM_SIZE / PRODUCT below, re-run, and the PDF is rebuilt.
"""
import math
import sys

import pymupdf

TEMPLATE = r"C:\Users\asus\Downloads\Documents\Startup Buildathon _ Idea Submission Deck.pdf"
OUT = r"C:\Projects\Buildathon\deck\ClaimRight - Idea Submission.pdf"

TEAM_NAME = "Aviti"
TEAM_SIZE = "2"
PRODUCT = "ClaimRight"
REPORT_CARD_URL = ("https://datastudio.google.com/conversation?agent=projects/claimright-aviti/"
                   "locations/us/dataAgents/agent_df7c8b7f-00a1-41f8-8808-188940a9790b")

INK, QUIET = "#202124", "#5f6368"
BLUE, GREEN, RED, YELLOW = "#4285F4", "#34A853", "#EA4335", "#F9AB00"
TINT = {BLUE: "#E8F0FE", GREEN: "#E6F4EA", RED: "#FCE8E6", YELLOW: "#FEF7E0"}
GREY_TINT = "#F1F3F4"

ARCH = pymupdf.Archive(r"C:\Windows\Fonts")
CSS = """
@font-face {font-family: seg; src: url(segoeui.ttf);}
@font-face {font-family: seg; src: url(segoeuib.ttf); font-weight: bold;}
* {font-family: seg; margin: 0; padding: 0;}
p {margin-bottom: 4px; line-height: 1.3;}
ul, ol {margin-left: 0; padding-left: 0;}
li {margin-left: 12px;}
li {margin-bottom: 3px; line-height: 1.3;}
b {font-weight: bold;}
table {border-collapse: collapse; width: 100%;}
td, th {padding: 3px 5px; vertical-align: top; line-height: 1.25; border-bottom: 0.6px solid #dadce0;}
th {text-align: left; font-weight: bold; background-color: #F1F3F4;}
"""

overflow = []


def rgb(hexstr):
    h = hexstr.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def text(page, rect, body, size=10, color=INK, align="left"):
    r = pymupdf.Rect(rect)
    spare, scale = page.insert_htmlbox(
        r,
        f'<div style="font-size:{size}px;color:{color};text-align:{align}">{body}</div>',
        css=CSS, archive=ARCH, scale_low=0.85)
    if scale < 1:
        overflow.append((page.number, body[:50], round(scale, 2)))


def box(page, rect, fill, stroke=None, radius=0.08, width=1.2):
    page.draw_rect(pymupdf.Rect(rect), color=rgb(stroke) if stroke else None,
                   fill=rgb(fill), width=width, radius=radius)


def arrow(page, p1, p2, color="#80868b", width=1.3, head=5):
    p1, p2 = pymupdf.Point(p1), pymupdf.Point(p2)
    page.draw_line(p1, p2, color=rgb(color), width=width)
    ang = math.atan2(p2.y - p1.y, p2.x - p1.x)
    left = pymupdf.Point(p2.x - head * math.cos(ang - 0.45), p2.y - head * math.sin(ang - 0.45))
    right = pymupdf.Point(p2.x - head * math.cos(ang + 0.45), p2.y - head * math.sin(ang + 0.45))
    page.draw_polyline([p2, left, right, p2], color=rgb(color), fill=rgb(color), width=0.5)


def clear_placeholder(page):
    hits = page.search_for("Type here")
    for h in hits:
        page.add_redact_annot(h + (-2, -2, 30, 2))
    if hits:
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)


def heading(page, title, subtitle):
    """Header for the blank template page, matching the filled pages' style."""
    text(page, (39, 80, 681, 106), title, size=20, color=INK)
    text(page, (39, 106, 681, 122), subtitle, size=10.5, color=INK)


def footnote(page, body):
    text(page, (39, 389, 681, 403), body, size=6.5, color=QUIET)


# ---------------------------------------------------------------- slides

def title_slide(p):
    text(p, (137, 263, 681, 281), TEAM_NAME, size=13)
    text(p, (122, 297, 681, 315), TEAM_SIZE, size=13)
    text(p, (183, 330, 681, 395),
         f"{PRODUCT}: Indian families lose crores every year to unfair health-insurance "
         "claim cuts, and have no easy, affordable way to get that money back.", size=13)


def problem_slide(p):
    clear_placeholder(p)
    box(p, (39, 136, 392, 382), GREY_TINT)
    text(p, (51, 145, 382, 378), f"""
<p style="font-size:11px;color:{RED}"><b>A real moment, in lakhs of families</b></p>
<p>Rahul's mother has surgery. The bill is <b>₹1,80,000</b>. The insurer pays ₹1,58,000 and
calls <b>₹22,000 "non-payable"</b>. The hospital won't discharge her until he pays the gap. He pays.
He still doesn't know if the cut was fair.</p>
<p style="margin-top:6px"><b>Why the money is simply lost</b></p>
<ul>
<li>Policy wording is confusing, and few people know IRDAI's own rules on what insurers must pay.</li>
<li>Nobody has the energy to fight while someone they love is in hospital.</li>
<li>Recovery firms charge about 18% and suit large claims, so cuts of ₹5,000 to ₹50,000 go unchallenged.</li>
</ul>""", size=10.4)

    stats = [
        (RED, "₹15,100 Cr", "of health claims disallowed by insurers in FY24"),
        (GREEN, "71%", "of 53,184 Insurance Ombudsman complaints (FY25) went the policyholder's way"),
        (BLUE, "3.26 crore", "health claims in FY25; about 8% rejected outright"),
    ]
    y = 136
    for color, big, small in stats:
        box(p, (406, y, 681, y + 76), TINT[color])
        text(p, (418, y + 8, 672, y + 36), big, size=21, color=color)
        text(p, (418, y + 39, 672, y + 72), small, size=9.2)
        y += 85
    footnote(p, "Sources: IRDAI data via Business Standard (Dec 2024); Insurance Business Asia (2025); "
                "Insurance Samadhan fee via IT Brief (Mar 2026). Rahul is an illustrative example.")


def solution_slide(p):
    clear_placeholder(p)
    text(p, (39, 132, 681, 160),
         f"<b>{PRODUCT}</b> is an AI claims copilot on WhatsApp and the web, in Hindi and English. "
         "It finds the unfair cuts in a family's insurance settlement and fights to get the money back.",
         size=10.2)
    steps = [
        (BLUE, "1  Upload or just talk",
         "Photos of the hospital bill, settlement letter and policy. Or explain it by voice in Hindi."),
        (RED, "2  Find the unfair cuts",
         "Gemini reads every line. Our rules engine checks each cut against IRDAI rules and the policy."),
        (YELLOW, "3  Fight for you",
         "One tap drafts the complaint. We track deadlines and escalate to IRDAI and the Ombudsman."),
        (GREEN, "4  Small, fair fee",
         "₹299 for the work, plus a 10% success fee that is refunded if we don't win."),
    ]
    w, gap, x = 151.5, 12, 39
    for color, title, body in steps:
        box(p, (x, 168, x + w, 250), TINT[color])
        text(p, (x + 9, 176, x + w - 8, 194), f"<b>{title}</b>", size=10.2, color=color)
        text(p, (x + 9, 197, x + w - 8, 248), body, size=9.2)
        if x + w < 640:
            arrow(p, (x + w + 1, 209), (x + w + gap - 1, 209))
        x += w + gap

    box(p, (39, 262, 681, 330), "#FFFFFF", stroke="#dadce0", width=0.8)
    text(p, (51, 269, 672, 328), f"""
<p style="color:{QUIET};font-size:8.5px">WHAT THE FAMILY SEES</p>
<p>"₹18,400 of your ₹22,000 cut looks wrong: ₹12,000 for items your policy covers, and ₹6,400 from a
room-rent deduction wrongly applied to medicines. Shall I file the complaint?"</p>""", size=9.8)

    text(p, (39, 342, 681, 386), f"""
<p><b>Who pays:</b> families pay ₹299 plus a refundable 10% success fee, so they risk only ₹299. Next, small hospitals
pay a monthly plan to check claims <i>before</i> they go to the insurer, so the cut never happens.</p>""",
         size=9.8)


def architecture_slide(p):
    clear_placeholder(p)
    W, H = 140, 58
    xs = [39, 206, 373, 541]
    r1, r2 = 136, 214

    def node(x, y, title, l1, l2, color=None):
        fill = TINT[color] if color else "#FFFFFF"
        box(p, (x, y, x + W, y + H), fill, stroke=color or "#bdc1c6", width=1.4 if color else 0.9)
        text(p, (x + 8, y + 7, x + W - 6, y + 22), f"<b>{title}</b>", size=9.4, color=INK)
        text(p, (x + 8, y + 24, x + W - 6, y + H - 2), f"{l1}<br>{l2}", size=8.2, color=QUIET)

    node(xs[0], r1, "Family or hospital desk", "WhatsApp or web app", "Photos + Hindi voice")
    node(xs[1], r1, "API on Cloud Run", "Receives documents", "Runs each case")
    node(xs[2], r1, "Gemini 3.8 Flash", "Reads bills, settlement", "letters and policy PDFs", BLUE)
    node(xs[3], r1, "Rules engine (plain code)", "IRDAI rules, policy terms,", "room-rent maths", GREEN)
    node(xs[3], r2, "Gemini 4 Argon", "Drafts the complaint, citing", "rules found by File Search", BLUE)
    node(xs[2], r2, "Escalation agent", "Antigravity + Agent Skills,", "tracks every deadline", YELLOW)
    node(xs[1], r2, "Where it goes", "Insurer grievance, then IRDAI", "Bima Bharosa, Ombudsman")
    node(xs[0], r2, "Gemini 3.8 Live", "Hindi voice: hears the", "problem, explains the result", BLUE)

    for a, b in zip(xs, xs[1:]):
        arrow(p, (a + W + 1, r1 + H / 2), (b - 1, r1 + H / 2))
    arrow(p, (xs[3] + W / 2, r1 + H + 1), (xs[3] + W / 2, r2 - 1))
    arrow(p, (xs[3] - 1, r2 + H / 2), (xs[2] + W + 1, r2 + H / 2))
    arrow(p, (xs[2] - 1, r2 + H / 2), (xs[1] + W + 1, r2 + H / 2))
    arrow(p, (xs[0] + W / 2, r2 - 1), (xs[0] + W / 2, r1 + H + 1))
    arrow(p, (xs[0] + W / 2, r1 + H + 1), (xs[0] + W / 2, r2 - 1))

    y0 = 290
    box(p, (39, y0, 681, y0 + 80), GREY_TINT)
    text(p, (51, y0 + 7, 672, y0 + 22), "<b>Google Cloud data layer (built with Antigravity + Data Agent Kit)</b>", size=9.4)
    chips = [("BigQuery", "every audited cut + IRDAI rules"), ("MCP Toolbox (Cloud Run)", "insurer track record for the chat agent"),
             ("BigQuery data agent", "Insurer Report Card in Data Studio")]
    cx = 51
    for name, sub in chips:
        box(p, (cx, y0 + 28, cx + 196, y0 + 70), "#FFFFFF", stroke="#bdc1c6", width=0.8)
        text(p, (cx + 8, y0 + 33, cx + 190, y0 + 72), f"<b>{name}</b><br>{sub}", size=8.8)
        cx += 208
    footnote(p, "The AI reads documents and writes letters. All rupee amounts and deadlines are calculated "
                "by plain code, never by the AI. The demo uses synthetic bills, with no real patient data.")


def tools_slide(p):
    clear_placeholder(p)
    cols = [
        (BLUE, "Google AI Studio", [
            "Prototype and test prompts on sample bills and settlement letters",
            "Tune structured extraction of every line item and deduction",
            "Test the Gemini Live voice flow in Hindi",
            "Export the working prototype into Antigravity"]),
        (RED, "Google Antigravity", [
            "Agent-first build of the full app during the two days",
            "Runs the escalation agent: complaint, follow-up, IRDAI portal, Ombudsman",
            "Fast, test-backed changes to the rules engine as we add insurers"]),
        (GREEN, "Google Agent Skills", [
            "read-settlement-letter",
            "check-irdai-rules",
            "room-rent-deduction-check",
            "draft-grievance-letter",
            "escalate-to-ombudsman"]),
    ]
    w, gap, x = 206, 12, 39
    for color, title, items in cols:
        box(p, (x, 136, x + w, 318), TINT[color])
        lis = "".join(f"<li>{i}</li>" for i in items)
        extra = ("<p style='margin-top:5px'>Each skill is a short playbook the agent follows, "
                 "so new insurers and rules are added without retraining.</p>") if "Skills" in title else ""
        text(p, (x + 10, 145, x + w - 8, 316),
             f"<p style='color:{color};font-size:11px'><b>{title}</b></p><ul>{lis}</ul>{extra}", size=9.2)
        x += w + gap
    box(p, (39, 330, 681, 372), GREY_TINT)
    text(p, (51, 337, 672, 370),
         "<b>Live on Google Cloud:</b> Cloud Run (app, API and a private MCP Toolbox), Vertex AI Gemini, an ADK chat "
         "agent, BigQuery and a BigQuery data agent in Data Studio, with the data side built in Antigravity.",
         size=9.4)


def models_slide(p):
    clear_placeholder(p)
    rows = [
        ("Gemini 3.8 Flash", "Reads photos of bills, settlement letters and policy PDFs into clean line items", "Core"),
        ("Gemini 3.8 Live", "Real-time Hindi voice: the family explains the problem and hears the result", "Core"),
        ("Gemini 4 Argon", "Writes complaints and appeals that cite the exact rule and policy clause", "Core"),
        ("Gemini Embedding 2 + File Search", "Finds the right IRDAI circular and policy clause for each cut", "Core"),
        ("Gemini 3.5 Flash (asia-south1)", "Processes real patient documents inside India for data residency", "Launch"),
        ("Gemma 4", "On-device option for hospitals that keep claim files on their own computers", "Planned"),
    ]
    trs = "".join(f"<tr><td style='width:190px'><b>{m}</b></td><td>{u}</td><td style='width:50px'>{s}</td></tr>" for m, u, s in rows)
    text(p, (39, 136, 681, 330),
         f"<table><tr><th style='width:190px'>Model</th><th>What it does in {PRODUCT}</th>"
         f"<th style='width:50px'>Stage</th></tr>{trs}</table>", size=9.6)
    box(p, (39, 290, 681, 332), TINT[GREEN])
    text(p, (51, 297, 672, 330),
         "<b>Design rule:</b> Gemini reads and writes; plain code does every rupee calculation and deadline, "
         "so amounts are always exact and every claim we make can be traced to a rule.", size=9.6)


def business_slide(p):
    heading(p, "Business Model", "Who pays, and why they will.")
    tiers = [
        (GREEN, "Families: now", "<b>₹299</b> for the work, plus a <b>10% success fee</b> paid upfront "
         "(max ₹2,999). Not recovered in 120 days? The 10% comes back.",
         "Proof people pay: Insurance Samadhan charges 18% + GST and has handled 20,000+ cases."),
        (BLUE, "Small hospitals: next", "₹5,000 to ₹15,000 a month to check every claim before it is sent and answer insurer queries.",
         "Proof: hospitals already pay firms like Care.fi and ClaimBuddy to chase claims."),
        (YELLOW, "Employers: later", "Claims help offered as an employee benefit on group health policies, priced per employee.",
         "Same engine, sold to HR teams."),
    ]
    w, gap, x = 206, 12, 39
    for color, title, body, proof in tiers:
        box(p, (x, 136, x + w, 262), TINT[color])
        text(p, (x + 10, 145, x + w - 8, 260),
             f"<p style='color:{color};font-size:11px'><b>{title}</b></p><p>{body}</p>"
             f"<p style='color:{QUIET};margin-top:4px'>{proof}</p>", size=9.4)
        x += w + gap
    box(p, (39, 272, 352, 378), TINT[GREEN])
    text(p, (49, 279, 346, 376), f"""
<p><b>Example: a ₹10,000 cut that was wrong</b></p>
<p>Family pays upfront: ₹299 + ₹1,000 = <b>₹1,299</b></p>
<p>We win: we keep ₹1,299 (13%, vs about 21% at recovery firms)</p>
<p>We don't: ₹1,000 refunded, we keep ₹299</p>
<p style="color:{QUIET}">Partial win: 10% of what comes back.</p>""",
         size=9)
    box(p, (364, 272, 681, 378), GREY_TINT)
    text(p, (374, 279, 674, 376), """
<p><b>Rough size (estimates, bottom-up)</b></p>
<ul>
<li>Families: 65,000 cases a year × (₹299 + 10% of ₹15,000 × 70% win rate) ≈ ₹8.8 Cr a year.</li>
<li>Hospitals: about 11,400 nursing homes of 10 to 50 beds × ₹60,000 a year ≈ ₹68 Cr a year.</li>
</ul>""", size=9.2)
    footnote(p, "Sources: Insurance Samadhan via IT Brief (Mar 2026); Accion (38,000 private hospitals); 71% of "
                "Ombudsman complaints went the policyholder's way in FY25. Case counts, win rate and prices are our "
                "assumptions, to be validated. Fees exclude 18% GST.")


def competition_slide(p):
    heading(p, "Competition", "Who else helps, and why families will pick us.")
    head = ["", "Insurance Samadhan", "Free AI letter tools", "Broker claim desks", PRODUCT]
    rows = [
        ("Who does the work", "Human staff", "You", "Broker staff", "AI, with human review"),
        ("Fee", "About 18% + GST", "Free", "Bundled", "₹299 + 10% (refunded if no win)"),
        ("Small cuts (₹5k to ₹50k)", "Not their focus", "Yes", "Own policies only", "Yes"),
        ("Checks each cut against IRDAI rules", "Manually", "No", "Sometimes", "Yes, line by line"),
        ("Follows up to the Ombudsman", "Yes", "No", "Sometimes", "Yes, deadlines tracked"),
        ("Hindi voice and WhatsApp", "No", "No", "Varies", "Yes"),
    ]
    ths = "".join(
        f"<th style='{'color:#FFFFFF;background-color:' + GREEN if h == PRODUCT else ''}'>{h}</th>" for h in head)
    trs = "".join(
        "<tr>" + "".join(
            f"<td style='{'font-weight:bold;' if i == 0 else ''}{'background-color:' + TINT[GREEN] + ';' if i == 4 else ''}'>{c}</td>"
            for i, c in enumerate(r)) + "</tr>" for r in rows)
    text(p, (39, 136, 681, 320), f"<table>{ths and '<tr>' + ths + '</tr>'}{trs}</table>", size=9.4)
    box(p, (39, 296, 681, 340), TINT[GREEN])
    text(p, (51, 304, 672, 338),
         "<b>Our edge:</b> AI makes small claims worth fighting. We charge less, work in Hindi on WhatsApp, "
         "and finish in days, not months. Hospital-side players (Care.fi, ClaimBuddy, Medi Assist) focus on "
         "bigger hospitals, managed services or lending.", size=9.8)
    footnote(p, "Competitor details from public coverage (IT Brief, Accion, Outlook Business, CXOToday). "
                "\"Not their focus\" is our reading of their model.")


def build_plan_slide(p):
    heading(p, "Two-Day Build and Roadmap", "What we will demo at the Buildathon, and what comes after.")
    box(p, (39, 136, 392, 382), TINT[BLUE])
    text(p, (51, 145, 382, 378), f"""
<p style="color:{BLUE};font-size:11px"><b>Demo at the Buildathon</b></p>
<ol>
<li>Upload a realistic sample bill, settlement letter and policy.</li>
<li>Gemini extracts every line item and deduction.</li>
<li>Rules engine flags unfair cuts with the rupee amount and the reason.</li>
<li>Ask ClaimRight (ADK agent): "why was my claim cut?" in Hindi or English, answered from the audit.</li>
<li>One tap produces the complaint letter and the escalation timeline.</li>
<li>Insurer Report Card: a BigQuery data agent in Data Studio shows which insurers cut wrongly, and how often.</li>
<li>Live on Google Cloud (Cloud Run), synthetic data only.</li>
</ol>""", size=10.4)
    for r in p.search_for("Insurer Report Card"):
        p.insert_link({"kind": pymupdf.LINK_URI, "from": r, "uri": REPORT_CARD_URL})
    phases = [
        (GREEN, "Month 1 to 3", "Pilot with 50 families via WhatsApp; recover first claims; tune rules for the top 10 insurers."),
        (YELLOW, "Month 4 to 9", "Add Tamil, Telugu, Marathi, Bengali; launch the hospital pre-check plan with 10 nursing homes."),
        (RED, "Month 10+", "Employer benefit partnerships; scale hospital plan across tier-2 and tier-3 cities."),
    ]
    y = 136
    for color, when, what in phases:
        box(p, (406, y, 681, y + 76), TINT[color])
        text(p, (418, y + 8, 672, y + 74),
             f"<p style='color:{color};font-size:10.5px'><b>{when}</b></p><p>{what}</p>", size=9.4)
        y += 85


def main():
    src = pymupdf.open(TEMPLATE)
    # 0 guidelines, 1 title, 2 problem, 3 solution, 4 architecture, 5 tools, 6 models, 7 blank, 8 thanks
    out = pymupdf.open()
    order = [1, 2, 3, 4, 5, 6, 7, 7, 7, 8]
    for i in order:
        out.insert_pdf(src, from_page=i, to_page=i)
    fillers = [title_slide, problem_slide, solution_slide, architecture_slide, tools_slide,
               models_slide, business_slide, competition_slide, build_plan_slide, None]
    for page, fn in zip(out, fillers):
        if fn:
            fn(page)
    out.save(OUT, garbage=4, deflate=True)
    sys.stdout.reconfigure(encoding="utf-8")
    print("saved", OUT)
    print("overflow:", overflow or "none")


if __name__ == "__main__":
    main()
