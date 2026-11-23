"""Fill the Startup Buildathon *final prototype* template with ClaimRight content.

Run:  python deck/build_final_deck.py
Needs: python-pptx, qrcode[pil]. Screenshots of the live app are in deck/shots/.
"""
import copy
import io
from pathlib import Path

import qrcode
from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

TEMPLATE = Path(r"C:\Users\asus\Downloads\Final Prototype Submission Deck _ Startup Buildathon.pptx")
OUT = Path(r"C:\Projects\Buildathon\deck\ClaimRight - Final Prototype Submission.pptx")
SHOTS = Path(__file__).resolve().parent / "shots"

LIVE_URL = "https://claimright-809314822230.us-central1.run.app"
REPORT_CARD_URL = ("https://datastudio.google.com/conversation?agent=projects/claimright-aviti/"
                   "locations/us/dataAgents/agent_df7c8b7f-00a1-41f8-8808-188940a9790b")

# ClaimRight app palette
NAVY, GREEN, RED, AMBER = "0F2A4A", "15803D", "B91C1C", "B45309"
SLATE, MUTED, LINE, WHITE = "334155", "64748B", "CBD5E1", "FFFFFF"
NAVY_T, GREEN_T, RED_T, AMBER_T, GREY_T = "E8EDF3", "E7F3EA", "FDECEC", "FDF3E3", "F1F5F9"
BLUE, BLUE_T = "1A73E8", "E8F0FE"   # Google blue, for Google Cloud / Vertex AI boxes
FONT = "Arial"
TITLE_FONT = "Google Sans Flex Medium"


def rgb(h):
    return RGBColor.from_string(h)


# ---------------------------------------------------------------- helpers

def text(slide, x, y, w, h, paras, size=12, color=SLATE, bold=False, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, font=FONT, space_after=4, name=None, margin=0.0):
    """paras: str | list of (str | list of (text, {opts})). Each item is one paragraph."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for side in ("left", "right", "top", "bottom"):
        setattr(tf, f"margin_{side}", Inches(margin))
    if isinstance(paras, str):
        paras = [paras]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space_after)
        runs = [(para, {})] if isinstance(para, str) else para
        for t, o in runs:
            r = p.add_run()
            r.text = t
            f = r.font
            f.name = o.get("font", font)
            f.size = Pt(o.get("size", size))
            f.bold = o.get("bold", bold)
            f.italic = o.get("italic", False)
            f.color.rgb = rgb(o.get("color", color))
            if o.get("link"):
                r.hyperlink.address = o["link"]
    return tb


def box(slide, x, y, w, h, fill, line=None, shape=MSO_SHAPE.RECTANGLE, name=None, line_w=1.0):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        s.name = name
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = 0.08
    s.fill.solid()
    s.fill.fore_color.rgb = rgb(fill)
    if line:
        s.line.color.rgb = rgb(line)
        s.line.width = Pt(line_w)
    else:
        s.line.fill.background()
    s.shadow.inherit = False
    s.text_frame.text = ""
    return s


def labeled_box(slide, x, y, w, h, title, sub="", fill=WHITE, line=NAVY, title_color=NAVY, size=11, sub_size=9.5,
                align=PP_ALIGN.CENTER):
    box(slide, x, y, w, h, fill, line, MSO_SHAPE.ROUNDED_RECTANGLE)
    paras = [[(title, {"bold": True, "color": title_color, "size": size})]]
    if sub:
        paras.append([(sub, {"color": SLATE, "size": sub_size})])
    text(slide, x + 0.08, y + 0.04, w - 0.16, h - 0.08, paras, align=align, anchor=MSO_ANCHOR.MIDDLE, space_after=2)


def arrow(slide, x1, y1, x2, y2, color=MUTED, width=1.5):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = rgb(color)
    c.line.width = Pt(width)
    ln = c.line._get_or_add_ln()
    tail = etree.SubElement(ln, qn("a:tailEnd"))
    tail.set("type", "triangle")
    tail.set("w", "med")
    tail.set("h", "med")
    return c


def phone(slide, name, x, y, h, caption=None, cap_color=NAVY):
    path = SHOTS / f"{name}.png"
    pic = slide.shapes.add_picture(str(path), Inches(x), Inches(y), height=Inches(h))
    pic.line.color.rgb = rgb(NAVY)
    pic.line.width = Pt(1.5)
    pic.name = f"Screen: {name}"
    w = pic.width / 914400
    if caption:
        text(slide, x - 0.1, y + h + 0.06, w + 0.2, 0.3, [[(caption, {"bold": True, "color": cap_color, "size": 10})]],
             align=PP_ALIGN.CENTER)
    return w


def badge(slide, x, y, label, fill=NAVY, size=0.34, font_size=11):
    s = box(slide, x, y, size, size, fill, None, MSO_SHAPE.OVAL)
    text(slide, x, y, size, size, [[(label, {"bold": True, "color": WHITE, "size": font_size})]],
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    return s


def title(slide, t):
    """Title for the template's blank slides, matching the other slides' title box."""
    tb = text(slide, 0.29, 0.73, 9.78, 0.61, [[(t, {"font": TITLE_FONT, "size": 16, "color": "000000"})]],
              name="Title")
    tf = tb.text_frame
    tf.margin_left = tf.margin_right = Inches(0.1)
    tf.margin_top = tf.margin_bottom = Inches(0.1)


def subtitle(slide, t, y=1.25):
    text(slide, 0.4, y, 9.2, 0.3, [[(t, {"color": MUTED, "size": 11, "italic": True})]])


def set_first_text(shape, new):
    """Keep the template title's formatting; replace its text and drop the prompt lines below it."""
    paras = shape.text_frame.paragraphs
    runs = paras[0].runs
    runs[0].text = new
    for r in runs[1:]:
        r._r.getparent().remove(r._r)
    for br in paras[0]._p.findall(qn("a:br")):
        paras[0]._p.remove(br)
    for p in paras[1:]:
        p._p.getparent().remove(p._p)
    shape.height = Inches(0.61)


