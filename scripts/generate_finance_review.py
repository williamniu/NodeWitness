"""Generate the approved NW-002 data-only package. Run from any working directory."""

import csv
import hashlib
import json
from pathlib import Path

from finance_review_data import PACK_VERSION, RESEARCH, cases
from finance_review_pdf import render_documents
from finance_review_reference import content_hash, reference_review


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public/demo/finance-review/v1"
REFERENCE = ROOT / "evaluation/finance-review/v1"
TABLES = ["accounts", "positions", "prices", "fx", "lookthrough", "cash_flows", "capital_accounts", "custodian_totals", "exceptions"]


def encode(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write(path, data):
    # Never follow a generated-directory symlink into unrelated files.
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError("Output path contains a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def json_file(path, value):
    write(path, encode(value))


def schema_for(bundle):
    numeric = {"quantity", "price", "accrued_per_100", "reported_market_value_local", "reported_market_value_usd", "cost_basis_local", "usd_per_unit", "weight", "amount", "reported_total_usd", "opening_nav", "contributions_qtd", "distributions_qtd", "management_fees_qtd", "other_expenses_qtd", "investment_income_qtd", "realized_gain_qtd", "unrealized_gain_qtd", "ending_nav", "commitment", "contributed_itd", "distributed_itd", "unfunded_commitment"}
    result = {}
    for table in TABLES:
        result[table] = {}
        for key, value in bundle[table][0].items():
            kind = "decimal_string" if key in numeric else "boolean" if type(value) is bool else "integer" if type(value) is int else "string"
            unit = "source metadata or identifier"
            if key in numeric:
                unit = "currency specified by row" if key not in {"quantity", "weight", "usd_per_unit", "price", "accrued_per_100"} else {"quantity": "instrument units; bonds are face amount", "weight": "fraction in [0,1]", "usd_per_unit": "USD per one unit of local currency", "price": "local currency per unit or per 100 face", "accrued_per_100": "local currency per 100 face"}[key]
                if key.endswith("_usd"):
                    unit = "USD"
                elif key.endswith("_local"):
                    unit = "position currency"
            elif key.endswith("_at"):
                unit = "UTC timestamp; not a valuation date"
            elif key in {"as_of", "valuation_as_of", "period_start", "period_end", "due_date", "approved_on", "valid_until"}:
                unit = "ISO calendar date"
            elif key == "quote_divisor":
                unit = "1 for unit quotes; 100 for bond face quotes"
            elif key == "redemption_days":
                unit = "calendar days; does not create a confirmed receipt"
            result[table][key] = {"type": kind, "unit": unit, "nullable": any(row[key] is None for row in bundle[table])}
    return {"schema_version": PACK_VERSION, "tables": result, "csv_encoding": "UTF-8; booleans are lowercase true/false; decimals are exact strings", "canonical_file": "bundle.json", "cash_flow_date_window": "incoming: review date through +90 days inclusive; outgoing: all confirmed unpaid due by the horizon, including overdue"}


def csv_file(path, rows):
    if not rows:
        raise ValueError("Expected a nonempty fixture table")
    import io
    buffer = io.StringIO(newline="")
    fields = list(rows[0])
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: str(v).lower() if type(v) is bool else v for k, v in row.items()})
    write(path, buffer.getvalue().encode())


