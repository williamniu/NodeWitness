"""Frozen, paired real-model comparison. Existing slots are never rerun/overwritten."""

import json
from pathlib import Path
import statistics
import sys

from .grader import grade_run
from .runner import BUDGET, IMAGE, SYSTEM, TOOLS, command, model_metadata, run
from .sources import ROOT, PACK, load_case, now, sha

DIRECTORY = ROOT / "outputs/nw003/experiment-v2"
EXPERIMENT = "nw003-20261031-v2"
SEEDS = (11, 29, 47)
FROZEN = ["finance_runtime/" + name for name in (
    "__init__.py", "sources.py", "engine.py", "task.py", "runner.py", "package.py", "grader.py", "Dockerfile", "experiment.py")]
FROZEN += ["scripts/finance_review_reference.py", "evaluation/finance-review/v1/reference-results.json"]


def slots():
    result = []
    for i in range(7):
        for repeat, seed in enumerate(SEEDS, 1):
            arms = ("ordinary", "governed") if (i + repeat) % 2 else ("governed", "ordinary")
            for arm in arms:
                result.append({"run_id": f"{EXPERIMENT}-F{i:02}-{arm}-{repeat}", "case_id": f"F{i:02}", "arm": arm, "seed": seed, "repeat": repeat})
    return result


def freeze():
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    target = DIRECTORY / "freeze.json"
    if target.exists():
        raise ValueError("Freeze already exists; use verify/run/summary")
    source_hashes = {name: sha((ROOT / name).read_bytes()) for name in FROZEN}
    inputs = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in sorted(PACK.rglob("*")) if p.is_file()}
    document = {"experiment_id": EXPERIMENT, "frozen_at": now(), "source_hashes": source_hashes,
        "input_files": inputs, "model": model_metadata(), "budget": BUDGET, "seeds": SEEDS,
        "prompt_sha256": sha(SYSTEM.encode()), "tools_sha256": sha(TOOLS),
        "image_id": command(["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"]),
        "docker_version": command(["docker", "version", "--format", "{{.Server.Version}}"]),
        "slots": slots(), "expected_trials": 42,
        "calibration": ["32 decisions/tools, 900s episode, 120s model and other approved budgets unchanged.",
            "The complete v1 ledger and exact sources are retained separately. V2 fixes a per-finding citation false positive and advertised metadata reading; its independent checker also verifies actual source-read receipts.",
            "Development F02-001 exposed an unknown-record tool failure. Return explicit missing records; retain the failed development run.",
            "Development narrative repeated structured tables. The final shared prompt requests <=100-word summary, <=35-word explanations and 1-3 citations; full numerical/evidence tables remain in packages.",
            "Development and seven scripted sanity runs excluded from model-arm metrics."],
        "scope": "Frozen agent/computation/submission/evaluation path. Local UI, operator state and corrections are tested separately and are not an inference treatment in these 42 slots.",
        "fairness": "Same task, prompt, model/digest, source access, tools, budgets and paired seed. Arm ordering alternates. Ordinary records its candidate without a submission gate; governed validates and allows repair within the same budget.",
        "limits": ["Seven known synthetic cases, no held-out set", "No timed human reviewer study", "Requested seeds do not guarantee determinism", "Performance depends on local cache/load and is descriptive"]}
    target.write_text(json.dumps(document, indent=2) + "\n")
    return document


def verify():
    frozen = json.loads((DIRECTORY / "freeze.json").read_text())
    for section in ("source_hashes", "input_files"):
        for name, expected in frozen[section].items():
            if sha((ROOT / name).read_bytes()) != expected:
                raise RuntimeError("Frozen file changed: " + name)
    if model_metadata() != frozen["model"] or BUDGET != frozen["budget"]:
        raise RuntimeError("Frozen model/runtime/budget changed")
    if command(["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"]) != frozen["image_id"]:
        raise RuntimeError("Frozen task image changed")
    return frozen


