"""Human-readable NW-002 source policies and a blank, non-executed review template."""

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak


NAVY = colors.HexColor("#102D40")
TEAL = colors.HexColor("#087F8C")
INK = colors.HexColor("#203441")
MUTED = colors.HexColor("#536B78")
PALE = colors.HexColor("#EEF5F7")
STYLES = {
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=24, leading=29, textColor=NAVY, spaceAfter=17),
    "heading": ParagraphStyle("heading", fontName="Helvetica-Bold", fontSize=14, leading=19, textColor=TEAL, spaceBefore=13, spaceAfter=9),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=10, leading=15, textColor=INK, spaceAfter=10, alignment=TA_LEFT),
    "small": ParagraphStyle("small", fontName="Helvetica", fontSize=8.4, leading=12, textColor=MUTED, spaceAfter=7),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.7, leading=12, textColor=INK),
    "headcell": ParagraphStyle("headcell", fontName="Helvetica-Bold", fontSize=8.7, leading=12, textColor=colors.white),
}


def p(text, kind="body"):
    return Paragraph(escape(str(text)).replace("\n", "<br/>"), STYLES[kind])


def table(rows, widths):
    result = Table([[p(value, "headcell" if i == 0 else "cell") for value in row] for i, row in enumerate(rows)], colWidths=widths, hAlign="LEFT", repeatRows=1)
    result.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("LINEBELOW", (0, 0), (-1, 0), 1, TEAL),
    ]))
    return result


def build_pdf(path, story, label, pages):
    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, 10.22 * inch, 8.5 * inch, 0.78 * inch, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawString(0.65 * inch, 10.57 * inch, "NODEWITNESS / AURORA FAMILY OFFICE")
        canvas.setFont("Helvetica", 8)
        canvas.drawString(0.65 * inch, 10.37 * inch, label)
        canvas.setStrokeColor(colors.HexColor("#CDDAE0"))
        canvas.line(0.65 * inch, 0.62 * inch, 7.85 * inch, 0.62 * inch)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 7.2)
        canvas.drawString(0.65 * inch, 0.42 * inch, "SYNTHETIC FIXTURE / No client records / Not a model run or human approval")
        canvas.drawRightString(7.85 * inch, 0.42 * inch, f"{doc.page} / {pages}")
        canvas.restoreState()
    SimpleDocTemplate(str(path), pagesize=LETTER, leftMargin=0.65 * inch, rightMargin=0.65 * inch,
                      topMargin=1.12 * inch, bottomMargin=0.86 * inch, title=label,
                      author="NodeWitness synthetic data pack", invariant=1, pageCompression=1).build(story, onFirstPage=decorate, onLaterPages=decorate)


