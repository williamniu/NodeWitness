"""Assemble a reviewable draft from observed calculations and model proposals."""

import copy
import json
from pathlib import Path
from xml.sax.saxutils import escape

from . import VERSION
from .sources import citation, now, records, sha


def package_hash(package):
    return sha({k: v for k, v in package.items() if k not in ("approval", "handoff")})


def build_package(case, calculation, proposal, run_id, model, trace_sha256, source_changes=None, observed_ids=None):
    b, manifest = case["bundle"], case["manifest"]
    package = json.loads(case["files"]["review-package-template.json"])
    active = next(p for p in b["policies"] if p["policy_id"] == b["active_policy_id"])
    prior = next(p for p in b["policies"] if p["policy_id"] == b["prior_policy_id"])
    package.update({"case_id": b["case_id"], "run_id": run_id, "package_version": 1,
                    "review_as_of": b["review_as_of"], "active_policy_id": active["policy_id"],
                    "input_sha256": manifest["input_sha256"], "model_identity": model,
                    "checker_version": "nw-finance-checker@2", "runtime_version": VERSION,
                    "created_at": now(), "trace_sha256": trace_sha256,
                    "status": proposal.get("overall_status"), "as_reported_nav_usd": calculation["as_reported_nav_usd"],
                    "summary": proposal.get("summary", ""), "calculation": calculation["calculation"],
                    "source_changes": source_changes or [], "external_actions_executed": False})
    for key in sorted(set(prior["rules"]) | set(active["rules"])):
        if prior["rules"].get(key) == active["rules"].get(key):
            continue
        package["policy_changes"].append({"change_id": "POL-" + key, "rule_id": key,
            "before": prior["rules"].get(key), "after": active["rules"].get(key),
            "effective_from": active["effective_from"], "evidence": [
                {"file": f"policy-{p['version']}.json", "source_id": p["source_id"],
                 "record_id": p["policy_id"], "fields": ["rules", "effective_from"],
                 "file_sha256": sha(case["files"][f"policy-{p['version']}.json"]),
                 "source_date": p["effective_from"], "policy_id": p["policy_id"], "policy_page": None}
                for p in (prior, active)], "affected_checks": [f["rule_id"] for f in calculation["findings"]]})
    issues = calculation["findings"][-1]["observed"]["issues"]
    for src in b["source_catalog"]:
        rows = b.get(src["file"].removesuffix(".csv").removesuffix(".json"), [])
        if not isinstance(rows, list):
            rows = []
        dates = [r.get("valuation_as_of", r.get("as_of", r.get("period_end"))) for r in rows]
        received = [r.get("received_at") for r in rows]
        problems = [i["code"] for i in issues if i["evidence"]["file"] == src["file"]]
        quality = "conflicting" if any("conflict" in p for p in problems) else "stale" if any("date" in p for p in problems) else "missing" if problems else "superseded" if src["file"] == "policy-v1.json" else "verified_for_scope"
        package["source_inventory"].append({"source_id": src["source_id"], "file": src["file"],
            "sha256": manifest["files"][src["file"]], "measurement_date": sorted({d for d in dates if d}),
            "received_at": sorted({d for d in received if d}), "quality_state": quality})
    claims = {f.get("rule_id"): f for f in proposal.get("findings", [])}
    calculation_refs = {r["file"] + ":" + r["record_id"]: r for result in calculation["findings"] for r in result["evidence"]}
    permitted = set(calculation_refs) | set(observed_ids or [])
    for result in calculation["findings"]:
        f = copy.deepcopy(result)
        claim = claims.get(f["rule_id"], {})
        existing = {r["file"] + ":" + r["record_id"] for r in f["evidence"]}
        for identifier in claim.get("citations", []):
            if identifier not in permitted or identifier in existing:
                continue
            filename, _, record_id = identifier.partition(":")
            row = records(case, filename).get(record_id)
            if row:
                f["evidence"].append(citation(case, filename, record_id, list(row)))
                existing.add(identifier)
        f.update({"finding_id": "F-" + f["rule_id"], "business_state": claim.get("business_state"),
                  "explanation": claim.get("explanation", ""), "model_citations": claim.get("citations", []),
                  "units": "USD; percent of reported NAV; cash coverage is a ratio",
                  "calculation": calculation["calculation"], "limit": active["rules"], "action_ids": []})
        if claim.get("action"):
            aid = "ACT-" + f["rule_id"]
            f["action_ids"].append(aid)
            package["suggested_actions"].append({"action_id": aid, "finding_ids": [f["finding_id"]],
                "description": claim["action"], "bounded_effect": "Review proposal only; no external execution",
                "owner_role": "Compliance Lead", "due": "Before final sign-off", "evidence": f["evidence"],
                "input_sha256": manifest["input_sha256"], "decision": "pending", "execution_receipt": None})
        if claim.get("source_request"):
            package["sources_to_recheck"].append({"request_id": "REQ-" + f["rule_id"],
                "source_id": sorted({e["source_id"] for e in f["evidence"]}), "reason": f["limitations"],
                "requested_confirmation": claim["source_request"], "owner_role": "Investment Operations",
                "due": "Before verified conclusions / final sign-off", "state": "pending"})
        package["findings"].append(f)
    inventory_files = {s["file"] for s in package["source_inventory"]}
    for finding in package["findings"]:
        for ref in finding["evidence"]:
            if ref["file"] in inventory_files:
                continue
            package["source_inventory"].append({"source_id": ref["source_id"], "file": ref["file"],
                "sha256": ref["file_sha256"], "measurement_date": [ref["source_date"]] if ref["source_date"] else [],
                "received_at": [], "quality_state": "verified_for_scope",
                "authority": "Manifest-backed file provenance; content still requires principal review."})
            inventory_files.add(ref["file"])
    package["limitations"] = ["Entirely synthetic fixed data; no client assets or financial advice.",
        "Seven known cases; not evidence of unseen-case model reliability.",
        "Arithmetic is deterministic. Qwen narratives and proposed actions require human review.",
        "Local single-operator declaration; production identity authentication is not implemented.",
        "No trading, external messages, tax calculation, hedge offsets or guaranteed liquidity."]
    package["handoff"]["receiving_role"] = "Review Principal"
    package["handoff"]["remaining_obligations"] = ["Read explanations and evidence", "Resolve outstanding source requests", "Make an explicit local decision"]
    return package


