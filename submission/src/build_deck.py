"""Build the 7-slide submission deck on the official Airtel SYNC template.
python submission/src/build_deck.py "Submission Template_Sync.pptx" "Team Name" "College"
"""
import copy
import io
import sys
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parents[2]
SHOTS = ROOT / "docs" / "screenshots"
TEMPLATE, TEAM, COLLEGE = sys.argv[1], sys.argv[2], sys.argv[3]
REPO = "github.com/AjinkyaHon9504/Airtel_sync_aj"
VIDEO = sys.argv[4] if len(sys.argv) > 4 else "https://" + REPO + "#demo"

RED, INK, MUT, LINE, BG2, OK, WARN, REV, BAD, WHITE = (RGBColor.from_string(x) for x in
    ["D71920", "16181D", "5B6474", "E3E6EA", "F6F7F9", "12805C", "B54708", "6941C6", "B42318", "FFFFFF"])
PINK = RGBColor.from_string("FFF3F2")
FONT = "Arial"

prs = Presentation(TEMPLATE)
W, H = prs.slide_width, prs.slide_height
cover, inner = prs.slides[0], prs.slides[1]
inner_pic = next(s for s in inner.shapes if s.shape_type == 13)
INNER_BLOB = inner_pic.image.blob


def new_slide():
    s = prs.slides.add_slide(inner.slide_layout)
    for ph in list(s.placeholders):
        ph._element.getparent().remove(ph._element)
    s.shapes.add_picture(io.BytesIO(INNER_BLOB), 0, 0, W, H)
    return s


def text(s, x, y, w, h, runs, size=12, color=INK, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, spacing=None, name=None):
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    paras = runs if isinstance(runs, list) else [runs]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if spacing:
            p.space_after = Pt(spacing)
        segs = para if isinstance(para, list) else [para]
        for seg in segs:
            t, o = (seg, {}) if isinstance(seg, str) else seg
            r = p.add_run()
            r.text = t
            f = r.font
            f.name = FONT
            f.size = Pt(o.get("size", size))
            f.bold = o.get("bold", bold)
            f.italic = o.get("italic", False)
            f.color.rgb = o.get("color", color)
    return tb


def box(s, x, y, w, h, fill=WHITE, line=LINE, radius=True, shadow=False):
    shp = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    if radius:
        shp.adjustments[0] = 0.08
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(0.75)
    if not shadow:
        shp.shadow.inherit = False
    shp.text_frame.text = ""
    return shp


def title(s, t, sub=None):
    text(s, 0.45, 0.6, 9.1, 0.42, t, size=21, bold=True, name="Title")
    if sub:
        text(s, 0.45, 1.03, 9.1, 0.3, sub, size=10.5, color=MUT, name="Subtitle")


def footer(s, n):
    text(s, 0.45, 5.2, 4, 0.2, f"Udyam Express · {TEAM}  ·  {n}", size=8, color=MUT)


def pic(s, path, x, y, w=None, h=None, border=True):
    p = s.shapes.add_picture(str(path), Inches(x), Inches(y), Inches(w) if w else None, Inches(h) if h else None)
    if border:
        p.line.color.rgb = LINE
        p.line.width = Pt(0.75)
    return p


def table(s, x, y, w, rows, colw, size=9, header_fill=INK, row_h=0.28, first_bold=True, fills=None):
    shp = s.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w), Inches(row_h * len(rows)))
    tbl = shp.table
    tbl.first_row = True
    for i, cw in enumerate(colw):
        tbl.columns[i].width = Inches(cw)
    for r, row in enumerate(rows):
        tbl.rows[r].height = Inches(row_h)
        for c, val in enumerate(row):
            cell = tbl.cell(r, c)
            cell.margin_left = cell.margin_right = Inches(0.06)
            cell.margin_top = cell.margin_bottom = Inches(0.03)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            cell.fill.fore_color.rgb = header_fill if r == 0 else (fills[r][c] if fills and fills[r] and fills[r][c] else (WHITE if r % 2 else BG2))
            tf = cell.text_frame
            tf.word_wrap = True
            parts = val if isinstance(val, list) else [val]
            for k, part in enumerate(parts):
                p = tf.paragraphs[0] if k == 0 else tf.add_paragraph()
                t, o = (part, {}) if isinstance(part, str) else part
                run = p.add_run()
                run.text = t
                run.font.name = FONT
                run.font.size = Pt(o.get("size", size))
                run.font.bold = o.get("bold", r == 0 or (first_bold and c == 0))
                run.font.color.rgb = o.get("color", WHITE if r == 0 else INK)
    return shp


