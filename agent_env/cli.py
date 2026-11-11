"""CLI for actual container trials, frozen experiments, exports, and action replay."""

import argparse
import datetime
import hashlib
import json
import re
import time
import uuid
from pathlib import Path

from . import VERSION
from .adapters import MODEL, PROMPT_VERSION, SYSTEM, TOOLS, Qwen
from .cases import CASES, TASK_VERSION
from .runner import BUDGET, IMAGE, ROOT, Environment, command, digest, reference_actions
from .verifier import VERSION as VERIFIER_VERSION

OUTPUT = ROOT / "outputs/nw001"


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def source_identity():
    paths = list((ROOT / "agent_env").rglob("*.py")) + [ROOT / "agent_env/environment/Dockerfile"]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    return {"base_commit": command(["git", "rev-parse", "HEAD"]),
            "task_files": hashes, "task_source_digest": digest(hashes),
            "working_tree": "task source identified by file hashes; pre-existing unrelated changes retained"}


def image_identity():
    return json.loads(command(["docker", "image", "inspect", IMAGE]))[0]["Id"]


def replay(record):
    env = Environment(record["scenario_id"], record["image_id"])
    try:
        env.reset(record["seed"])
        initial_equal = env.initial_digest == record["initial_state_digest"]
        observations_equal = True
        for step in record["steps"]:
            observation = env.step(step["action"])
            observations_equal &= digest(observation) == digest(step["observation"])
        verdict = env.verify()
        return {"kind": "same_action_replay", "initial_state_equal": initial_equal,
                "observations_equal": bool(observations_equal),
                "final_state_equal": verdict["state_digest"] == record["verifier"]["state_digest"],
                "reward_equal": verdict["reward"] == record["verifier"]["reward"],
                "passed": bool(initial_equal and observations_equal and verdict["state_digest"] == record["verifier"]["state_digest"] and verdict["reward"] == record["verifier"]["reward"])}
    finally:
        env.close()


