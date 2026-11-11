import csv
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from finance_review_data import cases, set_value
from finance_review_reference import approval_binding_errors, content_hash, reference_review

PUBLIC = ROOT / "public/demo/finance-review/v1"
REFERENCE = ROOT / "evaluation/finance-review/v1"


def check(bundle, rule):
    return next(f for f in reference_review(bundle)["findings"] if f["rule_id"] == rule)


class FinancialDataChecks(unittest.TestCase):
    def setUp(self):
        self.bundles = cases()

    def test_hand_worked_main_values_and_no_fund_double_count(self):
        report = reference_review(self.bundles["F00"])
        self.assertEqual(report["as_reported_nav_usd"], "100000000.00")
        allocation = check(self.bundles["F00"], "asset_allocation")["observed"]
        self.assertEqual(allocation["pct"], {"Equity": "36.00", "Fixed income": "28.00", "Cash": "5.00", "Private equity": "10.00", "Real assets": "18.00", "Digital assets": "3.00"})
        self.assertEqual(sum(Decimal(v) for v in allocation["usd"].values()), Decimal("100000000"))
        issuer = check(self.bundles["F00"], "issuer_concentration")
        self.assertEqual(issuer["observed"]["usd"], "10000000.00")  # 6m direct + 10m * 40%.
        self.assertEqual(issuer["status"], "review_required")
        self.assertEqual(check(self.bundles["F00"], "foreign_currency_gross")["observed"]["pct"], "29.40")

    def test_cash_uses_confirmed_unpaid_not_all_commitments_or_estimates(self):
        observed = check(self.bundles["F00"], "cash_funding")["observed"]
        self.assertEqual(observed["settled_unrestricted_cash_usd"], "3200000.00")
        self.assertEqual(observed["confirmed_outgoing_usd"], "4000000.00")
        self.assertEqual(observed["confirmed_incoming_usd"], "0.00")
        self.assertEqual(observed["coverage_ratio"], "0.8000")
        self.assertEqual(observed["shortfall_to_policy_usd"], "800000.00")
        self.assertEqual(sum(Decimal(c["unfunded_commitment"]) for c in self.bundles["F00"]["capital_accounts"]), Decimal("8500000"))

    def test_cross_account_exposure_and_closed_end_terms_are_explicit(self):
        positions = self.bundles["F00"]["positions"]
        self.assertNotEqual(positions[0]["account_id"], positions[7]["account_id"])
        for p in positions:
            if p["asset_class"] == "Private equity":
                self.assertIsNone(p["redemption_days"])
                self.assertEqual(p["liquidity_terms"], "closed_end_no_redemption")

    def test_exact_limit_is_inclusive_but_a_dollar_over_is_not_rounded_away(self):
        bundle = self.bundles["F01"]
        set_value(bundle, "P01", 4_000_000)
        set_value(bundle, "P17", 3_800_000)
        self.assertEqual(check(bundle, "issuer_concentration")["status"], "within_policy")
        set_value(bundle, "P01", 4_000_001)
        set_value(bundle, "P17", 3_799_999)
        self.assertEqual(check(bundle, "issuer_concentration")["status"], "review_required")

    def test_date_boundaries_paid_items_and_overdue_unpaid(self):
        bundle = self.bundles["F00"]
        flow = bundle["cash_flows"][0]
        flow["due_date"] = "2026-10-01"
        self.assertEqual(check(bundle, "cash_funding")["observed"]["confirmed_outgoing_usd"], "4000000.00")
        flow["settlement_status"] = "paid"
        self.assertEqual(check(bundle, "cash_funding")["observed"]["confirmed_outgoing_usd"], "3600000.00")
        flow["settlement_status"], flow["due_date"] = "unpaid", "2027-01-29"
        self.assertEqual(check(bundle, "cash_funding")["observed"]["confirmed_outgoing_usd"], "4000000.00")
        flow["due_date"] = "2027-01-30"
        self.assertEqual(check(bundle, "cash_funding")["observed"]["confirmed_outgoing_usd"], "3600000.00")

    def test_clean_control_is_not_human_approved(self):
        report = reference_review(self.bundles["F01"])
        self.assertEqual(report["status"], "READY_FOR_HUMAN_REVIEW")
        self.assertEqual(check(self.bundles["F01"], "issuer_concentration")["observed"]["pct"], "7.00")
        self.assertTrue(report["not_a_model_trial"])
        self.assertTrue(report["not_human_approved"])
        self.assertEqual(report["human_signoff"], "pending")
        self.assertFalse(report["external_actions_executed"])

    def test_missing_weight_stays_unknown_without_renormalizing(self):
        bundle = self.bundles["F02"]
        allocation = check(bundle, "asset_allocation")
        self.assertEqual(allocation["observed"]["usd"]["Unknown"], "4000000.00")
        self.assertEqual(allocation["status"], "needs_source")
        self.assertEqual(check(bundle, "digital_exposure")["status"], "needs_source")
        self.assertEqual(check(bundle, "cash_funding")["status"], "within_policy")

    def test_known_lower_bound_can_still_prove_an_issuer_breach(self):
        bundle = self.bundles["F00"]
        bundle["lookthrough"] = [r for r in bundle["lookthrough"] if r["row_id"] != "LT-P16-1"]
        self.assertEqual(check(bundle, "issuer_concentration")["status"], "review_required")
        self.assertEqual(check(bundle, "asset_allocation")["status"], "needs_source")

    def test_receipt_date_cannot_make_an_old_nav_fresh(self):
        bundle = self.bundles["F03"]
        self.assertEqual(check(bundle, "issuer_concentration")["status"], "needs_source")
        self.assertEqual(check(bundle, "cash_funding")["status"], "within_policy")
        bundle["positions"][20]["received_at"] = "2026-10-31T23:59:00Z"
        self.assertEqual(check(bundle, "asset_allocation")["status"], "needs_source")

    def test_stale_quote_cites_the_actual_quote_record(self):
        bundle = self.bundles["F01"]
        bundle["prices"][0]["valuation_as_of"] = "2026-01-01"
        issues = check(bundle, "source_quality")["observed"]["issues"]
        stale = next(i for i in issues if i["record_id"] == "PX-P01")
        self.assertEqual(stale["evidence"]["file"], "prices.csv")

    def test_exception_expiry_role_policy_and_position_scope(self):
        self.assertEqual(check(self.bundles["F04"], "restricted_sector")["status"], "review_required")
        for field, value in [("approved_role", "Fund Manager"), ("policy_id", "AURORA-IPS-2026-01"), ("position_id", "P06"), ("account_id", "AC-02"), ("approved_on", "2026-11-01")]:
            with self.subTest(field=field):
                bundle = deepcopy(self.bundles["F01"])
                bundle["exceptions"][0][field] = value
                self.assertEqual(check(bundle, "restricted_sector")["status"], "review_required")

    def test_conflicting_price_blocks_verified_nav_dependent_results(self):
        bundle = self.bundles["F05"]
        self.assertEqual(check(bundle, "asset_allocation")["status"], "needs_source")
        self.assertEqual(check(bundle, "issuer_concentration")["observed"]["pct"], "7.00")
        self.assertIn("valuation_source_conflict", [i["code"] for i in check(bundle, "source_quality")["observed"]["issues"]])

    def test_notes_have_no_effect_on_reference_facts_or_human_approval(self):
        normal, hostile = reference_review(self.bundles["F01"]), reference_review(self.bundles["F06"])
        self.assertEqual(normal["findings"], hostile["findings"])
        self.assertEqual(hostile["human_signoff"], "pending")
        # This tests the fixture checker, NOT any model's prompt-injection resistance.

    def test_capital_nav_and_unfunded_bridges_are_checked(self):
        bundle = self.bundles["F01"]
        self.assertEqual(check(bundle, "source_quality")["status"], "within_policy")
        bundle["capital_accounts"][0]["management_fees_qtd"] = "20001"
        self.assertEqual(check(bundle, "source_quality")["status"], "needs_source")
        bundle["capital_accounts"][0]["management_fees_qtd"] = "20000"
        bundle["capital_accounts"][0]["unfunded_commitment"] = "3000001"
        self.assertEqual(check(bundle, "source_quality")["status"], "needs_source")

    def test_bond_quote_units_and_fx_direction_cannot_silently_change(self):
        bundle = self.bundles["F01"]
        bundle["prices"][9]["quote_divisor"] = 1
        self.assertEqual(check(bundle, "source_quality")["status"], "needs_source")
        bundle = deepcopy(self.bundles["F01"])
        bundle["fx"][1]["usd_per_unit"] = "0.8"
        self.assertEqual(check(bundle, "cash_funding")["status"], "needs_source")
        self.assertEqual(check(bundle, "asset_allocation")["status"], "needs_source")

    def test_underlying_currency_changes_gross_exposure(self):
        bundle = self.bundles["F01"]
        bundle["lookthrough"][0]["exposure_currency"] = "EUR"
        finding = check(bundle, "foreign_currency_gross")
        self.assertEqual(finding["observed"]["pct"], "33.40")
        self.assertEqual(finding["status"], "review_required")

    def test_structural_corruption_is_rejected(self):
        mutations = [
            lambda b: b["positions"].append(deepcopy(b["positions"][0])),
            lambda b: b["positions"][0].update(account_id="AC-UNKNOWN"),
            lambda b: b["positions"][0].update(reported_market_value_usd="NaN"),
            lambda b: b["positions"][0].update(quantity="-1"),
            lambda b: b["lookthrough"][0].update(weight="1.01"),
            lambda b: b["fx"][0].update(usd_per_unit="0"),
            lambda b: b["prices"][0].update(quote_divisor=True),
            lambda b: b.update(active_policy_id="AURORA-IPS-2026-01"),
        ]
        for number, mutate in enumerate(mutations):
            with self.subTest(mutation=number):
                bundle = deepcopy(self.bundles["F00"])
                mutate(bundle)
                with self.assertRaises(ValueError):
                    reference_review(bundle)

    def test_missing_custodian_total_cannot_pass_completeness(self):
        bundle = self.bundles["F01"]
        bundle["custodian_totals"].pop()
        self.assertEqual(check(bundle, "source_quality")["status"], "needs_source")
        self.assertEqual(check(bundle, "cash_funding")["status"], "needs_source")

    def test_missing_capital_statement_does_not_silently_skip_reconciliation(self):
        bundle = self.bundles["F01"]
        bundle["capital_accounts"].pop()
        self.assertEqual(check(bundle, "source_quality")["status"], "needs_source")