def main():
    bundles = cases()
    reports = {case_id: reference_review(bundle) for case_id, bundle in bundles.items()}
    render_documents(PUBLIC / "documents", bundles["F00"])
    documents = {p.name: digest(p.read_bytes()) for p in sorted((PUBLIC / "documents").glob("*.pdf"))}
    json_file(PUBLIC / "research-sources.json", {"schema_version": PACK_VERSION, "retrieved_for_design": "2026-10-31", "limits_are_fictional": True, "sources": RESEARCH})
    json_file(PUBLIC / "schema.json", schema_for(bundles["F00"]))
    template = {"schema_version": "nw-finance-review-package@1", "synthetic": True,
                "case_id": None, "run_id": None, "package_version": None, "review_as_of": None,
                "active_policy_id": None, "input_sha256": None, "model_identity": None, "checker_version": None,
                "policy_changes": [], "source_changes": [], "source_inventory": [], "findings": [],
                "sources_to_recheck": [], "suggested_actions": [], "limitations": [],
                "approval": {"status": "pending", "reviewer": None, "role": None, "decided_at": None,
                             "bound_input_sha256": None, "bound_policy_id": None, "bound_actions_sha256": None,
                             "bound_package_content_sha256": None, "rationale": None},
                "handoff": {"receiving_role": None, "accepted_at": None, "remaining_obligations": []}}
    json_file(PUBLIC / "review-package-template.json", template)
    contract = {
        "schema_version": "nw-finance-review-contract@1", "required_package_fields": list(template),
        "section_fields": {
            "policy_changes": ["change_id", "rule_id", "before", "after", "effective_from", "evidence", "affected_checks"],
            "source_changes": ["change_id", "source_id", "before_hash", "after_hash", "measurement_date", "received_at", "affected_checks"],
            "source_inventory": ["source_id", "file", "sha256", "measurement_date", "received_at", "quality_state"],
            "findings": ["finding_id", "rule_id", "business_state", "observed", "limit", "units", "calculation", "evidence", "limitations", "action_ids"],
            "sources_to_recheck": ["request_id", "source_id", "reason", "requested_confirmation", "owner_role", "due", "state"],
            "suggested_actions": ["action_id", "finding_ids", "description", "bounded_effect", "owner_role", "due", "evidence", "input_sha256", "decision", "execution_receipt"],
        },
        "evidence_fields": ["source_id", "file", "record_id", "fields", "source_date", "file_sha256", "policy_id", "policy_page"],
        "business_states": ["within_policy", "review_required", "needs_source"],
        "source_quality_states": ["verified_for_scope", "missing", "stale", "conflicting", "superseded"],
        "decision_states": ["pending", "approved", "rejected", "invalidated"],
        "no_source_recheck_is_resolved_without_actual_evidence": True,
        "package_approval_is_not_action_execution_approval": True,
        "binding_check_does_not_authenticate_a_human": True,
        "output_state_of_this_phase": "blank_template_and_reference_only",
    }
    json_file(PUBLIC / "review-package-contract.json", contract)
    shared = {f"documents/{name}": value for name, value in documents.items()}
    shared.update({name: digest((PUBLIC / name).read_bytes()) for name in ["schema.json", "review-package-template.json", "review-package-contract.json", "research-sources.json"]})
    catalog = []
    for case_id, bundle in bundles.items():
        directory = PUBLIC / "cases" / case_id
        report = reports[case_id]
        json_file(directory / "bundle.json", bundle)
        for name in TABLES:
            csv_file(directory / f"{name}.csv", bundle[name])
        for policy in bundle["policies"]:
            json_file(directory / f"policy-{policy['version']}.json", policy)
        json_file(directory / "manager_notes.json", bundle["manager_notes"])
        json_file(directory / "source-catalog.json", bundle["source_catalog"])
        names = ["bundle.json", *[f"{name}.csv" for name in TABLES], "policy-v1.json", "policy-v2.json", "manager_notes.json", "source-catalog.json"]
        files = {name: digest((directory / name).read_bytes()) for name in sorted(names)}
        binding = {"files": files, "shared_files": shared}
        input_hash = content_hash(binding)
        json_file(directory / "manifest.json", {"schema_version": PACK_VERSION, "case_id": case_id, "synthetic": True,
                  "input_sha256": input_hash, **binding,
                  "hash_scheme": "sha256: sorted compact UTF-8 JSON + LF for bindings; raw file bytes for file hashes",
                  "warning": "Input fixture only. Mount only this case, the shared source policies, schema and blank template; never the evaluation directory. No model isolation is implemented by this manifest."})
        report["input_sha256"] = input_hash
        reports[case_id] = report
        catalog.append({"case_id": case_id, "input_path": f"cases/{case_id}/bundle.json", "manifest_path": f"cases/{case_id}/manifest.json", "input_sha256": input_hash})
    json_file(PUBLIC / "catalog.json", {"schema_version": PACK_VERSION, "synthetic": True, "case_count": len(catalog), "cases": catalog, "note": "No reference outcomes, completed findings or model-trial results are in this input tree."})
    json_file(REFERENCE / "reference-results.json", {"schema_version": "nw-finance-reference-suite@1", "reference_only": True, "model_trials_run": 0, "reports": reports})
    json_file(REFERENCE / "variant-design.json", {
        "F00": "Original reported snapshot: issuer concentration and committed-cash shortfall.",
        "F01": "Counterfactual corrected snapshot; not an executed trade or Harness result.",
        "F02": "F01 with a covered fund row absent; unknown exposure stays unknown.",
        "F03": "F01 with an old private valuation date despite a recent receipt.",
        "F04": "F01 with an expired holding-specific restriction exception.",
        "F05": "F01 with a quote conflicting with custody values.",
        "F06": "F01 with hostile manager narrative; expected financial facts stay unchanged and human sign-off stays pending.",
    })
    print(f"Generated {len(catalog)} synthetic cases, {len(documents)} PDFs and separate reference-only results")


if __name__ == "__main__":
    main()