def trial(case_id, agent, seed, image, experiment=None):
    run_id = case_id.lower() + "-" + agent + "-" + uuid.uuid4().hex[:10]
    path = OUTPUT / "trials" / (run_id + ".json")
    record = {"schema": "nw.trial@1", "run_id": run_id, "scenario_id": case_id,
              "split": CASES[case_id]["split"], "agent": agent, "seed": seed,
              "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "environment_version": VERSION, "task_version": TASK_VERSION,
              "prompt_version": PROMPT_VERSION, "verifier_version": VERIFIER_VERSION,
              "source": source_identity(), "image_id": image, "budgets": BUDGET,
              "experiment_id": experiment, "model_events": [], "errors": [],
              "status": "running", "steps": [], "human_review": "pending"}
    env = Environment(case_id, image)
    started = time.monotonic()
    try:
        observation = env.reset(seed)
        record["initial_state_digest"] = env.initial_digest
        if agent == "baseline":
            record["model"] = {"adapter": "scripted-reference@1", "model": None}
            reference_actions(env)
        else:
            adapter = Qwen()
            record["model"] = adapter.metadata()
            messages = [{"role": "system", "content": SYSTEM},
                        {"role": "user", "content": json.dumps(observation)}]
            for decision in range(BUDGET["decisions"]):
                if env.terminated or env.truncated:
                    break
                if env.remaining() <= 0.2:
                    env.truncated, env.reason = True, "episode_time_budget"
                    break
                try:
                    event = adapter.decide(messages, seed, min(BUDGET["model_seconds"], env.remaining()))
                    record["model_events"].append({"decision": decision, **event})
                    write_json(path, {**record, "steps": env.steps})
                    if event.get("error"):
                        raise RuntimeError(str(event["error"]))
                    message = event["message"]
                    messages.append(message)
                    calls = message.get("tool_calls", [])
                    if len(calls) != 1:
                        record["errors"].append({"layer": "agent", "kind": "InvalidModelOutput", "decision": decision,
                                                 "detail": "Exactly one tool call was required; no action was executed"})
                        messages.append({"role": "user", "content": "Invalid output: call exactly one supplied tool. Finish using submit; do not fabricate results."})
                        continue
                    function = calls[0].get("function", {})
                    args = function.get("arguments", {})
                    if isinstance(args, str):
                        args = json.loads(args)
                    action = {"tool": function.get("name"), "args": args}
                    result = env.step(action)
                    messages.append({"role": "tool", "tool_name": function.get("name"), "content": json.dumps(result)})
                except (OSError, ValueError, RuntimeError) as exc:
                    detail = str(exc)
                    if hasattr(exc, "read"):
                        detail += " " + exc.read(4000).decode(errors="replace")
                    record["errors"].append({"layer": "agent", "kind": type(exc).__name__, "detail": detail[:4500]})
                    env.truncated, env.reason = True, "model_error"
                    break
            if not env.terminated and not env.truncated:
                env.truncated, env.reason = True, "decision_budget"
        try:
            record["verifier"] = env.verify()
        except Exception as exc:
            record["errors"].append({"layer": "verifier", "kind": type(exc).__name__, "detail": str(exc)[:2000]})
            raise
        record["steps"] = env.steps
        record["termination"] = {"terminated": env.terminated, "truncated": env.truncated, "reason": env.reason}
        record["status"] = "completed" if record["verifier"]["compliant_completion"] else "failed"
    except Exception as exc:
        record["status"] = "blocked"
        record["steps"] = getattr(env, "steps", [])
        record["errors"].append({"layer": "infrastructure", "kind": type(exc).__name__, "detail": str(exc)[:2500]})
    finally:
        try:
            env.close()
        except RuntimeError:
            record["cleanup_error"] = env.cleanup_error
            record["status"] = "blocked"
        record["duration_seconds"] = round(time.monotonic() - started, 3)
        record["tool_calls"] = len(record["steps"])
        for key in ("prompt_eval_count", "eval_count"):
            values = [event["usage"].get(key) for event in record["model_events"] if event["usage"].get(key) is not None]
            record[key] = sum(values) if values else None
        write_json(path, record)
    if "verifier" in record:
        try:
            record["replay"] = replay(record)
        except Exception as exc:
            record["replay"] = {"passed": False, "error": str(exc)[:1000]}
        write_json(path, record)
    print(json.dumps({"run_id": run_id, "status": record["status"],
                      "reward": record.get("verifier", {}).get("reward"),
                      "replay": record.get("replay", {}).get("passed"), "path": str(path)}, ensure_ascii=False), flush=True)
    return record


def freeze(name):
    path = OUTPUT / "experiments" / name / "manifest.json"
    if path.exists():
        raise ValueError("Experiment already exists; use a new identifier")
    manifest = {"experiment_id": name, "status": "frozen", "source": source_identity(),
                "image_id": image_identity(), "model": Qwen().metadata(), "budgets": BUDGET,
                "prompt_digest": digest({"system": SYSTEM, "tools": TOOLS}),
                "cases_digest": digest(CASES), "case_ids": [case for case in CASES if case.startswith("E")],
                "seeds": [101, 202, 303], "planned_qwen_trials": 18,
                "planned_baseline_trials": 6, "codex_trials": "as needed; distinct counts",
                "human_review": "pending"}
    manifest["manifest_digest"] = digest(manifest)
    write_json(path, manifest)
    print(str(path))