def title_shape(slide):
    return [s for s in slide.shapes if s.has_text_frame][0]


def notes(slide, t):
    slide.notes_slide.notes_text_frame.text = t


def delete_slide(prs, index):
    sld_ids = prs.slides._sldIdLst
    sld = sld_ids[index]
    prs.part.drop_rel(sld.get(qn("r:id")))
    sld_ids.remove(sld)


# ---------------------------------------------------------------- slides

def s_team(slide):
    tb = [s for s in slide.shapes if s.has_text_frame][0]
    tb.left, tb.top, tb.width, tb.height = Inches(0.64), Inches(3.35), Inches(8.9), Inches(2.1)
    tf = tb.text_frame
    tf.word_wrap = True
    values = {"Team Name:": " Aviti", "Team Size:": " 2",
              "Problem Statement:": (" Indian families lose money when health insurers wrongly cut hospital claims. "
                                     "Small cuts of ₹2,000 to ₹50,000 are almost never fought: the IRDAI rules and policy "
                                     "terms are hard to read, and recovery firms and lawyers skip claims this small.")}
    for p in tf.paragraphs:
        if p.text in values and p.runs:
            src = p.runs[0]
            src.font.bold = True
            r = copy.deepcopy(src._r)
            src._r.addnext(r)
            new = p.runs[-1]
            new.text = values[src.text]
            new.font.bold = False
        if p.text.startswith("Problem Statement:"):
            for r in p.runs:
                r.font.size = Pt(15)
    notes(slide, "Team Aviti (2 people). ClaimRight targets the small claim cuts nobody fights.")


def s_brief(slide):
    set_first_text(title_shape(slide), "Brief about the idea")
    text(slide, 0.4, 1.4, 5.2, 0.75,
         [[("ClaimRight: an AI auditor that checks every rupee your health insurer cut", {"bold": True, "size": 19,
                                                                                         "color": NAVY})]])
    text(slide, 0.4, 2.2, 5.2, 1.3,
         ["Families upload the hospital bill, the settlement letter and the policy. Gemini reads them; a rules "
          "engine checks every cut against IRDAI rules and the policy, explains it in English or Hindi and writes "
          "the complaint letter.",
          "Hospitals get the same check upfront: a pre-check panel inside their billing software flags the charges "
          "an insurer will cut, before the claim is sent."], size=12)
    steps = [("01", "Upload", "Photo or PDF of 3 documents", NAVY),
             ("02", "Check", "Gemini + IRDAI rules, every line", GREEN),
             ("03", "Fight", "Letter + escalation timeline", AMBER)]
    x = 0.4
    for num, head, sub, col in steps:
        box(slide, x, 3.95, 1.62, 0.92, GREY_T, None, MSO_SHAPE.ROUNDED_RECTANGLE)
        text(slide, x + 0.12, 4.0, 1.4, 0.85, [[(num + "  ", {"bold": True, "color": col, "size": 12}),
                                               (head, {"bold": True, "color": NAVY, "size": 13})],
                                              [(sub, {"size": 10, "color": SLATE})]], space_after=3)
        x += 1.79
    text(slide, 0.4, 5.02, 5.4, 0.3, [[("Live on Google Cloud: ", {"bold": True, "color": NAVY, "size": 10.5}),
                                       ("claimright-809314822230.us-central1.run.app",
                                        {"color": BLUE, "size": 10.5, "link": LIVE_URL})]])
    phone(slide, "home", 5.95, 1.4, 3.75)
    phone(slide, "report", 7.85, 1.4, 3.75)
    notes(slide, "One-line pitch, then the 3-step flow. Both phone screens are from the live Cloud Run app.")


