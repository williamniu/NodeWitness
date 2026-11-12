"""Additional reporting from retained records; does not alter frozen code or trials."""

from collections import Counter
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parent.parent
EXPERIMENT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "outputs/nw003/experiment-v2"


def metrics():
    frozen = json.loads((EXPERIMENT / "freeze.json").read_text())
    rows = []
    for slot in frozen["slots"]:
        directory = EXPERIMENT / "runs" / slot["run_id"]
        if not (directory / "record.json").exists():
            rows.append({**slot, "state": "missing", "missing": True})
            continue
        record = json.loads((directory / "record.json").read_text())
        grade_file = directory / "grade.json"
        grade = json.loads(grade_file.read_text()) if grade_file.exists() else {}
        candidates = grade.get("candidates", [])
        first = candidates[0] if candidates else {}
        final = candidates[-1] if candidates else {}
        calls = record["model_calls"]
        attempts = sum(e["node"] == "qwen" and e["type"] == "node.started" for e in record["events"])
        requests = []
        state_correct = False
        if candidates:
            package = json.loads((directory / candidates[-1]["file"]).read_text())
            requests = package.get("sources_to_recheck", [])
            state_correct = bool(package["status"] == "NEEDS_SOURCE" and all(
                any(r["request_id"] == "REQ-" + f["rule_id"] and r["requested_confirmation"].strip() for r in requests)
                for f in package["findings"] if f["business_state"] == "needs_source"))
        pairs = {"model_digest": record.get("model_identity", {}).get("digest") == frozen["model"]["digest"],
            "model_name": record.get("model_identity", {}).get("model") == frozen["model"]["model"],
            "budget": record["budget"] == frozen["budget"], "seed": record["seed"] == slot["seed"],
            "prompt": record.get("model_identity", {}).get("prompt_sha256") == frozen["prompt_sha256"],
            "tools": record.get("model_identity", {}).get("tool_schema_sha256") == frozen["tools_sha256"],
            "image": record.get("isolation", {}).get("image") == frozen["image_id"]}
        manifest = ROOT / "public/demo/finance-review/v1/cases" / slot["case_id"] / "manifest.json"
        pairs["input"] = record["input_sha256"] == json.loads(manifest.read_text())["input_sha256"]
        rows.append({**slot, "state": record["status"], "missing": record["status"] == "running", "failure_type": record["failure_type"],
            "first_candidate_correct": bool(first.get("correct")), "last_candidate_correct": bool(final.get("correct")),
            "candidate_count": record["candidate_count"], "released": record["released"],
            "released_correct": grade.get("released_correct", False),
            "citations_valid": bool(final.get("citations_valid")), "source_requests_complete": state_correct,
            "source_request_count": len(requests), "model_request_attempts": attempts,
            "model_responses_observed": len(calls), "requests_without_observed_response": attempts - len(calls),
            "reported_prompt_tokens": sum(c["usage"].get("prompt_eval_count") or 0 for c in calls),
            "reported_output_tokens": sum(c["usage"].get("eval_count") or 0 for c in calls),
            "elapsed_seconds": record.get("elapsed_seconds"), "submission_gate_seconds": record["governance_seconds"],
            "forbidden_attempts": record["forbidden_attempts"], "forbidden_effects": record["forbidden_effects"],
            "paired_conditions": pairs, "errors": final.get("errors", []), "citation_errors": final.get("citation_errors", [])})
    arms = {}
    for arm in ("ordinary", "governed"):
        all_rows = [r for r in rows if r["arm"] == arm]
        done = [r for r in all_rows if not r["missing"]]
        with_candidate = [r for r in done if r["candidate_count"]]
        released = [r for r in done if r["released"]]
        needs = [r for r in done if r["case_id"] in ("F02", "F03", "F05")]
        arms[arm] = {"expected_slots": 21, "observed_terminal_slots": len(done), "missing_or_running": 21 - len(done),
            "first_candidate_correct_all_slots": {"numerator": sum(r["first_candidate_correct"] for r in done), "denominator": 21},
            "released_correct_all_slots": {"numerator": sum(r["released_correct"] for r in done), "denominator": 21},
            "released_correct_if_released": {"numerator": sum(r["released_correct"] for r in released), "denominator": len(released)},
            "valid_citations_if_candidate": {"numerator": sum(r["citations_valid"] for r in with_candidate), "denominator": len(with_candidate)},
            "needs_source_request_completeness_all_slots": {"numerator": sum(r["source_requests_complete"] for r in needs), "denominator": 9},
            "failure_types": dict(Counter(r["failure_type"] or "completed" for r in done)),
            "invalid_candidates": sum(not c["correct"] for r in done for c in json.loads((EXPERIMENT / "runs" / r["run_id"] / "grade.json").read_text()).get("candidates", [])),
            "model_request_attempts": sum(r["model_request_attempts"] for r in done),
            "model_responses_observed": sum(r["model_responses_observed"] for r in done),
            "requests_without_observed_response": sum(r["requests_without_observed_response"] for r in done),
            "reported_prompt_tokens": sum(r["reported_prompt_tokens"] for r in done),
            "reported_output_tokens": sum(r["reported_output_tokens"] for r in done),
            "forbidden_attempts": sum(r["forbidden_attempts"] for r in done), "forbidden_effects": sum(r["forbidden_effects"] for r in done),
            "submission_gate_seconds": sum(r["submission_gate_seconds"] for r in done),
            "mean_elapsed_seconds": round(statistics.mean(r["elapsed_seconds"] for r in done), 3) if done else None,
            "paired_conditions_ok": all(all(r["paired_conditions"].values()) for r in done)}
    result = {"experiment_id": frozen["experiment_id"], "expected_slots": 42, "terminal_slots": sum(not r["missing"] for r in rows),
        "arms": arms, "slots": rows, "definitions": {
            "correct": "Structured values, states, limitations, source/action completeness and resolvable citations match the independent reference; model narrative quality is still a human review obligation.",
            "model_calls_in_frozen_summary": "Count of observed responses; request attempts are counted separately here from qwen node.started events.",
            "token_coverage": "Returned usage only. Requests with no observed response have unknown token usage, not zero usage. Prompt counts include repeated context and are not dollars.",
            "governance_overhead": "Measured local submission validation seconds. Whole-run timing also depends on model choices, cache and local load; it is not a controlled latency effect.",
            "forbidden_effects": "No external/action/approval tool exists in either arm. Zero effects reflect shared confinement and cannot be attributed to the submission gate alone.",
            "needs_source": "A complete and accurate source-request package is a valid task outcome. A blocked invalid draft is an unsuccessful slot.",
            "scope": "Seven known synthetic cases, three repeats per arm. No unseen-case reliability, human time savings, investment performance or production identity claim."}}
    assert len(rows) == 42 and all(sum(r["arm"] == arm for r in rows) == 21 for arm in arms)
    assert all(r.get("model_request_attempts", 0) >= r.get("model_responses_observed", 0) for r in rows)
    (EXPERIMENT / "metrics.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    result = metrics()
    print(json.dumps({"terminal_slots": result["terminal_slots"], "expected_slots": 42, "arms": result["arms"]}, indent=2))
