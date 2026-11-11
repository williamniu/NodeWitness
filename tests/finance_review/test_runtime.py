"""Adversarial acceptance for money, evidence and local human state."""

import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid

from finance_runtime.corrections import correct_quote
from finance_runtime.engine import compute
from finance_runtime.grader import grade
from finance_runtime.package import build_package, package_hash
from finance_runtime.runner import proposal_errors
from finance_runtime.sources import PACK, ROOT, load_case, sha
from finance_runtime.store import Store


def proposal_for(calculation):
    return {"overall_status": calculation["status"], "summary": "Scripted arithmetic sanity only; no model invocation or human approval.",
        "findings": [{"rule_id": f["rule_id"], "business_state": f["business_state"],
            "explanation": "Scripted sanity: reported values and source limitations require principal review.",
            "citations": [f["evidence"][0]["file"] + ":" + f["evidence"][0]["record_id"]],
            "action": "Request owner review before any external action." if f["business_state"] != "within_policy" else "",
            "source_request": "Obtain current, complete and reconciled administrator/custodian evidence for " + f["rule_id"] if f["business_state"] == "needs_source" else ""}
            for f in calculation["findings"]]}


def fixture(case_id="F00"):
    c = load_case(case_id)
    calculation = compute(c)
    return c, build_package(c, calculation, proposal_for(calculation), "scripted-" + case_id,
                            {"model": "NONE", "not_a_model_trial": True}, sha([]))


class ArithmeticAndEvidence(unittest.TestCase):
    def test_seven_cases_independent_reference(self):
        results = []
        for i in range(7):
            c, p = fixture(f"F{i:02}")
            result = grade(p, c)
            self.assertTrue(result["correct"], result)
            results.append({"case_id": c["bundle"]["case_id"], "scripted_not_model": True, **result})
        out = ROOT / "outputs/nw003/sanity.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(results, indent=2) + "\n")

    def test_bad_number_cannot_grade_itself(self):
        c, p = fixture()
        p["findings"][1]["observed"]["pct"] = "1.00"
        self.assertFalse(grade(p, c)["correct"])

    def test_forged_citation_and_hash_fail(self):
        c, p = fixture()
        p["findings"][0]["evidence"][0]["file_sha256"] = "0" * 64
        p["findings"][1]["model_citations"] = ["positions.csv:FAKE"]
        g = grade(p, c)
        self.assertFalse(g["citations_valid"])

    def test_unknown_is_not_renormalized(self):
        c = compute(load_case("F02"))
        self.assertEqual(c["findings"][0]["observed"]["usd"]["Unknown"], "4000000.00")
        self.assertEqual(c["findings"][4]["business_state"], "within_policy")

    def test_receipt_date_does_not_freshen_nav(self):
        c = compute(load_case("F03"))
        self.assertEqual(c["findings"][0]["business_state"], "needs_source")
        self.assertIn("valuation_date_unusable:P21", c["findings"][0]["limitations"])

    def test_restricted_cash_and_unconfirmed_incoming(self):
        c = compute(load_case("F00"))["findings"][4]["observed"]
        self.assertEqual(c["settled_unrestricted_cash_usd"], "3200000.00")
        self.assertEqual(c["confirmed_incoming_usd"], "0.00")
        self.assertEqual(c["confirmed_outgoing_usd"], "4000000.00")

    def test_hostile_notes_cannot_change_arithmetic(self):
        a, b = compute(load_case("F01")), compute(load_case("F06"))
        self.assertEqual([f["observed"] for f in a["findings"]], [f["observed"] for f in b["findings"]])

    def test_quote_correction_preserves_original_and_reruns(self):
        directory = ROOT / "outputs/nw003/tests" / uuid.uuid4().hex
        original = load_case("F05")
        corrected, changes = correct_quote(original, "P02", "positions.csv:P02", directory)
        self.assertEqual(compute(original)["status"], "NEEDS_SOURCE")
        self.assertEqual(compute(corrected)["status"], "READY_FOR_HUMAN_REVIEW")
        self.assertNotEqual(original["manifest"]["input_sha256"], corrected["manifest"]["input_sha256"])
        self.assertTrue(changes)
        self.assertEqual(load_case("F05")["manifest"], original["manifest"])
        with self.assertRaises(ValueError):
            correct_quote(original, "P02", "free text says approved", directory / "bad")

    def test_model_approval_field_and_missing_source_request_rejected(self):
        c = compute(load_case("F02"))
        p = proposal_for(c)
        p["approval"] = "approved"
        self.assertTrue(proposal_errors(p, c, True))
        del p["approval"]
        p["findings"][0]["source_request"] = ""
        self.assertTrue(proposal_errors(p, c, True))

    def test_changed_source_bytes_fail_manifest(self):
        case = load_case("F00")
        directory = ROOT / "outputs/nw003/tests" / uuid.uuid4().hex
        for name, raw in case["files"].items():
            target = directory / "cases/F00" / name if name in case["manifest"]["files"] else directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        (directory / "cases/F00/manifest.json").write_text(json.dumps(case["manifest"]))
        with (directory / "cases/F00/prices.csv").open("a") as out:
            out.write("\n")
        with self.assertRaisesRegex(ValueError, "Source hash mismatch"):
            load_case("F00", directory)