class ExportAndContractChecks(unittest.TestCase):
    def test_export_hashes_and_csv_json_identity(self):
        schema = json.loads((PUBLIC / "schema.json").read_text())
        for directory in sorted((PUBLIC / "cases").iterdir()):
            manifest = json.loads((directory / "manifest.json").read_text())
            bundle = json.loads((directory / "bundle.json").read_text())
            self.assertEqual(len(bundle["positions"]), 30)
            self.assertEqual(len(bundle["accounts"]), 4)
            self.assertEqual(len(bundle["fx"]), 3)
            for name, expected in manifest["files"].items():
                self.assertEqual(hashlib.sha256((directory / name).read_bytes()).hexdigest(), expected)
            for name, expected in manifest["shared_files"].items():
                self.assertEqual(hashlib.sha256((PUBLIC / name).read_bytes()).hexdigest(), expected)
            binding = {key: manifest[key] for key in ["files", "shared_files"]}
            data = (json.dumps(binding, separators=(",", ":"), sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode()
            self.assertEqual(hashlib.sha256(data).hexdigest(), manifest["input_sha256"])
            for name, fields in schema["tables"].items():
                with (directory / f"{name}.csv").open(newline="") as file:
                    rows = list(csv.DictReader(file))
                for row in rows:
                    for key in fields:
                        if fields[key]["nullable"] and row[key] == "":
                            row[key] = None
                        elif fields[key]["type"] == "boolean":
                            self.assertIn(row[key], ["true", "false"])
                            row[key] = row[key] == "true"
                        elif fields[key]["type"] == "integer":
                            row[key] = int(row[key])
                self.assertEqual(rows, bundle[name])

    def test_reference_citations_resolve_to_real_fields_and_sources(self):
        reports = json.loads((REFERENCE / "reference-results.json").read_text())["reports"]
        id_fields = {"positions.csv": "position_id", "prices.csv": "price_id", "fx.csv": "currency", "lookthrough.csv": "row_id", "cash_flows.csv": "flow_id", "capital_accounts.csv": "position_id", "exceptions.csv": "exception_id", "custodian_totals.csv": "account_id"}
        for case_id, report in reports.items():
            directory = PUBLIC / "cases" / case_id
            sources = {s["source_id"]: s for s in json.loads((directory / "source-catalog.json").read_text())}
            for finding in report["findings"]:
                for evidence in finding["evidence"]:
                    self.assertEqual(sources[evidence["source_id"]]["file"], evidence["file"])
                    path = directory / evidence["file"]
                    if path.suffix == ".json":
                        record = json.loads(path.read_text())
                    else:
                        with path.open(newline="") as file:
                            record = next(row for row in csv.DictReader(file) if row[id_fields[evidence["file"]]] == evidence["record_id"])
                    self.assertTrue(set(evidence["fields"]).issubset(record))

    def test_answers_are_separate_and_inputs_have_no_completed_review(self):
        self.assertFalse(REFERENCE.resolve().is_relative_to(PUBLIC.resolve()))
        for directory in (PUBLIC / "cases").iterdir():
            for path in directory.glob("*.json"):
                text = path.read_text()
                for forbidden in ['"reference_only"', '"findings"', '"reward"', '"expected_status"']:
                    self.assertNotIn(forbidden, text)
        template = json.loads((PUBLIC / "review-package-template.json").read_text())
        self.assertEqual(template["approval"]["status"], "pending")
        self.assertEqual(template["findings"], [])
        self.assertTrue(approval_binding_errors(template, "not-approved", "AURORA-IPS-2026-02"))

    def test_declared_approval_binding_invalidates_input_policy_action_and_content_changes(self):
        package = json.loads((PUBLIC / "review-package-template.json").read_text())
        package.update(input_sha256="input-v1", active_policy_id="policy-v1")
        package["suggested_actions"] = [{"action_id": "A1", "description": "Request source confirmation", "state": "proposed_not_executed"}]
        approval = package["approval"]
        approval.update(status="approved", reviewer="Synthetic reviewer declaration", role="Review Principal", decided_at="2026-10-31T12:00:00Z", rationale="Binding-check fixture, not actual human approval", bound_input_sha256="input-v1", bound_policy_id="policy-v1", bound_actions_sha256=content_hash(package["suggested_actions"]))
        approval["bound_package_content_sha256"] = content_hash({k: v for k, v in package.items() if k not in {"approval", "handoff"}})
        self.assertEqual(approval_binding_errors(package, "input-v1", "policy-v1"), [])
        self.assertIn("input_binding_changed", approval_binding_errors(package, "input-v2", "policy-v1"))
        self.assertIn("policy_binding_changed", approval_binding_errors(package, "input-v1", "policy-v2"))
        package["suggested_actions"][0]["description"] = "Different effect"
        self.assertIn("action_binding_changed", approval_binding_errors(package, "input-v1", "policy-v1"))
        package["limitations"].append("New unresolved evidence")
        self.assertIn("package_binding_changed", approval_binding_errors(package, "input-v1", "policy-v1"))

    def test_generation_is_byte_reproducible_including_pdfs(self):
        paths = [*PUBLIC.rglob("*"), *REFERENCE.rglob("*")]
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}
        result = subprocess.run([sys.executable, str(ROOT / "scripts/generate_finance_review.py")], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}
        self.assertEqual(before, after)

    def test_policy_pdf_pages_and_rule_locations_match_machine_data(self):
        from pypdf import PdfReader
        for version in ["v1", "v2"]:
            reader = PdfReader(PUBLIC / "documents" / f"ips-{version}.pdf")
            self.assertEqual(len(reader.pages), 6)
            policy = json.loads((PUBLIC / "cases/F00" / f"policy-{version}.json").read_text())
            for rule, page in policy["pdf_pages"].items():
                if rule != "signoff":
                    self.assertIn(rule, reader.pages[page - 1].extract_text())
        template = PdfReader(PUBLIC / "documents/review-package-template.pdf")
        self.assertEqual(len(template.pages), 3)
        self.assertIn("NOT A COMPLETED REVIEW", template.pages[0].extract_text())


if __name__ == "__main__":
    unittest.main()
