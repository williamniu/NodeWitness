"""Regression cases discovered in the retained v1 frozen experiment."""

import unittest

from finance_runtime.engine import compute
from finance_runtime.grader import grade
from finance_runtime.package import build_package
from finance_runtime.runner import proposal_errors
from finance_runtime.sources import ROOT, citation, load_case, records, sha
import copy
import json
from tests.finance_review.test_runtime import proposal_for


class EvidenceRegression(unittest.TestCase):
    def test_current_read_corroboration_is_valid_across_controls(self):
        case = load_case("F05")
        calculation = compute(case)
        proposal = proposal_for(calculation)
        quality = next(f for f in proposal["findings"] if f["rule_id"] == "source_quality")
        quality["citations"] += ["prices.csv:PX-P02", "positions.csv:P02"]
        self.assertEqual(proposal_errors(proposal, calculation, True), [])
        package = build_package(case, calculation, proposal, "scripted-citation-regression", {"model": "NONE", "not_a_model_trial": True}, sha([]))
        result = grade(package, case)
        self.assertTrue(result["correct"], result)

    def test_listed_source_catalog_is_record_addressable(self):
        case = load_case("F05")
        catalog = records(case, "source-catalog.json")
        self.assertIn("SRC-PX", catalog)
        self.assertEqual(catalog["SRC-PX"]["file"], "prices.csv")

    def test_cross_case_or_nonexistent_records_are_still_denied(self):
        calculation = compute(load_case("F05"))
        for citation in ("cases/F01/positions.csv:P02", "positions.csv:FAKE"):
            proposal = proposal_for(calculation)
            proposal["findings"][-1]["citations"].append(citation)
            self.assertTrue(proposal_errors(proposal, calculation, True))

    def test_real_but_unread_notes_need_observed_receipt(self):
        case = load_case("F06")
        calculation = compute(case)
        proposal = proposal_for(calculation)
        proposal["findings"][-1]["citations"].append("manager_notes.json:NOTE-02")
        self.assertTrue(proposal_errors(proposal, calculation, True))
        observed = {"manager_notes.json:NOTE-02"}
        self.assertEqual(proposal_errors(proposal, calculation, True, observed), [])
        package = build_package(case, calculation, proposal, "scripted-observed-note", {"model": "NONE"}, sha([]), observed_ids=observed)
        self.assertTrue(grade(package, case)["correct"])

    def test_independent_checker_rejects_unread_metadata_with_real_hash(self):
        directory = ROOT / "outputs/nw003/experiment/runs/nw003-20261031-v1-F00-governed-1"
        if not directory.exists():
            self.skipTest("Retained real v1 trace is unavailable in a fresh checkout")
        case = load_case("F00")
        package = copy.deepcopy(json.loads((directory / "review.json").read_text()))
        row = records(case, "source-catalog.json")["SRC-PX"]
        package["findings"][0]["evidence"].append(citation(case, "source-catalog.json", "SRC-PX", list(row)))
        package["findings"][0]["model_citations"].append("source-catalog.json:SRC-PX")
        result = grade(package, case, json.loads((directory / "record.json").read_text()), directory)
        self.assertFalse(result["correct"])
        self.assertTrue(any("actual source-read receipt" in s for s in result["citation_errors"]))

    def test_account_metadata_without_publisher_source_id_binds_to_manifest(self):
        case = load_case("F00")
        calculation = compute(case)
        proposal = proposal_for(calculation)
        proposal["findings"][0]["citations"].append("accounts.csv:AC-01")
        observed = {"accounts.csv:AC-01"}
        self.assertEqual(proposal_errors(proposal, calculation, True, observed), [])
        package = build_package(case, calculation, proposal, "scripted-account-metadata", {"model": "NONE"}, sha([]), observed_ids=observed)
        result = grade(package, case)
        self.assertTrue(result["correct"], result)
        self.assertTrue(any(s["file"] == "accounts.csv" for s in package["source_inventory"]))


if __name__ == "__main__":
    unittest.main()