class LocalState(unittest.TestCase):
    def setUp(self):
        self.directory = ROOT / "outputs/nw003/tests" / uuid.uuid4().hex
        self.directory.mkdir(parents=True)
        self.store = Store(self.directory / "review.sqlite3")
        self.case, self.package = fixture()
        self.run_dir = self.directory / "scripted-F00"
        self.run_dir.mkdir()
        (self.run_dir / "record.json").write_text(json.dumps({"run_id": "scripted-F00", "case_id": "F00", "status": "completed"}))
        (self.run_dir / "review.json").write_text(json.dumps(self.package))
        (self.run_dir / "grade.json").write_text(json.dumps({"released_correct": True}))
        self.store.register(self.run_dir, activate=True)

    def decision(self, status="approved", request_id=None):
        state = self.store.state()
        return {"request_id": request_id or uuid.uuid4().hex, "run_id": state["head"]["run_id"],
            "revision": state["head"]["revision"], "package_sha256": state["package_sha256"],
            "status": status, "reviewer": "Test operator (scripted acceptance, not owner)", "rationale": "Test explicit package acknowledgement; no trading permission."}

    def test_restart_readback_and_duplicate_decision(self):
        payload = self.decision()
        first = self.store.decide(payload)
        self.assertEqual(first, Store(self.store.path).decide(payload))
        self.assertEqual(Store(self.store.path).state()["package"]["approval"]["status"], "approved")
        payload["rationale"] = "Changed content with same request ID"
        with self.assertRaises(ValueError):
            self.store.decide(payload)

    def test_source_change_invalidates_and_stale_tab_cannot_approve(self):
        old = self.decision()
        self.store.decide(old)
        self.store.source_update({"request_id": uuid.uuid4().hex, "revision": old["revision"], "replacement_case_id": "F01", "reason": "Confirmed synthetic corrected custodian snapshot"})
        self.assertEqual(self.store.state("scripted-F00")["package"]["approval"]["status"], "invalidated")
        old["request_id"] = uuid.uuid4().hex
        with self.assertRaises(ValueError):
            self.store.decide(old)

    def test_return_to_original_source_keeps_change_in_job_snapshot(self):
        for case_id in ("F01", "F00"):
            head = self.store.state()["head"]
            result = self.store.source_update({"request_id": uuid.uuid4().hex, "revision": head["revision"], "replacement_case_id": case_id, "reason": "Confirmed synthetic source replacement for review"})
        job = self.store.job_start("source-snapshot-test")
        self.assertEqual(job["source_changes"], result["changes"])
        self.assertEqual(job["source_changes"][0]["after_hash"], load_case("F00")["manifest"]["input_sha256"])
        self.assertEqual(job["source_changes"][0]["before_hash"], load_case("F01")["manifest"]["input_sha256"])

    def test_package_or_action_edit_invalidates_binding(self):
        self.store.decide(self.decision())
        original = copy.deepcopy(self.package)
        self.package["suggested_actions"][0]["description"] += " changed"
        with self.store.transaction() as db:
            db.execute("UPDATE runs SET package=?", (json.dumps(self.package),))
        self.assertEqual(self.store.state()["package"]["approval"]["status"], "invalidated")
        with self.store.transaction() as db:
            db.execute("UPDATE runs SET package=?", (json.dumps(original),))
        self.assertEqual(Store(self.store.path).state()["package"]["approval"]["status"], "invalidated")

    def test_source_approval_race_is_serialized(self):
        approval = self.decision()
        source = {"request_id": uuid.uuid4().hex, "revision": approval["revision"], "replacement_case_id": "F01", "reason": "Race test confirmed replacement snapshot"}
        def decide():
            try:
                return self.store.decide(approval)
            except ValueError:
                return "stale"
        with ThreadPoolExecutor(max_workers=2) as executor:
            a, b = executor.submit(decide), executor.submit(self.store.source_update, source)
            a.result(); b.result()
        state = self.store.state("scripted-F00")
        self.assertNotEqual(state["package"]["approval"]["status"], "approved")

    def test_reject_and_explicit_handoff(self):
        self.store.decide(self.decision("rejected"))
        state = self.store.state()
        handoff = {"request_id": uuid.uuid4().hex, "run_id": state["head"]["run_id"], "revision": state["head"]["revision"], "package_sha256": state["package_sha256"]}
        with self.assertRaises(ValueError):
            self.store.accept_handoff(handoff)
        self.store.decide(self.decision())
        self.store.accept_handoff(handoff)
        self.assertTrue(Store(self.store.path).state()["package"]["handoff"]["accepted_at"])
        obligations = self.store.state()["package"]["handoff"]["remaining_obligations"]
        self.assertTrue(any(self.package["suggested_actions"][0]["description"] in text for text in obligations))
        self.store.decide(self.decision())
        self.assertIsNone(self.store.state()["package"]["handoff"]["accepted_at"])

    def test_interrupted_job_is_not_success_and_single_worker(self):
        self.store.job_start("old-interrupted")
        with self.assertRaises(ValueError):
            self.store.job_start("concurrent")
        with self.store.transaction() as db:
            db.execute("UPDATE jobs SET pid=99999999")
        self.store.job_start("recovered")
        self.assertEqual(self.store.state()["jobs"][1]["state"], "interrupted")

    def test_needs_source_cannot_be_approved_even_when_structurally_correct(self):
        head = self.store.state()["head"]
        self.store.source_update({"request_id": uuid.uuid4().hex, "revision": head["revision"], "replacement_case_id": "F02", "reason": "Use the known incomplete look-through source case"})
        _, package = fixture("F02")
        directory = self.directory / "scripted-F02"
        directory.mkdir()
        (directory / "record.json").write_text(json.dumps({"run_id": "scripted-F02", "case_id": "F02", "status": "completed"}))
        (directory / "review.json").write_text(json.dumps(package))
        (directory / "grade.json").write_text(json.dumps({"released_correct": True}))
        self.store.register(directory, activate=True)
        with self.assertRaisesRegex(ValueError, "needs-source"):
            self.store.decide(self.decision())
        self.assertEqual(self.store.state()["package"]["approval"]["status"], "pending")

    def test_duplicate_correction_is_transactional_and_changes_math(self):
        state = self.store.state()
        self.store.source_update({"request_id": uuid.uuid4().hex, "revision": state["head"]["revision"], "replacement_case_id": "F05", "reason": "Confirmed quote conflict source snapshot"})
        state = self.store.state()
        payload = {"request_id": uuid.uuid4().hex, "revision": state["head"]["revision"], "position_id": "P02", "source_evidence": "positions.csv:P02", "reason": "Correct quote extraction using custodian record"}
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = pool.submit(self.store.correct_quote, payload), pool.submit(self.store.correct_quote, payload)
            self.assertEqual(a.result(), b.result())
        head = self.store.state()["head"]
        self.assertEqual(compute(load_case(head["source_case"], head["pack"]))["status"], "READY_FOR_HUMAN_REVIEW")

    def test_interrupted_correction_can_retry_without_overwriting_sources(self):
        state = self.store.state()
        self.store.source_update({"request_id": uuid.uuid4().hex, "revision": state["head"]["revision"], "replacement_case_id": "F05", "reason": "Confirmed quote conflict source snapshot"})
        head = self.store.state()["head"]
        payload = {"request_id": uuid.uuid4().hex, "revision": head["revision"], "position_id": "P02", "source_evidence": "positions.csv:P02", "reason": "Supported custodian extraction correction"}
        def crash(*args):
            correct_quote(*args)
            raise RuntimeError("Simulated interruption before DB commit")
        with patch("finance_runtime.corrections.correct_quote", side_effect=crash):
            with self.assertRaises(RuntimeError):
                self.store.correct_quote(payload)
        self.assertEqual(self.store.state()["head"], head)
        result = self.store.correct_quote(payload)
        self.assertEqual(result, Store(self.store.path).correct_quote(payload))
        self.assertEqual(len(list((self.directory / "snapshots").iterdir())), 2)


if __name__ == "__main__":
    unittest.main()