def suite(name, agent):
    path = OUTPUT / "experiments" / name / "manifest.json"
    manifest = json.loads(path.read_text())
    frozen_digest = manifest.pop("manifest_digest")
    if digest(manifest) != frozen_digest:
        raise ValueError("Frozen experiment manifest was modified")
    manifest["manifest_digest"] = frozen_digest
    if manifest["source"] != source_identity() or manifest["prompt_digest"] != digest({"system": SYSTEM, "tools": TOOLS}):
        raise ValueError("Frozen source/prompt changed. Preserve this experiment and freeze a new version.")
    if agent == "qwen" and Qwen().metadata() != manifest["model"]:
        raise ValueError("Frozen model/runtime changed")
    seeds = manifest["seeds"] if agent == "qwen" else manifest["seeds"][:1]
    existing = [json.loads(p.read_text()) for p in (OUTPUT / "trials").glob("*.json")]
    for case_id in manifest["case_ids"]:
        for seed in seeds:
            if any(r.get("experiment_id") == name and r["agent"] == agent and r["scenario_id"] == case_id and r["seed"] == seed for r in existing):
                print("Preserving existing slot " + case_id + "/" + str(seed), flush=True)
                continue
            record = trial(case_id, agent, seed, manifest["image_id"], name)
            existing.append(record)
            if record.get("verifier", {}).get("engineering_failure") or record.get("cleanup_error"):
                raise RuntimeError("Hard engineering failure; stop affected experiment")


def report(name):
    manifest = json.loads((OUTPUT / "experiments" / name / "manifest.json").read_text())
    records = [json.loads(p.read_text()) for p in (OUTPUT / "trials").glob("*.json")]
    records = [r for r in records if r.get("experiment_id") == name]
    result = {"experiment": manifest, "groups": {}, "human_review": "pending",
              "codex_backup": {"trials": 0, "status": "not used", "reason": "Qwen primary; native host-tool confinement has not been verified"},
              "limits": "Six cases in one environment family; no unseen generalization, production reliability, or RL training claim."}
    for agent, planned in [("qwen", 18), ("baseline", 6)]:
        rows = [r for r in records if r["agent"] == agent]
        verified = [r for r in rows if "verifier" in r]
        counts = {status: sum(r["status"] == status for r in rows) for status in ("completed", "failed", "blocked", "running")}
        cases = {case: [{"run_id": r["run_id"], "seed": r["seed"], "status": r["status"],
                         "task_completion": r.get("verifier", {}).get("task_completion"),
                         "compliant_completion": r.get("verifier", {}).get("compliant_completion"),
                         "reward": r.get("verifier", {}).get("reward"), "replay": r.get("replay", {}).get("passed")}
                        for r in rows if r["scenario_id"] == case] for case in manifest["case_ids"]}
        result["groups"][agent] = {"planned": planned, "recorded": len(rows), **counts,
                                   "not_run": planned - len(rows),
                                   "verified_trials": len(verified), "unverified_trials": len(rows) - len(verified),
                                   "metric_coverage": "Verdict/effect counts cover verified_trials; missing verifier results are unknown, not zero.",
                                   "task_completions": sum(r.get("verifier", {}).get("task_completion", False) for r in rows),
                                   "compliant_completions": sum(r.get("verifier", {}).get("compliant_completion", False) for r in rows),
                                   "unauthorized_attempts": sum(r.get("verifier", {}).get("unauthorized_attempts", 0) for r in rows),
                                   "actual_unauthorized_effects": sum(r.get("verifier", {}).get("actual_unauthorized_effects", 0) for r in rows),
                                   "three_of_three_cases": sum(len(v) == 3 and all(r["compliant_completion"] for r in v) for v in cases.values()) if agent == "qwen" else None,
                                   "evidence_valid_and_fresh": sum(r["verifier"]["evidence_valid_and_fresh"] for r in verified),
                                   "replays_passed": sum(r.get("replay", {}).get("passed", False) for r in rows),
                                   "tool_calls": sum(r.get("tool_calls", 0) for r in rows),
                                   "valid_actions": sum(len(r.get("steps", [])) - r.get("verifier", {}).get("invalid_actions", 0) - r.get("verifier", {}).get("unauthorized_attempts", 0) for r in verified),
                                   "model_decisions": sum(len(r.get("model_events", [])) for r in rows),
                                   "invalid_model_outputs": sum(e["kind"] in {"InvalidModelOutput", "JSONDecodeError"} for r in rows for e in r["errors"]),
                                   "duration_seconds": round(sum(r.get("duration_seconds", 0) for r in rows), 3),
                                   "token_usage": {key: {"available_trials": sum(r.get(key) is not None for r in rows),
                                                         "observed_total": sum(r[key] for r in rows if r.get(key) is not None) if any(r.get(key) is not None for r in rows) else None}
                                                   for key in ("prompt_eval_count", "eval_count")},
                                   "recoverable_case": {"recorded": sum(r["scenario_id"] == "E04" for r in rows),
                                                        "completed": sum(r["scenario_id"] == "E04" and r.get("verifier", {}).get("compliant_completion", False) for r in rows)},
                                   "error_counts": {layer: sum(e["layer"] == layer for r in rows for e in r["errors"]) +
                                                     sum(not s["observation"]["ok"] and ("infrastructure" if s["observation"].get("kind") == "InfrastructureError" else "tool") == layer for r in rows for s in r.get("steps", []))
                                                    for layer in ("agent", "tool", "verifier", "infrastructure")},
                                   "cases": cases}
    write_json(OUTPUT / "experiments" / name / "report.json", result)
    return result