def s_opportunities(slide):
    set_first_text(title_shape(slide), "Opportunities")
    cards = [
        ("How is it different from existing ideas?", NAVY, NAVY_T, [
            "Recovery firms such as Insurance Samadhan use human staff and charge about 18% + GST; small cuts are not their focus.",
            "Free AI letter tools write a letter but never check the cut against the rules.",
            "ClaimRight checks each line against the IRDAI circular and the family's own policy, and cites the source."]),
        ("How will it solve the problem?", GREEN, GREEN_T, [
            "Finds the cuts that break a rule, with the exact rupee amount, calculated by code, never by the AI.",
            "Explains each cut in plain English or Hindi.",
            "Writes the complaint letter and gives dated next steps: insurer, then Bima Bharosa, then the Ombudsman.",
            "For hospitals, the same rules run inside billing software and stop the cut before the claim is sent."]),
        ("USP of the solution", AMBER, AMBER_T, [
            "Built for small claims (₹2,000 to ₹50,000) that nobody fights today.",
            "The check is free. To fight: ₹299 + a 10% success fee that is refunded if nothing is recovered.",
            "Every verdict traces to an official source; the insurer track record comes from BigQuery."]),
    ]
    x = 0.4
    for head, col, tint, items in cards:
        box(slide, x, 1.45, 2.95, 2.95, tint, None, MSO_SHAPE.ROUNDED_RECTANGLE)
        paras = [[(head, {"bold": True, "color": col, "size": 13})]]
        paras += [[("■  ", {"color": col, "size": 8}), (t, {"size": 11})] for t in items]
        text(slide, x + 0.18, 1.58, 2.62, 2.8, paras, space_after=7)
        x += 3.12
    box(slide, 0.4, 4.6, 9.2, 0.7, WHITE, GREEN, MSO_SHAPE.ROUNDED_RECTANGLE)
    text(slide, 0.6, 4.62, 8.8, 0.66,
         [[("Why it is winnable: ", {"bold": True, "color": GREEN, "size": 12}),
           ("71% of Insurance Ombudsman complaints went the policyholder's way in FY25. Families just need "
            "to know which cut to fight, and how.", {"size": 12})]], anchor=MSO_ANCHOR.MIDDLE)
    notes(slide, "Different: rules-checked, not just a letter. Solves: rupee-exact verdicts plus the letter and "
                 "escalation. USP: small claims, low risk pricing, traceable sources.")


def s_features(slide):
    set_first_text(title_shape(slide), "List of features offered by the solution")
    feats = [
        ("Upload + Gemini reading", "Photo or PDF of bill, letter and policy; every line into structured data.", NAVY),
        ("Rule-by-rule verdicts", "Wrong / ask the insurer / looks right, each with the ₹ amount.", GREEN),
        ("Plain explanations", "Each cut explained in English and Hindi, with the rule and its source.", GREEN),
        ("Ask ClaimRight agent", "ADK chat agent answers questions about the claim in Hindi or English.", BLUE),
        ("Insurer track record", "How often this insurer breaks the same rule (BigQuery via MCP Toolbox).", BLUE),
        ("Complaint letter", "EN/HI letter with fill-in blanks; copy, WhatsApp, email or download.", AMBER),
        ("Escalation timeline", "Dated steps: insurer's grievance officer, Bima Bharosa, Ombudsman.", AMBER),
        ("Insurer Report Card", "BigQuery data agent in Data Studio: wrong cuts by insurer, rule, city.", RED),
        ("Hospital pre-check", "Panel in the hospital's billing software flags cuts before the claim is sent.", RED),
    ]
    w, h, gx, gy = 2.95, 1.13, 0.175, 0.17
    for i, (head, sub, col) in enumerate(feats):
        r, c = divmod(i, 3)
        x, y = 0.4 + c * (w + gx), 1.45 + r * (h + gy)
        box(slide, x, y, w, h, WHITE, LINE, MSO_SHAPE.ROUNDED_RECTANGLE)
        badge(slide, x + 0.15, y + 0.17, f"{i + 1}", fill=col)
        text(slide, x + 0.6, y + 0.12, w - 0.72, h - 0.2,
             [[(head, {"bold": True, "color": NAVY, "size": 12})], [(sub, {"size": 10, "color": SLATE})]],
             space_after=3)
    notes(slide, "Nine features, all working in the live prototype.")