def stat(s, x, y, w, big, small, color=RED, bigsize=22, h=0.82):
    box(s, x, y, w, h, fill=WHITE)
    text(s, x + 0.12, y + 0.08, w - 0.2, 0.4, big, size=bigsize, bold=True, color=color)
    text(s, x + 0.12, y + 0.5, w - 0.2, 0.3, small, size=8.5, color=MUT)


# =================================================================== 1. COVER
s = cover
text(s, 0.55, 3.0, 4.4, 0.25, f"{TEAM.upper()}  ·  {COLLEGE}", size=10, bold=True, color=RGBColor.from_string("FF5A5F"))
text(s, 0.55, 3.27, 4.6, 0.5, "Udyam Express", size=30, bold=True, color=WHITE)
text(s, 0.55, 3.82, 4.2, 0.45, "A small business discovers, buys, verifies and tracks its Accel Business bundle in one sitting: on a phone, in its own language.", size=10.5, color=RGBColor.from_string("E4E7EC"))
chips = ["Advisor · OneBill · Smart KYC · Tracker", "12/12 KYC  ·  0 rule breaks on 5,000 profiles", "Lead→activation 7.4% → 13% (replayed)"]
yy = 4.37
for c in chips[:2]:
    pass
b1 = box(s, 0.55, 4.38, 1.85, 0.34, fill=RED, line=None)
text(s, 0.55, 4.38, 1.85, 0.34, "▶  Demo video (≤3 min)", size=10, bold=True, color=WHITE, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE).click_action.hyperlink.address = VIDEO
b2 = box(s, 2.5, 4.38, 2.35, 0.34, fill=WHITE, line=None)
text(s, 2.5, 4.38, 2.35, 0.34, "GitHub: AjinkyaHon9504/Airtel_sync_aj", size=8.5, bold=True, color=INK, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE).click_action.hyperlink.address = "https://" + REPO
text(s, 0.55, 4.82, 4.6, 0.25, "Airtel SYNC 2026  ·  Enterprise Track A: Project Udyam Digital", size=8.5, color=RGBColor.from_string("C9CDD4"))
s.notes_slide.notes_text_frame.text = "Udyam Express: one-sitting digital onboarding for Accel Business SMB customers. Demo video and code linked on this slide."