def markdown(package):
    lines = ["# Aurora review package", "", "SYNTHETIC • LOCAL OPERATOR REVIEW • NO EXTERNAL ACTIONS", "",
        f"Run: `{package['run_id']}` | Input: `{package['input_sha256']}`", "",
        f"Review date: {package['review_as_of']} | Policy: {package['active_policy_id']}",
        f"Business outcome: **{package['status']}** | Human decision: **{package['approval']['status']}**", "",
        package["summary"], "", "## Policy changes", ""]
    for c in package["policy_changes"]:
        lines += [f"- {c['rule_id']}: {json.dumps(c['before'])} → {json.dumps(c['after'])}; effective {c['effective_from']}."]
    lines += ["", "## Source revisions", "", json.dumps(package["source_changes"], ensure_ascii=False), "", "## Findings", ""]
    for f in package["findings"]:
        lines += [f"### {f['rule_id']} — {f['business_state']}", "", f["explanation"], "",
            f"Observed: `{json.dumps(f['observed'], ensure_ascii=False)}`", "",
            f"Limitations: {', '.join(f['limitations']) or 'None identified for this scope.'}", "",
            f"Model citations: {', '.join(f['model_citations'])}", ""]
    for title, items, key in (("Proposed actions", package["suggested_actions"], "description"),
                              ("Sources requiring confirmation", package["sources_to_recheck"], "requested_confirmation")):
        lines += ["## " + title, ""]
        lines += ["- " + item[key] for item in items] or ["None proposed."]
        lines += [""]
    lines += ["## Source inventory", "", "| Source | File | Quality | Measurement date | SHA256 |", "|---|---|---|---|---|"]
    for s in package["source_inventory"]:
        lines += [f"| {s['source_id']} | {s['file']} | {s['quality_state']} | {', '.join(s['measurement_date'])} | {s['sha256']} |"]
    lines += ["", "## Trace and decision", "", f"Trace: `{package['trace_sha256']}`", "",
        "Model: " + json.dumps(package["model_identity"]), "", "Approval: " + json.dumps(package["approval"]), "",
        "Handoff: " + json.dumps(package["handoff"]), "", "## Limitations", ""]
    lines += ["- " + s for s in package["limitations"]]
    return "\n".join(lines) + "\n"