def s_flow(slide):
    set_first_text(title_shape(slide), "Process flow diagram")
    w, h = 1.62, 1.0
    xs = [0.4, 2.29, 4.18, 6.07, 7.96]
    y1, y2 = 1.55, 3.45
    row1 = [("Family uploads", "bill, settlement letter, policy", WHITE, NAVY),
            ("Gemini 3.8 Flash", "reads every line item and cut", BLUE_T, BLUE),
            ("Rules engine", "checks each cut: 9 IRDAI and policy rules", GREEN_T, GREEN),
            ("Verdicts", "wrong / ask / looks right, ₹ to claim back", WHITE, NAVY),
            ("Anything wrong?", "No: 'claim looks correct', nothing to pay", AMBER_T, AMBER)]
    for x, (t, s, fill, line) in zip(xs, row1):
        labeled_box(slide, x, y1, w, h, t, s, fill=fill, line=line, title_color=line)
    for a, b in zip(xs, xs[1:]):
        arrow(slide, a + w + 0.03, y1 + h / 2, b - 0.03, y1 + h / 2)
    arrow(slide, xs[4] + w / 2, y1 + h + 0.03, xs[4] + w / 2, y2 - 0.03, color=GREEN)
    text(slide, xs[4] + w / 2 + 0.08, y1 + h + 0.25, 0.6, 0.3, [[("Yes", {"bold": True, "color": GREEN, "size": 10})]])
    row2 = [("Outcome", "Win: keep 10%. Nothing in 120 days: 10% refunded", GREEN_T, GREEN),
            ("Insurance Ombudsman", "free for the family", WHITE, NAVY),
            ("Bima Bharosa (IRDAI)", "if no fix in 14 days", WHITE, NAVY),
            ("Complaint letter", "to the insurer's grievance officer, EN/HI", WHITE, NAVY),
            ("Family chooses to fight", "₹299 + 10% (refundable)", AMBER_T, AMBER)]
    for x, (t, s, fill, line) in zip(xs, row2):
        labeled_box(slide, x, y2, w, h, t, s, fill=fill, line=line, title_color=line)
    for a, b in zip(xs[1:], xs):
        arrow(slide, a - 0.03, y2 + h / 2, b + w + 0.03, y2 + h / 2)
    text(slide, 0.4, 4.62, 9.2, 0.85,
         [[("At every step: ", {"bold": True, "color": NAVY, "size": 10.5}),
           ("the family can ask the \"Ask ClaimRight\" agent in Hindi or English. Rupee amounts and deadlines come "
            "from code; Gemini only reads and explains.", {"size": 10.5})],
          [("For hospitals: ", {"bold": True, "color": RED, "size": 10.5}),
           ("the same rules run before the claim is sent (room above the limit, items billed the wrong way, "
            "sub-limits), each flagged with the fix, so the top row never has to happen.", {"size": 10.5})]],
         space_after=3)
    notes(slide, "Top row is the free check. Bottom row runs right to left: the paid fight and the escalation ladder.")


def s_wireframes(slide):
    set_first_text(title_shape(slide), "Wireframes/Mock diagrams of the proposed solution")
    subtitle(slide, "Mobile-first web app, English and Hindi. Screens from the working prototype, in the order a family sees them.")
    names = [("onboarding", "1  Why it matters"), ("home", "2  Home"), ("upload", "3  Upload"),
             ("checking", "4  Checking"), ("cut", "5  Each cut explained")]
    x = 0.45
    for n, cap in names:
        w = phone(slide, n, x, 1.65, 3.3, caption=cap)
        if n != "cut":
            arrow(slide, x + w + 0.07, 3.3, x + w + 0.33, 3.3, color=GREEN)
        x += w + 0.4
    notes(slide, "Design: newspaper style, square corners, navy and green; Anton headlines, Inter body, "
                 "Noto Sans Devanagari for Hindi.")