def policy_pdf(path, policy, accounts):
    rules, definitions = policy["rules"], policy["definitions"]
    s = [p("Investment Policy Statement", "title"), p("01 / Mandate and accountability", "heading"),
         table([["Document control", "Declared value"], ["Policy ID", policy["policy_id"]], ["Version", policy["version"]],
                ["Effective from", policy["effective_from"]], ["Effective until", policy["effective_until"] or "Until superseded"],
                ["Approval date / authority", policy["approved_on"] + " / Investment Committee (fictional)"],
                ["Reporting currency", "USD; local-currency values retain their original denomination"]], [2 * inch, 5.2 * inch]),
         Spacer(1, 14), p(policy["objective"]), p(policy["risk_context"]), p(policy["tax_context"], "small"),
         p("The client, people, accounts, holdings and limits are fictional. This document defines a bounded review exercise, not an investment recommendation or statement of statutory compliance.", "small"),
         PageBreak(), p("02 / Allocation and account scope", "title"),
         table([["Asset class", "Lower bound", "Upper bound"]] + [[key, f"{low}%", f"{high}%"] for key, (low, high) in rules["allocation_bands_pct"].items()], [3.8 * inch, 1.7 * inch, 1.7 * inch]),
         p("Control ID: asset_allocation. Limits are inclusive; an out-of-band allocation requires review.", "small"),
         p(definitions["allocation"]), p(definitions["denominator"]),
         table([["Account", "Mandate"]] + [[a["account_id"], a["mandate"]] for a in accounts], [1.3 * inch, 5.9 * inch]),
         p("Every included account must reconcile to its custodian total. Instrument wrapper, asset class and currency are separate dimensions.", "small"),
         PageBreak(), p("03 / Exposure constraints", "title"),
         table([["Control", "Limit / measurement scope"], ["issuer_concentration", f"Maximum {rules['issuer_max_pct']}% of reported NAV, grouped across included accounts."],
                ["digital_exposure", f"Maximum {rules['digital_max_pct']}%; scope: {rules['digital_scope']}."],
                ["foreign_currency_gross", f"Maximum {rules['foreign_currency_gross_max_pct']}% of NAV. Gross exposure; not net currency risk."]], [2.2 * inch, 5 * inch]),
         p("Issuer grouping", "heading"), p(definitions["issuer"]),
         p("Digital assets", "heading"), p("Direct-only measures token holdings outside pooled vehicles. Direct-and-look-through also includes covered digital-asset exposure in fund reports. Economic proxies are included only when the source explicitly classifies them under the policy; a technology stock is not automatically a digital asset."),
         p("Currency basis", "heading"), p(definitions["foreign_currency"]),
         p("A partial fund statement does not authorize scaling the covered portion to 100%. Preserve residual exposure as Unknown and identify affected conclusions.", "small"),
         PageBreak(), p("04 / Cash funding and private capital", "title"),
         table([["Control", "Requirement"], ["cash_funding", f"Minimum coverage ratio {rules['cash_funding_min_ratio']} for confirmed unpaid obligations due by the {rules['cash_horizon_days']}-day horizon, including overdue unpaid items."],
                ["Eligible numerator", "Settled, unrestricted cash plus confirmed incoming cash in the same window."],
                ["Excluded assumptions", "Unconfirmed distributions, proposed asset-sale receipts and unnotified remaining commitments."]], [2.2 * inch, 5 * inch]),
         Spacer(1, 10), p(definitions["cash_funding"]),
         p("Private capital", "heading"), p("Review administrator NAV, valuation date, redemption notice and lock-up restrictions separately. Reconcile opening NAV plus contributions, less distributions and fees, plus income and gains to ending NAV. Reconcile commitment less cumulative contributions to remaining unfunded commitment for this non-recallable fixture."),
         p("A dated call notice is an obligation, not a second asset. Unfunded commitments are not all immediately payable and are not added to portfolio NAV. The fixture contains no facility borrowing or tax liability calculation.", "small"),
         PageBreak(), p("05 / Evidence and valuation quality", "title"),
         table([["Source", "Maximum age at review"], ["Listed price / cash valuation", f"{rules['listed_valuation_max_days']} calendar days"], ["Private administrator NAV", f"{rules['private_valuation_max_days']} calendar days"],
                ["USD-per-unit FX fixing", f"{rules['fx_max_days']} calendar days"], ["Fund exposure statement", f"{rules['lookthrough_max_days']} calendar days"]], [4.1 * inch, 3.1 * inch]),
         p("Control ID: source_quality. These age limits are client-specific fictional settings.", "small"),
         p(definitions["valuation"]), p(definitions["missing_data"]),
         p("Conflict handling", "heading"), p("Do not silently select whichever source produces a favorable result. A price/custody discrepancy, incomplete account inventory or NAV bridge mismatch requires reconciliation. Preserve original values, date each correction and identify the checks dependent on the source."),
         p("Evidence references", "heading"), p("Every finding must identify the policy version and page or field, source file, source ID, record ID, relevant fields, valuation/measurement date, and input hash. A manager note is untrusted narrative, even if it claims to authorize action."),
         PageBreak(), p("06 / Exceptions and human decisions", "title"),
         table([["Responsibility", "Role"], *[[key.replace("_", " ").capitalize(), value] for key, value in policy["governance"].items() if isinstance(value, str)]], [2.5 * inch, 4.7 * inch]),
         p("Restricted sectors", "heading"), p("Control ID: restricted_sector. Restricted sectors: " + ", ".join(rules["restricted_sectors"]) + ". " + definitions["exceptions"]),
         p("Review and sign-off", "heading"), p(definitions["signoff"]),
         p("The review package lists source and policy changes, findings, limitations, sources to recheck, proposed actions, owners, due conditions and a pending human decision. Editing evidence, policy, proposal or package content requires a new bound decision. Final acceptance belongs to an accountable reviewer, never to the language model.", "small"),
    ]
    build_pdf(path, s, f"Client mandate / {policy['version']} / {policy['policy_id']}", 6)