def export(package, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "review.json").write_text(json.dumps(package, indent=2, ensure_ascii=False) + "\n")
    (directory / "review.md").write_text(markdown(package))
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.alignment = TA_LEFT
        style.wordWrap = "CJK"
    styles["BodyText"].fontSize = 9
    styles["BodyText"].leading = 13
    styles["BodyText"].textColor = colors.HexColor("#243949")
    story = []
    def para(text, kind="BodyText"):
        story.extend([Paragraph(escape(str(text)), styles[kind]), Spacer(1, 7)])
    para("NODEWITNESS / AURORA", "Title")
    para("Review package for principal sign-off", "Heading1")
    para("SYNTHETIC DATA | LOCAL OPERATOR DECLARATION | NO EXTERNAL ACTIONS", "Heading3")
    for label, value in (("Run", package["run_id"]), ("Review date", package["review_as_of"]),
        ("Active policy", package["active_policy_id"]), ("Business outcome", package["status"]),
        ("Human decision", package["approval"]["status"]), ("Input SHA256", package["input_sha256"]),
        ("Package content SHA256", package_hash(package))):
        para(f"{label}: {value}")
    para(package["summary"])
    para("Mandate changes", "Heading2")
    for c in package["policy_changes"]:
        para(f"{c['rule_id']}: {json.dumps(c['before'])} -> {json.dumps(c['after'])}; effective {c['effective_from']}.")
    para("Source revisions", "Heading2")
    para(json.dumps(package["source_changes"]) if package["source_changes"] else "Initial version; no replacement source applied.")
    for f in package["findings"]:
        story.append(PageBreak())
        para(f["rule_id"].replace("_", " ").title(), "Heading1")
        para(f"Decision support: {f['business_state']}", "Heading2")
        para(f["explanation"])
        observed = f["observed"]
        for k, v in observed.items():
            if k == "issues":
                for issue in v:
                    para(issue["code"] + ": " + issue["record_id"])
                if not v:
                    para("No source-quality issues identified for this scope.")
            else:
                para(f"{k}: {json.dumps(v, ensure_ascii=False)}")
        para("Limits: " + json.dumps(f["limit"], ensure_ascii=False))
        para("Limitations: " + ("; ".join(f["limitations"]) or "None identified for this scope."))
        para("Model-selected evidence: " + ", ".join(f["model_citations"]))
        para("Full record/field/hash evidence is included in the companion JSON. Policy page: " + str(f["evidence"][0]["policy_page"]))
    story.append(PageBreak())
    for title, rows, key in (("Proposed actions", package["suggested_actions"], "description"),
                             ("Source confirmations", package["sources_to_recheck"], "requested_confirmation")):
        para(title, "Heading1")
        for row in rows:
            para(row[key])
            para("Owner: " + row["owner_role"] + " | Due: " + row["due"])
        if not rows:
            para("None proposed.")
    para("Local decision and handoff", "Heading1")
    para(json.dumps(package["approval"]))
    para(json.dumps(package["handoff"]))
    for limitation in package["limitations"]:
        para(limitation)
    story.append(PageBreak())
    para("Source and execution inventory", "Heading1")
    for s in package["source_inventory"]:
        para(f"{s['source_id']} | {s['file']} | {s['quality_state']}", "Heading3")
        para("Measurement: " + ", ".join(s["measurement_date"]) + " | Received: " + ", ".join(s["received_at"]))
        para("SHA256: " + s["sha256"])
    para("Trace SHA256: " + package["trace_sha256"])
    para("Model identity: " + json.dumps(package["model_identity"]))
    def footer(canvas, doc):
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#506575"))
        canvas.drawString(42, 24, "NodeWitness | synthetic local review | " + package["run_id"][:45])
        canvas.drawRightString(570, 24, str(doc.page))
    SimpleDocTemplate(str(directory / "review.pdf"), pagesize=(612, 792), rightMargin=42,
        leftMargin=42, topMargin=42, bottomMargin=42, title="Aurora Review Package", author="NodeWitness").build(story, onFirstPage=footer, onLaterPages=footer)