def s_architecture(slide):
    set_first_text(title_shape(slide), "Architecture diagram of the proposed solution")
    labeled_box(slide, 0.4, 2.05, 1.35, 1.3, "Family or hospital", "family app, or the hospital's billing desk", fill=WHITE, line=NAVY, size=10.5, sub_size=9)
    # Cloud Run app
    box(slide, 2.05, 1.4, 4.35, 2.6, NAVY_T, NAVY, MSO_SHAPE.ROUNDED_RECTANGLE, line_w=1.25)
    text(slide, 2.2, 1.45, 4.1, 0.3, [[("Cloud Run: claimright (app + API)", {"bold": True, "color": NAVY, "size": 11})]])
    inner = [("Web app", "mobile-first, EN / HI"), ("Rules engine", "all ₹ maths; audits + hospital pre-check"),
             ("ADK agent", "\"Ask ClaimRight\", 5 tools"), ("Audit pipeline", "upload, read, check, explain")]
    for i, (t, s) in enumerate(inner):
        r, c = divmod(i, 2)
        labeled_box(slide, 2.2 + c * 2.07, 1.82 + r * 1.06, 1.97, 0.92, t, s, fill=WHITE, line=NAVY, size=10.5, sub_size=9)
    # Vertex AI
    box(slide, 6.75, 1.4, 2.85, 2.6, BLUE_T, BLUE, MSO_SHAPE.ROUNDED_RECTANGLE, line_w=1.25)
    text(slide, 6.9, 1.45, 2.6, 0.3, [[("Vertex AI (Gemini)", {"bold": True, "color": BLUE, "size": 11})]])
    labeled_box(slide, 6.9, 1.82, 2.55, 0.92, "Gemini 3.8 Flash", "reads documents, explains, chats",
                fill=WHITE, line=BLUE, title_color=BLUE, size=10.5, sub_size=9)
    labeled_box(slide, 6.9, 2.88, 2.55, 0.92, "Gemini 3.1 Pro", "writes complaint letters (EN / HI)",
                fill=WHITE, line=BLUE, title_color=BLUE, size=10.5, sub_size=9)
    # data layer
    y = 4.3
    labeled_box(slide, 2.05, y, 2.0, 0.92, "MCP Toolbox", "private Cloud Run, 3 SQL tools", fill=GREEN_T, line=GREEN,
                title_color=GREEN, size=10.5, sub_size=9)
    labeled_box(slide, 4.4, y, 2.0, 0.92, "BigQuery", "audits + IRDAI rules tables", fill=GREEN_T, line=GREEN,
                title_color=GREEN, size=10.5, sub_size=9)
    labeled_box(slide, 6.75, y, 2.85, 0.92, "BigQuery data agent", "\"Insurer Report Card\" in Data Studio",
                fill=GREEN_T, line=GREEN, title_color=GREEN, size=10.5, sub_size=9)
    text(slide, 0.4, y + 0.05, 1.5, 0.85, [[("Data side built with Antigravity + Data Agent Kit",
                                             {"italic": True, "color": GREEN, "size": 9.5})]], anchor=MSO_ANCHOR.MIDDLE)
    # arrows
    arrow(slide, 1.78, 2.7, 2.02, 2.7)
    arrow(slide, 6.43, 2.7, 6.72, 2.7, color=BLUE)
    arrow(slide, 3.18, 3.65, 3.05, y - 0.03, color=GREEN)      # agent -> toolbox
    arrow(slide, 4.08, y + 0.46, 4.37, y + 0.46, color=GREEN)  # toolbox -> bigquery
    arrow(slide, 5.25, 3.65, 5.4, y - 0.03, color=GREEN)       # pipeline saves audits
    arrow(slide, 6.43, y + 0.46, 6.72, y + 0.46, color=GREEN)  # bigquery -> data agent
    text(slide, 5.42, 3.98, 1.2, 0.3, [[("saves each audit", {"size": 8.5, "color": GREEN, "italic": True})]])
    notes(slide, "Everything runs on Google Cloud (us-central1). The Toolbox is private: only the app's service "
                 "account can call it, with an identity token.")


def s_tech(slide):
    set_first_text(title_shape(slide), "Technologies to be used in the solution")
    rows = [("Area", "Google technology", "What it does in ClaimRight"),
            ("Gemini models", "Gemini 3.8 Flash, Gemini 3.1 Pro on Vertex AI",
             "Reads bills and letters with structured output; EN/HI explanations; chat; complaint letters"),
            ("Agents", "Agent Development Kit (ADK), MCP Toolbox for Databases",
             "\"Ask ClaimRight\" chat agent; private, parameterised BigQuery tools for the agent"),
            ("Data and analytics", "BigQuery, BigQuery data agent, Data Studio",
             "Audit log, IRDAI rules table, Insurer Report Card"),
            ("Cloud", "Cloud Run, Secret Manager, Cloud Build, Artifact Registry, IAM",
             "Hosts the app and the Toolbox; private service-to-service access"),
            ("Build tools", "Google Antigravity + Data Agent Kit, Google AI Studio",
             "BigQuery side built agent-first in Antigravity; free-tier development"),
            ("App and quality", "Python, FastAPI, Pydantic, mobile-first web app, pytest",
             "API, family app, hospital billing-desk demo; 27 tests; agent eval with Gemini as judge")]
    tbl = slide.shapes.add_table(len(rows), 3, Inches(0.4), Inches(1.45), Inches(9.2), Inches(3.7)).table
    widths = [1.75, 3.35, 4.1]
    for i, wd in enumerate(widths):
        tbl.columns[i].width = Inches(wd)
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            cell = tbl.cell(r, c)
            cell.fill.solid()
            cell.fill.fore_color.rgb = rgb(NAVY if r == 0 else (GREY_T if r % 2 == 0 else WHITE))
            cell.margin_left = cell.margin_right = Inches(0.08)
            cell.margin_top = cell.margin_bottom = Inches(0.04)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.text = ""
            run = p.add_run()
            run.text = val
            run.font.name = FONT
            run.font.size = Pt(10.5 if r else 11)
            run.font.bold = r == 0 or c == 0
            run.font.color.rgb = rgb(WHITE if r == 0 else (NAVY if c < 2 else SLATE))
    notes(slide, "All Google: Gemini on Vertex AI, ADK, MCP Toolbox, BigQuery + data agent, Cloud Run, Antigravity.")