# =================================================================== 2. PROBLEM
s = new_slide()
title(s, "93 of every 100 interested businesses are never switched on", "Accel's Apr–Jun 2026 data (5,000 SMB leads): the demand exists; the sales journey loses it.")
cd = CategoryChartData()
stages = ["Lead", "Contacted", "Needs assessed", "Quote accepted", "KYC complete", "Activated"]
vals = [5000, 3406, 1974, 861, 588, 368]
cd.categories = list(reversed(stages))
cd.add_series("Leads", list(reversed(vals)))
gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(0.4), Inches(1.38), Inches(4.3), Inches(2.45), cd)
ch = gf.chart
ch.has_legend = False
ch.has_title = False
ch.plots[0].gap_width = 45
ch.plots[0].series[0].format.fill.solid()
ch.plots[0].series[0].format.fill.fore_color.rgb = RED
pl = ch.plots[0]
pl.has_data_labels = True
pl.data_labels.font.size = Pt(9)
pl.data_labels.font.name = FONT
pl.data_labels.font.color.rgb = INK
pl.data_labels.number_format = "#,##0"
pl.data_labels.number_format_is_linked = False
pl.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
ch.value_axis.visible = False
ch.value_axis.has_major_gridlines = False
ch.value_axis.maximum_scale = 6200
ch.category_axis.tick_labels.font.size = Pt(9)
ch.category_axis.tick_labels.font.name = FONT
ch.category_axis.tick_labels.font.color.rgb = MUT
ch.category_axis.format.line.fill.background()
text(s, 0.45, 3.83, 4.2, 0.22, "Steepest leak: needs assessed → quote accepted (only 44% pass)", size=8.5, color=MUT, bold=True)
for i, (big, small) in enumerate([("17.6 days", "lead → live today"), ("3.0", "times each customer chases status"), ("₹15,053", "spent to win one customer"), ("9.6% vs 2.0%", "activation with vs without GSTIN")]):
    stat(s, 4.95 + (i % 2) * 2.3, 1.38 + (i // 2) * 0.92, 2.2, big, small, bigsize=19)
box(s, 4.95, 3.24, 4.5, 0.83, fill=PINK, line=None)
text(s, 5.07, 3.3, 4.3, 0.75, [[("48 of 368", {"bold": True, "color": RED}), " activations were sold in breach of catalogue rules (tier, size, GST, dependencies). ",
                              ("Micro retail", {"bold": True}), " is 55% of leads but converts at 4.1% with ₹20k acquisition cost per ₹2.5k/month customer: field sales can't serve it profitably."]], size=9)
box(s, 0.45, 4.15, 9.0, 0.93, fill=WHITE)
text(s, 0.58, 4.2, 8.8, 0.22, [[("52% of the 4,632 drops are process friction, which a digital journey removes", {"bold": True}), ("  →  the feature that fixes each", {"color": MUT})]], size=10)
cols = [("827", "no time for / no visit", "Self-serve advisor"), ("385", "quote slow or complex", "Instant OneBill"),
        ("273", "paperwork, signatory away", "Smart KYC + e-sign"), ("139", "install delay, no fibre", "AirFiber + tracker"), ("805", "unreachable after 3 calls", "WhatsApp-first contact")]
for i, (n, why, fix) in enumerate(cols):
    x = 0.58 + i * 1.77
    text(s, x, 4.45, 1.7, 0.6, [[(n, {"bold": True, "size": 14, "color": RED}), ("  " + why, {"size": 8, "color": MUT})], [("→ " + fix, {"size": 8.5, "bold": True})]], size=9, spacing=2)
footer(s, 2)

# =================================================================== 3. SOLUTION
s = new_slide()
title(s, "Built and working: from hello to a verified order in one sitting", "Every screen below is the running prototype (phone-first web app; the same API serves WhatsApp and a partner tablet).")
crops = [("crop-advisor.png", "1 · Discover", "Chat or speak in Hindi, English or Hinglish (+6 languages via Gemini). One message or a GSTIN fills the profile."),
         ("crop-quote.png", "2 · OneBill", "Essential / Recommended / Complete on one monthly line. Add-ons toggle and re-price live; blocked items say why."),
         ("crop-kyc.png", "3 · Verify", "Consent first, then OCR on our server + GST/Udyam registry checks: 4 clear verdicts, each with a fix."),
         ("crop-tracker.png", "4 · Track", "Six stages and an ETA per product from install days, with WhatsApp updates instead of chase calls.")]
for i, (f, h, d) in enumerate(crops):
    x = 0.45 + i * 2.29
    pic(s, SHOTS / f, x + 0.33, 1.38, h=2.55)
    text(s, x, 3.98, 2.15, 0.22, h, size=11, bold=True, color=RED)
    text(s, x, 4.2, 2.15, 0.55, d, size=8.5, color=INK)
box(s, 0.45, 4.78, 9.0, 0.34, fill=INK, line=None)
text(s, 0.58, 4.78, 8.8, 0.34, [[("The AI talks, the rules engine decides.", {"bold": True, "color": WHITE}), ("  Products, eligibility and every ₹ come only from the catalogue; the LLM never sees documents.", {"color": RGBColor.from_string("D0D5DD")})]], size=9, anchor=MSO_ANCHOR.MIDDLE)
footer(s, 3)

# =================================================================== 4. KYC + PRIVACY
s = new_slide()
title(s, "Smart KYC: all 12 specimen applicants judged correctly", "On-server OCR (deskew, blur gate, GSTIN repair + checksum) → GST & Udyam registries → name, date and signatory checks.")
V = {"R": ("Rejected", BAD), "M": ("Manual review", REV), "A": ("Needs action", WARN), "V": ("Verified", OK)}
rows = [["Applicant", "What we found", "Verdict"],
        ["K01", "GSTIN cancelled in registry + Udyam number blank", "R"],
        ["K07", "Legal name edited ('Shri' vs 'Neelgiri Physio Clinic')", "M"],
        ["K04", "GST certificate blurred (sharpness 1 vs ≥60): no guessing", "A"],
        ["K05", "Udyam certificate missing: fetch from registry", "A"],
        ["K06", "GSTIN check digit fails (one digit altered)", "A"],
        ["K11", "Electricity bill 257 days old (limit 90)", "A"],
        ["K02 · K08 · K10", "Tilted scan straightened; O/0, I/T, J/I OCR misreads repaired via checksum", "V"],
        ["K03 · K09 · K12", "Clean", "V"]]
fills = [None] + [[None, None, PINK] for _ in rows[1:]]
disp = [rows[0]] + [[r[0], r[1], [(V[r[2]][0], {"bold": True, "color": V[r[2]][1]})]] for r in rows[1:]]
table(s, 0.45, 1.42, 5.55, disp, [1.05, 3.4, 1.1], size=8.5, row_h=0.36)
pic(s, SHOTS / "crop-consent.png", 6.25, 1.42, h=2.0)
pic(s, SHOTS / "04-kyc-k07.png", 7.4, 1.42, w=2.05, border=True) if False else None
box(s, 7.38, 1.42, 2.07, 2.0, fill=BG2, line=None)
text(s, 7.48, 1.5, 1.9, 1.9, [[("4 verdicts, not 2", {"bold": True, "size": 10})],
                               [("Verified", {"bold": True, "color": OK}), " → e-sign now"], [("Needs action", {"bold": True, "color": WARN}), " → owner fixes in-app"],
                               [("Manual review", {"bold": True, "color": REV}), " → specialist in 4 h"], [("Rejected", {"bold": True, "color": BAD}), " → registry problem"]], size=8.5, spacing=3)
box(s, 6.25, 3.55, 3.2, 1.55, fill=PINK, line=None)
text(s, 6.37, 3.62, 3.0, 1.45, [[("DPDP Act 2023 by design", {"bold": True, "size": 10, "color": RED})],
                               "• Consent per purpose before upload; hash-chained ledger; 1-tap withdraw & erase",
                               "• Documents never sent to an AI model",
                               "• Aadhaar / PAN redacted from chat; IDs masked in UI & logs",
                               "• Images purged after verdict (≤30 days in prod)"], size=8, spacing=1.5)
footer(s, 4)

# =================================================================== 5. SEGMENTS & CHANNELS
s = new_slide()
title(s, "Who first, with what bundle, through which channel", "Bundles are the advisor's live output for a typical business (catalogue midpoint, ex-GST). Priority = digital fit × economics.")
rows = [["#", "Segment (share of leads)", "Today: conversion · median bundle · churn · cost/activation", "Recommended bundle (typical business)", "₹/month · term", "Channel"],
        ["1", ["Professional offices (25%)", ("clinic, CA firm, 10 staff", {"bold": False, "color": MUT, "size": 8})], "11.1% · ₹6,575 · 13.8% · ₹10.7k\n86% have GSTIN → instant KYC", "Fibre 300 + 4G/5G failover + 4 business SIMs + email, security & backup for 10", "₹8,213 · 12 mo", "Self-serve web/voice"],
        ["2", ["Micro retail (55%)", ("kirana, salon, pharmacy", {"bold": False, "color": MUT, "size": 8})], "4.1% · ₹2,470 · 22.7% · ₹20.0k\nvery price-sensitive", "Fibre 100 (AirFiber if no fibre) + UPI billing tablet + 2 SIMs; Essential from ₹1,848", "₹2,546 · 12 mo", "WhatsApp + partner-assisted"],
        ["3", ["Multi-site (15%)", ("restaurant chain, 5 outlets", {"bold": False, "color": MUT, "size": 8})], "11.0% · ₹28,080 · 10.8% · ₹15.6k", "Fibre 300 + failover + POS per outlet, 20 cloud CCTV, 10 SIMs, one bill; SD-WAN in Complete", "₹26,705 · 24 mo", "Advisor qualifies → field rep"],
        ["4", ["Manufacturers (5%)", ("auto-parts unit, 45 staff", {"bold": False, "color": MUT, "size": 8})], "12.8% · ₹15,910 · 8.1% · ₹15.3k", "20 Mbps leased line (99.5% SLA) + 8 machine-monitoring IoT kits + SIMs, email & security", "₹26,444 · 24 mo", "Field sales + site survey"]]
table(s, 0.45, 1.38, 9.1, rows, [0.3, 1.6, 2.1, 2.85, 1.05, 1.2], size=8.3, row_h=0.5)
box(s, 0.45, 4.05, 9.1, 1.05, fill=WHITE)
text(s, 0.58, 4.1, 8.9, 0.22, [[("Field force & partners: the digital journey feeds them, it doesn't replace them", {"bold": True, "size": 10})]], size=10)
for i, (h, d) in enumerate([("Partners get warm leads", "Chats the bot can't close (tier-3 towns, >10 sites, custom needs) arrive with the chat summary, ranked by win-back score; commission on close."),
                            ("Assisted mode", "Same app on a partner's tablet for owners who prefer a person: KYC done on the spot, partner credited."),
                            ("Reps focus on big tickets", "Multi-site and factories (fastest payback) go to field sales pre-qualified; reps keep credit for advisor-sourced deals.")]):
    text(s, 0.58 + i * 2.97, 4.37, 2.85, 0.72, [[(h, {"bold": True, "color": RED, "size": 9})], [(d, {"size": 8})]], size=8)
footer(s, 5)

# =================================================================== 6. METRICS & IMPACT
s = new_slide()
title(s, "Five metrics, conservative targets: the 5,000 leads replayed", "Each drop reason is won back only by the feature that removes it, at cautious 10–40% rates (code: app/backoffice.py · impact()).")
rows = [["Metric that matters", "Today", "Replayed", "Pilot target"],
        ["Lead → activation", "7.36%", "13.0%", "≥ 12%"],
        ["Days lead → live", "17.6", "7.3", "≤ 8"],
        ["Cost per activation", "₹15,053", "₹8,447", "≤ ₹9,000"],
        ["Status chase calls / customer", "3.0", "tracker", "≤ 1.0"],
        ["6-month churn", "15.2%", "—", "≤ 12%"]]
fills = [None] + [[None, None, None, PINK] for _ in range(5)]
table(s, 0.45, 1.38, 4.7, rows, [1.95, 0.85, 0.95, 0.95], size=9.5, row_h=0.36, fills=fills)
text(s, 0.45, 3.6, 4.7, 0.6, [[("Why these are reachable: ", {"bold": True}), "quote, KYC and e-sign happen in one sitting, so only install time is left (AirFiber 2 days, fibre 5, leased line 21). In the data churn rises with chase calls (1 call → 5.9%, 5 calls → 27.9%); the tracker removes the calls."]], size=8.3, color=INK)
cd = CategoryChartData()
feat = [("Instant OneBill quote", 66), ("Self-serve advisor", 54), ("Smart KYC", 51), ("AirFiber fallback + tracker", 46), ("Essential tier", 18), ("Mobile-only path", 16), ("Remote e-sign", 13), ("UPI AutoPay", 11), ("WhatsApp-first contact", 9)]
cd.categories = [f for f, _ in reversed(feat)]
cd.add_series("Activations won back / quarter", [v for _, v in reversed(feat)])
gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(5.35), Inches(1.6), Inches(4.15), Inches(2.6), cd)
ch = gf.chart
ch.has_legend = False
ch.has_title = False
pl = ch.plots[0]
pl.gap_width = 40
pl.series[0].format.fill.solid()
pl.series[0].format.fill.fore_color.rgb = RED
pl.has_data_labels = True
pl.data_labels.font.size = Pt(8.5)
pl.data_labels.font.name = FONT
pl.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
ch.value_axis.visible = False
ch.value_axis.has_major_gridlines = False
ch.value_axis.maximum_scale = 80
ch.category_axis.tick_labels.font.size = Pt(8)
ch.category_axis.tick_labels.font.name = FONT
ch.category_axis.tick_labels.font.color.rgb = MUT
ch.category_axis.format.line.fill.background()
text(s, 5.4, 1.38, 4.1, 0.22, "Extra activations per quarter, by feature", size=9.5, bold=True)
for i, (big, small) in enumerate([("+283", "activations a quarter (1.8×)"), ("≈ ₹9.4 Cr", "added ARR run-rate after year 1"), ("48 → 0", "rule-breaking sales")]):
    stat(s, 0.45 + i * 3.05, 4.22, 2.95, big, small, bigsize=20, h=0.74)
text(s, 2.3, 5.21, 5.9, 0.18, "₹9.4 Cr = 283 × 4 quarters × ₹6,900 median bundle × 12 months. Cost model: −30% field effort on self-served sources, +₹40/lead platform cost (AI, OCR, hosting).", size=6.5, color=MUT)
footer_y = None

# =================================================================== 7. ARCHITECTURE / EVIDENCE / ROLLOUT / RISKS
s = new_slide()
title(s, "Built to ship: architecture, evidence, rollout and risks", "Runs offline at ₹0 (Gemini optional); registries, DigiLocker, e-Sign and UPI AutoPay sit behind production-shaped interfaces.")
pic(s, ROOT / "submission" / "src" / "architecture.png", 0.45, 1.38, w=5.25)
text(s, 0.45, 4.36, 5.25, 0.2, "Evidence (run pytest / tests/bench_public.py)", size=9.5, bold=True)
ev = [("27", "automated tests"), ("0", "rule breaks across 5,000 profiles × 3 tiers"), ("12/12", "KYC specimen verdicts"), ("75%", "of 268 unseen scenarios written by other teams"), ("0.72", "AUC lead score, June hold-out (2.2× lift)")]
for i, (n, d) in enumerate(ev):
    x = 0.45 + i * 1.06
    text(s, x, 4.58, 1.0, 0.55, [[(n, {"bold": True, "size": 13, "color": RED})], [(d, {"size": 7, "color": MUT})]], size=8)
rows = [["Phase", "Rollout plan"], ["Weeks 0–8", "Pilot: professional offices in Pune, Delhi, Jaipur, Kochi; web + WhatsApp; 20 partners"],
        ["Weeks 9–16", "Micro retail via WhatsApp + partner-assisted mode; 6 more Indian languages live"],
        ["Months 5–12", "All tier-1/2 cities; multi-site and factories qualified by advisor for field sales"]]
table(s, 5.9, 1.38, 3.6, rows, [0.95, 2.65], size=7.8, row_h=0.42)
rows = [["Risk", "Mitigation"], ["Install capacity", "Launch gated on crews; AirFiber (2 days) absorbs fibre backlog; SLA alerts"],
        ["Channel conflict", "Partners get leads + commission; reps keep credit"],
        ["Wrong advice / AI error", "LLM can't set products or prices; numbers checked; hand-off rules"],
        ["KYC fraud", "Registry + checksum + edit detection → manual review queue"]]
table(s, 5.9, 3.2, 3.6, rows, [1.1, 2.5], size=7.8, row_h=0.37)
footer(s, 7)

# re-add footers that were skipped
footer(prs.slides[-2], 6)

# drop the template's blank content slide (we cloned its background)
sldIdLst = prs.slides._sldIdLst
for sid in list(sldIdLst):
    if prs.slides.get(int(sid.get("id"))) is inner if hasattr(prs.slides, "get") else False:
        pass
ids = list(sldIdLst)
rid = ids[1].get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
prs.part.drop_rel(rid)
sldIdLst.remove(ids[1])

out = ROOT / "submission" / "UdyamExpress_Submission.pptx"
prs.save(out)
print("saved", out, len(prs.slides), "slides")