def summarize():
    frozen = json.loads((DIRECTORY / "freeze.json").read_text())
    results, missing = [], []
    for slot in frozen["slots"]:
        directory = DIRECTORY / "runs" / slot["run_id"]
        if not (directory / "record.json").exists():
            missing.append(slot["run_id"])
            continue
        record = json.loads((directory / "record.json").read_text())
        if record["status"] == "running":
            missing.append(slot["run_id"])
            continue
        result = grade_run(directory)
        results.append(result)
    arms = {}
    for arm in ("ordinary", "governed"):
        rows = [r for r in results if r["arm"] == arm]
        released = sum(r["released"] for r in rows)
        correct = sum(r["released_correct"] for r in rows)
        arms[arm] = {"trials": len(rows), "expected_trials": 21, "missing_trials": 21 - len(rows),
            "first_candidate_correct": sum(r["first_candidate_correct"] for r in rows),
            "released": released, "released_correct": correct,
            "released_correct_rate_all_slots": correct / 21,
            "released_correct_rate_if_released": correct / released if released else None,
            "failures": sum(bool(r["failure_type"]) for r in rows),
            "citations_valid": sum(bool(r["candidates"] and r["candidates"][-1]["citations_valid"]) for r in rows),
            "stale_case_correct": sum(r["released_correct"] for r in rows if r["case_id"] == "F03"), "stale_case_expected": 3,
            "needs_source_cases_correct": sum(r["released_correct"] for r in rows if r["case_id"] in ("F02", "F03", "F05")), "needs_source_cases_expected": 9,
            "hostile_case_correct": sum(r["released_correct"] for r in rows if r["case_id"] == "F06"), "hostile_case_expected": 3,
            "forbidden_attempts": sum(r["forbidden_attempts"] for r in rows), "forbidden_effects": sum(r["forbidden_effects"] for r in rows),
            "model_calls": sum(r["model_calls"] for r in rows), "prompt_tokens": sum(r["prompt_tokens"] for r in rows),
            "output_tokens": sum(r["output_tokens"] for r in rows),
            "mean_seconds": round(statistics.mean(r["elapsed_seconds"] for r in rows), 3) if rows else 0,
            "submission_gate_seconds": sum(r["governance_seconds"] for r in rows)}
    summary = {"experiment_id": EXPERIMENT, "frozen_at": frozen["frozen_at"], "updated_at": now(),
        "expected_trials": 42, "observed_trials": len(results), "missing_trials": len(missing), "missing_run_ids": missing,
        "arms": arms, "results": results, "scripted_sanity_trials": 7, "scripted_excluded_from_model_denominators": True,
        "human_time_savings": "UNMEASURED", "production_reliability": "NOT ESTABLISHED", "forbidden_effects_scope": "Finite tools plus container confinement apply to both arms; no external action tool exists.",
        "approval_invalidation": "Separate transactional/adversarial tests and browser acceptance; not a paired-model effect.",
        "treatment": frozen["fairness"], "limits": frozen["limits"]}
    summary["governed_minus_ordinary_correct_slots"] = arms["governed"]["released_correct"] - arms["ordinary"]["released_correct"]
    (DIRECTORY / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = ["# NW-003 paired model comparison", "", f"Experiment: {EXPERIMENT}. Actual completed slots: {len(results)}/42; missing: {len(missing)}.", "",
        "| Mode | First candidate correct /21 | Released and correct /21 | Failures | Valid citations /21 | Needs-source correct /9 | Forbidden attempts/effects | Mean seconds |", "|---|---|---|---|---|---|---|---|"]
    for arm, a in arms.items():
        lines += [f"| {arm} | {a['first_candidate_correct']} | {a['released_correct']} | {a['failures']} | {a['citations_valid']} | {a['needs_source_cases_correct']} | {a['forbidden_attempts']}/{a['forbidden_effects']} | {a['mean_seconds']} |"]
    lines += ["", f"Governed minus ordinary correct releases: {summary['governed_minus_ordinary_correct_slots']} slots. No positive effect is assumed.", "",
        "All 42 slots use the same legitimate information and numerical tools. Wrong/blocked drafts count as unsuccessful slots. The seven scripted sanity checks are separate.", "",
        "Human reviewer time savings are unmeasured. These are known synthetic cases. Narrative quality still requires principal review. No production identity or unseen-case reliability claim is supported.", "",
        "Source/correction/approval invalidation is verified separately. Tool confinement is shared by both arms; zero forbidden effects cannot be attributed solely to the submission gate.", ""]
    (DIRECTORY / "comparison.md").write_text("\n".join(lines))
    return summary


def execute():
    frozen = verify()
    for index, slot in enumerate(frozen["slots"], 1):
        directory = DIRECTORY / "runs" / slot["run_id"]
        if directory.exists():
            print(json.dumps({"slot": index, "retained_existing": slot["run_id"]}), flush=True)
            continue
        verify()
        record = run(slot["case_id"], slot["arm"], slot["seed"], slot["run_id"], DIRECTORY / "runs")
        result = grade_run(directory)
        summarize()
        print(json.dumps({"slot": index, "run_id": slot["run_id"], "status": record["status"], "correct": result["released_correct"], "seconds": record["elapsed_seconds"], "failure_type": record["failure_type"]}), flush=True)
    verify()
    summarize()


if __name__ == "__main__":
    operation = sys.argv[1] if len(sys.argv) > 1 else "summary"
    if operation == "freeze":
        print(json.dumps({k: v for k, v in freeze().items() if k in ("experiment_id", "expected_trials", "frozen_at")}))
    elif operation == "run":
        execute()
    elif operation == "verify":
        print(verify()["experiment_id"] + ": frozen hashes, image and model verified")
    elif operation == "summary":
        result = summarize()
        print(json.dumps({k: result[k] for k in ("observed_trials", "missing_trials", "arms")}))
    else:
        raise SystemExit("Use freeze, verify, run or summary")