def s_cost(slide):
    set_first_text(title_shape(slide), "Estimated implementation cost")
    stats = [("₹1.3", "AI cost of one free check", "3 documents read + EN/HI explanations", GREEN),
             ("≈ ₹11", "AI cost of a full fight", "check + EN and HI letters + 10 chat answers", NAVY),
             ("₹0", "AI cost of a hospital pre-check", "plain code, instant; Cloud Run scales to zero", AMBER)]
    y = 1.45
    for big, label, sub, col in stats:
        box(slide, 0.4, y, 3.3, 1.05, GREY_T, None, MSO_SHAPE.ROUNDED_RECTANGLE)
        text(slide, 0.55, y + 0.07, 1.35, 0.9, [[(big, {"bold": True, "color": col, "size": 26})]], anchor=MSO_ANCHOR.MIDDLE)
        text(slide, 1.9, y + 0.07, 1.75, 0.9, [[(label, {"bold": True, "color": NAVY, "size": 11})],
                                                [(sub, {"size": 9.5, "color": SLATE})]], anchor=MSO_ANCHOR.MIDDLE)
        y += 1.17
    rows = [("Step (median, measured)", "Model", "Tokens in / out"),
            ("Read 3 documents", "Gemini 3.8 Flash", "3,671 / 630"),
            ("Explain every cut, EN + HI", "Gemini 3.8 Flash", "533 / 535"),
            ("Complaint letter (per language)", "Gemini 3.1 Pro", "1,067 / 2,711"),
            ("One chat answer", "Gemini 3.8 Flash", "1,855 / 141")]
    tbl = slide.shapes.add_table(len(rows), 3, Inches(4.0), Inches(1.45), Inches(5.6), Inches(2.1)).table
    for i, wd in enumerate([2.45, 1.6, 1.55]):
        tbl.columns[i].width = Inches(wd)
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            cell = tbl.cell(r, c)
            cell.fill.solid()
            cell.fill.fore_color.rgb = rgb(NAVY if r == 0 else (GREY_T if r % 2 == 0 else WHITE))
            cell.margin_left = cell.margin_right = Inches(0.08)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = cell.text_frame.paragraphs[0]
            run = p.add_run()
            run.text = val
            run.font.name, run.font.size = FONT, Pt(10.5)
            run.font.bold = r == 0
            run.font.color.rgb = rgb(WHITE if r == 0 else SLATE)
            if c == 2:
                p.alignment = PP_ALIGN.RIGHT
    text(slide, 4.0, 3.75, 5.6, 1.05,
         [[("Unit economics: ", {"bold": True, "color": NAVY, "size": 11}),
           ("a family that fights pays ₹299 + 10%. The AI cost of the whole journey is about ₹11, under 4% of the "
            "₹299 work fee. Flash does 4 of the 5 jobs; the stronger Pro model only writes the letter.", {"size": 11})]])
    text(slide, 0.4, 5.03, 9.2, 0.4,
         [[("Tokens from our usage log (thinking counted as output). Prices: Gemini 3.8 Flash $1.50 / $7.50 per 1M tokens "
            "(standard rate from 1 Jan 2027; $0.75 / $3.75 until then), Gemini 3.1 Pro $2 / $12 per 1M (third-party "
            "listing). $1 = ₹88.", {"size": 8, "color": MUTED})]])
    notes(slide, "Costs are measured, not guessed: every Gemini call logs its tokens. Uses the higher 2027 Flash rate "
                 "to be conservative.")


def s_snapshots(slide):
    set_first_text(title_shape(slide), "Snapshots of the prototype")
    text(slide, 0.4, 1.25, 9.2, 0.3,
         [[("A real check of a synthetic knee-surgery claim on the live app: ", {"italic": True, "color": MUTED, "size": 11}),
           ("claimright-809314822230.us-central1.run.app", {"italic": True, "color": BLUE, "size": 11, "link": LIVE_URL})]])
    names = [("report", "₹62,000 to claim back"), ("chat", "Agent + BigQuery answer"), ("letter", "Complaint letter")]
    x = 0.45
    for n, cap in names:
        w = phone(slide, n, x, 1.65, 3.3, caption=cap)
        x += w + 0.32
    pic = slide.shapes.add_picture(str(SHOTS / "hospital.png"), Inches(5.95), Inches(2.15), width=Inches(3.65))
    pic.line.color.rgb = rgb(NAVY)
    pic.line.width = Pt(1.5)
    pic.name = "Screen: hospital billing desk"
    ph = pic.height / 914400
    text(slide, 5.95, 2.15 + ph + 0.08, 3.65, 0.55,
         [[("Hospital billing desk: ₹84,375 at risk, caught before the claim is sent", {"bold": True, "color": RED,
                                                                                         "size": 10})]],
         align=PP_ALIGN.CENTER)
    notes(slide, "Chat answer: the ADK agent called insurer_track_record on the MCP Toolbox, which queried BigQuery.")


