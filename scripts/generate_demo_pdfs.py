from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, Table, TableStyle


OUT = Path(__file__).resolve().parents[1] / "public" / "demo"
NAVY = HexColor("#0B1B2A")
CYAN = HexColor("#14B8C8")
INK = HexColor("#172833")
MUTED = HexColor("#607581")
PALE = HexColor("#EAF4F6")
AMBER = HexColor("#D48A16")


def text_style(size=10, color=INK, leading=15, bold=False):
    return ParagraphStyle(
        "body",
        fontName="Helvetica-Bold" if bold else "Helvetica",
        fontSize=size,
        leading=leading,
        textColor=color,
        alignment=TA_LEFT,
    )


def header(canvas: Canvas, version: str, page: int):
    width, height = LETTER
    canvas.setFillColor(NAVY)
    canvas.rect(0, height - 0.7 * inch, width, 0.7 * inch, fill=1, stroke=0)
    canvas.setFillColor(CYAN)
    canvas.rect(0, height - 0.72 * inch, width, 0.02 * inch, fill=1, stroke=0)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.setFillColor(HexColor("#FFFFFF"))
    canvas.drawString(0.62 * inch, height - 0.42 * inch, "AURORA FAMILY OFFICE")
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(HexColor("#A8C0CB"))
    canvas.drawRightString(width - 0.62 * inch, height - 0.42 * inch, f"INVESTMENT POLICY STATEMENT  /  {version}")
    canvas.setStrokeColor(HexColor("#CBD9DE"))
    canvas.line(0.62 * inch, 0.55 * inch, width - 0.62 * inch, 0.55 * inch)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.62 * inch, 0.34 * inch, "Synthetic document for the NodeWitness product demonstration")
    canvas.drawRightString(width - 0.62 * inch, 0.34 * inch, f"Page {page} of 3")


def cover(canvas: Canvas, version: str, effective: str, summary: str):
    width, height = LETTER
    header(canvas, version, 1)
    canvas.setFillColor(NAVY)
    canvas.roundRect(0.62 * inch, height - 3.12 * inch, width - 1.24 * inch, 1.76 * inch, 4, fill=1, stroke=0)
    canvas.setFillColor(CYAN)
    canvas.rect(0.62 * inch, height - 1.36 * inch, 1.22 * inch, 0.055 * inch, fill=1, stroke=0)
    canvas.setFillColor(HexColor("#FFFFFF"))
    canvas.setFont("Helvetica-Bold", 25)
    canvas.drawString(0.92 * inch, height - 2.06 * inch, "Investment Policy")
    canvas.drawString(0.92 * inch, height - 2.45 * inch, "Statement")
    canvas.setFont("Helvetica", 10)
    canvas.setFillColor(HexColor("#A8C0CB"))
    canvas.drawString(0.92 * inch, height - 2.78 * inch, "Client mandate and portfolio governance limits")

    data = [
        [Paragraph("DOCUMENT VERSION", text_style(8, MUTED, 10, True)), Paragraph(version, text_style(12, INK, 14, True))],
        [Paragraph("EFFECTIVE DATE", text_style(8, MUTED, 10, True)), Paragraph(effective, text_style(12, INK, 14, True))],
        [Paragraph("CLIENT", text_style(8, MUTED, 10, True)), Paragraph("Aurora Family Office", text_style(12, INK, 14, True))],
        [Paragraph("STATUS", text_style(8, MUTED, 10, True)), Paragraph("Approved for demonstration", text_style(12, INK, 14, True))],
    ]
    table = Table(data, colWidths=[1.65 * inch, 4.55 * inch], rowHeights=[0.48 * inch] * 4)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), HexColor("#F5F8F9")),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#D7E2E6")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
    ]))
    table.wrapOn(canvas, width, height)
    table.drawOn(canvas, 0.92 * inch, height - 5.5 * inch)

    canvas.setFillColor(INK)
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawString(0.92 * inch, height - 6.05 * inch, "Mandate summary")
    paragraph = Paragraph(summary, text_style(10, MUTED, 15))
    paragraph.wrapOn(canvas, 6.0 * inch, 0.9 * inch)
    paragraph.drawOn(canvas, 0.92 * inch, height - 6.8 * inch)