def export(name):
    result = report(name)
    destination = ROOT / "public/demo/agent-env"
    runs = []
    for path in sorted((OUTPUT / "trials").glob("*.json")):
        row = json.loads(path.read_text())
        if row.get("experiment_id") != name:
            continue
        public = {key: row.get(key) for key in ("schema", "run_id", "scenario_id", "split", "agent", "seed", "model", "environment_version", "task_version", "prompt_version", "verifier_version", "image_id", "budgets", "status", "steps", "verifier", "replay", "termination", "tool_calls", "duration_seconds", "prompt_eval_count", "eval_count")}
        public["presentation"] = "recorded run, not live execution"
        public["data_origin"] = "purpose-built synthetic service/data; simulated downstream; real Qwen inference where labelled"
        # Raw provider responses, host paths, and private recordings stay in ignored outputs.
        public["errors"] = [{"layer": e["layer"], "kind": e["kind"]} for e in row["errors"]]
        write_json(destination / (row["run_id"] + ".json"), public)
        runs.append({key: public[key] for key in ("run_id", "scenario_id", "agent", "status", "tool_calls", "duration_seconds")})
    public_report = {"experiment_id": name, "source_digest": result["experiment"]["source"]["task_source_digest"],
                     "manifest_digest": result["experiment"]["manifest_digest"],
                     "groups": result["groups"], "human_review": "pending", "limits": result["limits"],
                     "runs": runs, "presentation": "recorded evidence", "verification_date": "2026-10-31"}
    write_json(destination / "manifest.json", public_report)
    print(json.dumps({"exported_runs": len(runs), "destination": str(destination)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    run = subs.add_parser("run")
    run.add_argument("--case", choices=CASES, required=True)
    run.add_argument("--agent", choices=["baseline", "qwen"], default="baseline")
    run.add_argument("--seed", type=int, default=101)
    for name in ("freeze", "suite", "report", "export"):
        sub = subs.add_parser(name)
        sub.add_argument("experiment")
        if name == "suite":
            sub.add_argument("--agent", choices=["baseline", "qwen"], required=True)
    replay_cmd = subs.add_parser("replay")
    replay_cmd.add_argument("path", type=Path)
    args = parser.parse_args()
    if hasattr(args, "experiment") and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", args.experiment):
        parser.error("Experiment identifier must be a simple task-local name")
    if args.command == "run":
        record = trial(args.case, args.agent, args.seed, image_identity())
        raise SystemExit(0 if record["status"] == "completed" else 1)
    if args.command == "freeze":
        freeze(args.experiment)
    elif args.command == "suite":
        suite(args.experiment, args.agent)
    elif args.command == "report":
        print(json.dumps(report(args.experiment)["groups"], indent=2))
    elif args.command == "export":
        export(args.experiment)
    elif args.command == "replay":
        print(json.dumps(replay(json.loads(args.path.read_text())), indent=2))


if __name__ == "__main__":
    main()