def s_performance(slide):
    set_first_text(title_shape(slide), "Prototype Performance report/Benchmarking")
    stats = [("3 / 3", "demo claims audited correct to the rupee"),
             ("0", "extraction errors on all 3 synthetic cases"),
             ("100%", "agent eval: 5 checks on 10 questions (EN, HI, Hinglish, off-topic, pressure)"),
             ("27 / 27", "tests passing: rules engine + hospital pre-check"),
             ("22 s", "full live check of 3 PDFs on Cloud Run"),
             ("6.3 s", "median chat answer in the eval")]
    w, h = 2.1, 1.12
    for i, (big, label) in enumerate(stats):
        r, c = divmod(i, 2)
        x, y = 0.4 + c * (w + 0.15), 1.45 + r * (h + 0.15)
        box(slide, x, y, w, h, GREEN_T if i < 4 else NAVY_T, None, MSO_SHAPE.ROUNDED_RECTANGLE)
        text(slide, x + 0.12, y + 0.08, w - 0.24, h - 0.12,
             [[(big, {"bold": True, "color": GREEN if i < 4 else NAVY, "size": 22})],
              [(label, {"size": 9.5, "color": SLATE})]], space_after=1)
    cd = CategoryChartData()
    cd.categories = ["Read policy", "Read bill", "Read settlement", "Explain EN+HI", "Chat answer", "Letter (Pro)"]
    cd.add_series("Seconds", (2.9, 4.0, 4.9, 6.1, 6.3, 26.4))
    gf = slide.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(4.9), Inches(1.4), Inches(4.7), Inches(3.75), cd)
    ch = gf.chart
    ch.has_legend = False
    ch.has_title = True
    ch.chart_title.text_frame.text = "Median seconds per Gemini call (measured)"
    tr = ch.chart_title.text_frame.paragraphs[0].runs[0]
    tr.font.size, tr.font.bold, tr.font.name = Pt(11), True, FONT
    tr.font.color.rgb = rgb(NAVY)
    plot = ch.plots[0]
    plot.gap_width = 60
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.font.size, dl.font.name = Pt(10), FONT
    dl.font.color.rgb = rgb(SLATE)
    dl.number_format, dl.number_format_is_linked = '0.0" s"', False
    dl.position = XL_LABEL_POSITION.OUTSIDE_END
    ser = plot.series[0]
    ser.format.fill.solid()
    ser.format.fill.fore_color.rgb = rgb(GREEN)
    pt = ser.points[5]
    pt.format.fill.solid()
    pt.format.fill.fore_color.rgb = rgb(NAVY)
    ca, va = ch.category_axis, ch.value_axis
    ca.tick_labels.font.size = va.tick_labels.font.size = Pt(9.5)
    ca.tick_labels.font.name = va.tick_labels.font.name = FONT
    ca.tick_labels.font.color.rgb = va.tick_labels.font.color.rgb = rgb(SLATE)
    ca.format.line.color.rgb = rgb(LINE)
    va.visible = False
    va.has_major_gridlines = False
    text(slide, 4.9, 5.15, 4.7, 0.3, [[("The 3 documents are read in parallel. Letters are written once and cached.",
                                        {"size": 9, "color": MUTED, "italic": True})]])
    notes(slide, "Accuracy first: amounts match the hand-made answer key for all 3 demo cases. "
                 "Agent eval checks tool routing, grounded amounts, language, faithfulness and helpfulness.")


def s_future(slide):
    set_first_text(title_shape(slide), "Additional Details/Future Development")
    phases = [("Month 1 to 3", GREEN, GREEN_T, "Pilot with 50 families on WhatsApp; recover the first claims; "
                                              "tune rules for the top 10 insurers."),
              ("Month 4 to 9", AMBER, AMBER_T, "Pilot the pre-check panel in the billing software of 10 nursing homes; "
                                              "add Tamil, Telugu, Marathi, Bengali."),
              ("Month 10+", NAVY, NAVY_T, "Employer benefit partnerships; scale the hospital plan to tier-2 and "
                                         "tier-3 cities.")]
    y = 1.45
    for when, col, tint, what in phases:
        box(slide, 0.4, y, 4.4, 1.15, tint, None, MSO_SHAPE.ROUNDED_RECTANGLE)
        text(slide, 0.58, y + 0.1, 4.1, 1.0, [[(when, {"bold": True, "color": col, "size": 13})],
                                               [(what, {"size": 11})]], space_after=3)
        y += 1.3
    text(slide, 5.15, 1.45, 4.45, 0.35, [[("Next features", {"bold": True, "color": NAVY, "size": 13})]])
    items = ["WhatsApp bot: send photos, get the result in chat",
             "Gemini Live voice in Hindi for families who prefer to talk",
             "UPI payments with automatic refunds of the 10% fee",
             "Ready-made connectors for popular hospital software (API + panel)",
             "Data residency in India (asia-south1) for real patient documents",
             "Human review by claims experts before letters go out",
             "Insurer Report Card opened up for journalists and regulators"]
    text(slide, 5.15, 1.85, 4.45, 3.4, [[("■  ", {"color": GREEN, "size": 8}), (t, {"size": 11})] for t in items],
         space_after=7)
    notes(slide, "Roadmap after the Buildathon. All demo data is synthetic today.")