def rule_page(canvas: Canvas, version: str, threshold: str, scope: str, rule: str, detail: str):
    width, height = LETTER
    header(canvas, version, 2)
    canvas.setFillColor(INK)
    canvas.setFont("Helvetica-Bold", 19)
    canvas.drawString(0.72 * inch, height - 1.25 * inch, "4.2 Cryptocurrency exposure")
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.72 * inch, height - 1.52 * inch, "Binding client mandate - reviewed quarterly and on every source revision")

    canvas.setFillColor(PALE)
    canvas.roundRect(0.72 * inch, height - 3.34 * inch, width - 1.44 * inch, 1.42 * inch, 4, fill=1, stroke=0)
    canvas.setFillColor(CYAN)
    canvas.rect(0.72 * inch, height - 3.34 * inch, 0.055 * inch, 1.42 * inch, fill=1, stroke=0)
    canvas.setFillColor(NAVY)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(0.98 * inch, height - 2.25 * inch, "MANDATE RULE")
    paragraph = Paragraph(rule, text_style(13, INK, 19, True))
    paragraph.wrapOn(canvas, width - 2.1 * inch, 0.85 * inch)
    paragraph.drawOn(canvas, 0.98 * inch, height - 3.05 * inch)

    data = [
        [Paragraph("MAXIMUM", text_style(8, MUTED, 10, True)), Paragraph(threshold, text_style(17, NAVY, 20, True))],
        [Paragraph("MEASUREMENT SCOPE", text_style(8, MUTED, 10, True)), Paragraph(scope, text_style(10, INK, 14, True))],
        [Paragraph("REVIEW TRIGGER", text_style(8, MUTED, 10, True)), Paragraph("Any measured exposure above the maximum requires compliance review.", text_style(10, INK, 14))],
    ]
    table = Table(data, colWidths=[1.65 * inch, 4.65 * inch], rowHeights=[0.62 * inch, 0.72 * inch, 0.72 * inch])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#CFDDE2")),
        ("BACKGROUND", (0, 0), (0, -1), HexColor("#F5F8F9")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    table.wrapOn(canvas, width, height)
    table.drawOn(canvas, 0.72 * inch, height - 5.75 * inch)

    canvas.setFont("Helvetica-Bold", 11)
    canvas.setFillColor(INK)
    canvas.drawString(0.72 * inch, height - 6.25 * inch, "Interpretation")
    paragraph = Paragraph(detail, text_style(10, MUTED, 15))
    paragraph.wrapOn(canvas, width - 1.44 * inch, 1.0 * inch)
    paragraph.drawOn(canvas, 0.72 * inch, height - 7.15 * inch)


def appendix(canvas: Canvas, version: str):
    width, height = LETTER
    header(canvas, version, 3)
    canvas.setFillColor(INK)
    canvas.setFont("Helvetica-Bold", 19)
    canvas.drawString(0.72 * inch, height - 1.25 * inch, "Monitoring appendix")
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.72 * inch, height - 1.52 * inch, "Synthetic portfolio evidence snapshot - 18 July 2026")
    rows = [
        ["Measure", "Observed", "Mandate reference", "State"],
        ["Direct cryptocurrency exposure", "2.0%", "See section 4.2", "Observed"],
        ["Indirect / look-through crypto", "6.2%", "See section 4.2", "Observed"],
        ["Total cryptocurrency exposure", "8.2%", "See section 4.2", "Calculated"],
        ["Largest issuer exposure", "18.7%", "Maximum 20.0%", "Near limit"],
        ["Liquid allocation", "6.4%", "Minimum 5.0%", "Pass"],
    ]
    table = Table(rows, colWidths=[2.35 * inch, 0.9 * inch, 1.8 * inch, 1.05 * inch], rowHeights=[0.44 * inch] + [0.55 * inch] * 5)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#FFFFFF")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 1), (-1, -1), INK),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#F6F9FA"), HexColor("#FFFFFF")]),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#CFDDE2")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (3, 4), (3, 4), AMBER),
        ("TEXTCOLOR", (3, 5), (3, 5), HexColor("#16865B")),
    ]))
    table.wrapOn(canvas, width, height)
    table.drawOn(canvas, 0.72 * inch, height - 5.15 * inch)

    canvas.setFillColor(PALE)
    canvas.roundRect(0.72 * inch, height - 6.52 * inch, width - 1.44 * inch, 0.82 * inch, 4, fill=1, stroke=0)
    canvas.setFillColor(NAVY)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(0.94 * inch, height - 6.02 * inch, "Evidence note")
    note = Paragraph("These values are synthetic and are included to provide stable, reviewable evidence for the NodeWitness demonstration. They are not client records and must not be used for investment decisions.", text_style(9, MUTED, 13))
    note.wrapOn(canvas, width - 2.0 * inch, 0.5 * inch)
    note.drawOn(canvas, 0.94 * inch, height - 6.43 * inch)


def make_pdf(filename: str, version: str, effective: str, threshold: str, scope: str, rule: str, detail: str, summary: str):
    OUT.mkdir(parents=True, exist_ok=True)
    canvas = Canvas(str(OUT / filename), pagesize=LETTER, pageCompression=1)
    canvas.setTitle(f"Aurora Family Office Investment Policy Statement - {version}")
    canvas.setAuthor("NodeWitness synthetic demo")
    cover(canvas, version, effective, summary)
    canvas.showPage()
    rule_page(canvas, version, threshold, scope, rule, detail)
    canvas.showPage()
    appendix(canvas, version)
    canvas.save()


make_pdf(
    "aurora-ips-v1.pdf",
    "IPS v1",
    "14 July 2026",
    "10.0%",
    "Direct cryptocurrency holdings only",
    "Direct cryptocurrency exposure may not exceed 10% of portfolio market value.",
    "Direct exposure includes cryptocurrency tokens and directly held digital assets. Exposure held through pooled funds, ETFs, or derivatives is outside the measurement scope for this version.",
    "This statement defines the approved investment constraints used by Aurora Family Office. Compliance monitoring must compare current holdings with each binding limit and preserve cited source evidence.",
)

make_pdf(
    "aurora-ips-v2.pdf",
    "IPS v2",
    "18 July 2026",
    "5.0%",
    "Direct holdings plus look-through exposure",
    "Total cryptocurrency exposure may not exceed 5%. Total exposure includes direct holdings and look-through exposure through funds, ETFs, and derivatives.",
    "Look-through exposure must be included whenever the underlying cryptocurrency exposure is available or can be reasonably measured. A breach requires human compliance review before any remediation or communication is executed.",
    "This revised statement tightens the cryptocurrency maximum and expands the measurement scope. Monitoring systems must identify the semantic change, re-evaluate affected controls, and preserve unaffected check history.",
)