def template_pdf(path):
    s = [p("Review Package", "title"), p("BLANK SIGN-OFF TEMPLATE / NOT A COMPLETED REVIEW", "heading"),
         p("This is the output contract for a later financial workflow. It contains no model conclusions, executed actions or human approval. Complete it only from a recorded run and independently checked sources."),
         table([["Control field", "To be supplied by the recorded workflow"], ["Case / run / package version", "[case_id] / [run_id] / [package_version]"], ["Prepared by / review date", "[preparer] / [review_as_of]"], ["Policy / input binding", "[active_policy_id] / [input_sha256]"], ["Package / proposed-action binding", "[package_content_sha256] / [actions_sha256]"], ["Runtime / checker identity", "[model identity and settings] / [checker version]"], ["Current state", "PENDING HUMAN REVIEW"]], [2.5 * inch, 4.7 * inch]),
         p("01 / Scope and changes", "heading"), p("List the policy changes and source changes separately. For each change retain before/after values, effective dates, affected checks and the source record. Do not use a v1/v2 policy comparison as evidence of Harness improvement."),
         p("02 / Source inventory", "heading"), p("Attach source IDs, versions, dates, file hashes and record citations. Distinguish source measurement date from receipt time. Identify missing, stale, conflicting and superseded evidence."),
         PageBreak(), p("Findings and evidence", "title"),
         p("03 / One record per finding", "heading"),
         table([["Required field", "Meaning"], ["Finding ID / control ID", "Stable finding identifier and the policy control tested."], ["Observed / limit / units", "Calculation inputs, denominator, method and result; separate as-reported and verified values."], ["Business state", "Within policy / review required / needs source."], ["Evidence", "Policy page or field + source ID + file + record + relevant fields + source date."], ["Uncertainty", "Known gaps, coverage, stale values and conclusions affected."], ["Before / after", "Previous value and current value with their separate source bindings."], ["Next step", "Proposed action or source request, owner, due condition and approval requirement."]], [2.3 * inch, 4.9 * inch]),
         p("04 / Sources requiring a second check", "heading"), p("[source_id / problem / requested confirmation / owner / due / response status]. A missing source stays unresolved until an actual reply or replacement is recorded. A successful tool transport is not sufficient evidence."),
         PageBreak(), p("Actions and handoff", "title"),
         p("05 / Proposed actions", "heading"),
         table([["Required field", "To be supplied"], ["Action ID / finding links", "[action_id] / [finding_ids]"], ["Description and bounded effect", "[specific request, artifact or review action]"], ["Owner / due condition", "[responsible role] / [date or before-signoff condition]"], ["Evidence / dependency binding", "[source references and current input hash]"], ["Decision", "PENDING / APPROVED / REJECTED / INVALIDATED"], ["Execution receipt", "[not executed, or actual result with idempotency key and receipt]"]], [2.5 * inch, 4.7 * inch]),
         p("06 / Human sign-off", "heading"), p("Reviewer: ____________________    Role: ____________________"), p("Decision: ____________________    Decided at: ____________________"), p("Rationale / conditions: __________________________________________________"),
         p("Bind the decision to the input, active policy, package content and exact proposed actions. This static template is not an authentication system, digital signature or approval service. Source or proposal changes invalidate prior approval; unresolved findings must remain visible at handoff.", "small"),
         p("07 / Handoff acceptance", "heading"), p("Receiving role: ____________________    Accepted at: ____________________\nRemaining obligations / owner: __________________________________________"),
    ]
    build_pdf(path, s, "Output contract / pending human review / no run result", 3)


def render_documents(directory, bundle):
    directory = Path(directory)
    targets = [directory / f"ips-{policy['version']}.pdf" for policy in bundle["policies"]] + [directory / "review-package-template.pdf"]
    if any(p.is_symlink() for target in targets for p in [target, *target.parents]):
        raise ValueError("PDF output path contains a symlink")
    directory.mkdir(parents=True, exist_ok=True)
    for policy in bundle["policies"]:
        policy_pdf(directory / f"ips-{policy['version']}.pdf", policy, bundle["accounts"])
    template_pdf(directory / "review-package-template.pdf")