def s_business(slide):
    title(slide, "Business model")
    tiers = [("Families: now", GREEN, GREEN_T,
              "₹299 work fee + a 10% advance success fee (max ₹2,999). Nothing recovered in 120 days? The 10% comes back."),
             ("Small hospitals: next", BLUE, BLUE_T,
              "₹5,000 to ₹15,000 a month for the pre-check panel in their billing software: every claim checked before it is sent."),
             ("Employers: later", AMBER, AMBER_T,
              "Claims help as an employee benefit on group health policies, priced per employee.")]
    x = 0.4
    for head, col, tint, body in tiers:
        box(slide, x, 1.45, 2.95, 1.5, tint, None, MSO_SHAPE.ROUNDED_RECTANGLE)
        text(slide, x + 0.18, 1.56, 2.6, 1.35, [[(head, {"bold": True, "color": col, "size": 13})],
                                                [(body, {"size": 11})]], space_after=5)
        x += 3.12
    box(slide, 0.4, 3.15, 4.45, 1.65, WHITE, LINE, MSO_SHAPE.ROUNDED_RECTANGLE)
    text(slide, 0.58, 3.25, 4.1, 1.5,
         [[("Example: a ₹10,000 cut that was wrong", {"bold": True, "color": NAVY, "size": 12})],
          [("Family pays upfront: ₹299 + ₹1,000 = ", {"size": 11}), ("₹1,299", {"bold": True, "size": 11})],
          [("We win: we keep ₹1,299 (13%, vs about 21% at recovery firms)", {"size": 11})],
          [("We don't: ₹1,000 refunded, we keep ₹299", {"size": 11})]], space_after=4)
    box(slide, 5.15, 3.15, 4.45, 1.65, GREY_T, None, MSO_SHAPE.ROUNDED_RECTANGLE)
    text(slide, 5.33, 3.25, 4.1, 1.5,
         [[("Rough size (bottom-up estimates)", {"bold": True, "color": NAVY, "size": 12})],
          [("Families: 65,000 cases a year × (₹299 + 10% of ₹15,000 × 70% win rate) ≈ ₹8.8 Cr a year.", {"size": 11})],
          [("Hospitals: about 11,400 nursing homes × ₹60,000 a year ≈ ₹68 Cr a year.", {"size": 11})]], space_after=5)
    text(slide, 0.4, 4.95, 9.2, 0.25, [[("Fees exclude 18% GST. Case counts, win rate and prices are our assumptions, "
                                         "to be validated.", {"size": 8, "color": MUTED})]])
    notes(slide, "Low risk for families: only ₹299 is at stake. Hospitals are the bigger market next.")


def s_live(slide):
    title(slide, "Try the prototype")
    img = qrcode.make(LIVE_URL, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    q = slide.shapes.add_picture(buf, Inches(0.5), Inches(1.5), height=Inches(2.6))
    q.name = "QR code to the live app"
    text(slide, 0.4, 4.15, 2.8, 0.6, [[("Scan to open on your phone", {"bold": True, "color": NAVY, "size": 11})]],
         align=PP_ALIGN.CENTER)
    text(slide, 3.55, 1.45, 6.05, 0.5, [[("Live on Google Cloud Run", {"bold": True, "color": NAVY, "size": 16})]])
    text(slide, 3.55, 1.95, 6.05, 0.4, [[(LIVE_URL, {"color": BLUE, "size": 12, "link": LIVE_URL})]])
    steps = [("1", "Open the link and choose English or हिंदी."),
             ("2", "Tap \"Check my claim\" and upload a bill, settlement letter and policy, or open the DEMO tab "
                   "for 3 sample cases."),
             ("3", "Open a cut to see the rule and its source, then tap ASK and ask in Hindi or English."),
             ("4", "Tap \"Fight this cut\" for the complaint letter and dated next steps."),
             ("5", "Hospitals: open /hospital.html, pick the Deluxe room and watch the pre-check panel.")]
    y = 2.4
    for n, t in steps:
        badge(slide, 3.55, y, n, fill=GREEN, size=0.32, font_size=10)
        text(slide, 4.0, y - 0.02, 5.6, 0.5, [[(t, {"size": 11})]])
        y += 0.5
    text(slide, 3.55, 4.95, 6.05, 0.5,
         [[("Insurer Report Card (BigQuery data agent in Data Studio): ", {"bold": True, "color": NAVY, "size": 10}),
           ("open link", {"color": BLUE, "size": 10, "link": REPORT_CARD_URL}),
           (" (shown live; needs access). All data is synthetic.", {"size": 10, "color": MUTED})]])
    notes(slide, "Demo tip: open the app once before presenting so the first answer is fast.")


def main():
    prs = Presentation(str(TEMPLATE))
    s = list(prs.slides)
    s_team(s[1]); s_brief(s[2]); s_opportunities(s[3]); s_features(s[4]); s_flow(s[5]); s_wireframes(s[6])
    s_architecture(s[7]); s_tech(s[8]); s_cost(s[9]); s_snapshots(s[10]); s_performance(s[11]); s_future(s[12])
    s_business(s[13]); s_live(s[14])
    delete_slide(prs, 0)  # the template's "how to download" instruction slide
    prs.save(str(OUT))
    print("saved", OUT)


if __name__ == "__main__":
    main()
