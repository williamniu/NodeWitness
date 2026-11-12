"""Run terminal-task trials and keep every record, including failures.

  python3 -m terminal_env.cli run --task incident-p95 --agent oracle --seed 101
  python3 -m terminal_env.cli suite --agent qwen --seeds 101 202 303
"""

import argparse
import datetime
import json
import time
import uuid
from pathlib import Path

from . import VERSION
from .agents import Ollama, run_model
from .runner import BUDGET, TASK_IDS, TerminalEnvironment, run_nothing, run_oracle
from .verifier import VERSION as VERIFIER_VERSION

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "outputs/terminal/trials"


MODELS = {"qwen": "william-qwen38-agent:latest", "qwen38": "william-qwen38-agent:latest",
          "qwen36": "william-qwen3.6:latest"}


def make_adapter(agent):
    if agent not in MODELS:
        raise ValueError("Unknown model agent: " + agent)
    return Ollama(model=MODELS[agent])


def provenance():
    """What exactly ran: commit, whether terminal_env differs from it, and hashes of task code."""
    import hashlib
    import subprocess
    files = sorted(p for p in (ROOT / "terminal_env").rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    run = lambda *args: subprocess.run(args, cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return {"git_commit": run("git", "rev-parse", "HEAD"),
            "terminal_env_dirty": bool(run("git", "status", "--porcelain", "--", "terminal_env")),
            "terminal_env_digest": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()}


WORKSPACES = ROOT / "outputs/terminal/workspaces"


def save_workspace(env, run_id, record):
    """Keep the graded /workspace so a fixed grader can regrade the exact same bytes later."""
    import gzip
    try:
        if env.workspace_tar is None and env.sandbox:
            env.workspace_tar = env.sandbox.get()
        if env.workspace_tar:
            WORKSPACES.mkdir(parents=True, exist_ok=True)
            path = WORKSPACES / (run_id + ".tar.gz")
            path.write_bytes(gzip.compress(env.workspace_tar, mtime=0))
            record["workspace_archive"] = str(path.relative_to(ROOT))
    except Exception as exc:
        record["errors"].append({"kind": "WorkspaceArchiveError", "detail": str(exc)[:500]})


def regrade(run_id):
    """Grade a saved workspace again with the current verifier; the original verdict is kept."""
    import gzip
    from .runner import IMAGE, _load
    from .verifier import verify
    path = OUTPUT / (run_id + ".json")
    record = json.loads(path.read_text())
    tar = gzip.decompress((ROOT / record["workspace_archive"]).read_bytes())
    verdict = verify(_load(record["task"]), record["seed"], tar, IMAGE)
    record.setdefault("regrades", []).append({"at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                              "provenance": provenance(), "verifier": verdict})
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n")
    temporary.replace(path)
    print(json.dumps({"run_id": run_id, "original": record.get("status"), "regraded_passed": verdict["passed"],
                      "grader_exception": verdict.get("grader_exception")}))


def trial(task_id, agent, seed, experiment=None):
    run_id = "%s-%s-%d-%s" % (task_id, agent.replace(":", "_").replace("/", "_"), seed, uuid.uuid4().hex[:8])
    record = {"schema": "nw.terminal-trial@1", "run_id": run_id, "task": task_id, "agent": agent, "seed": seed,
              "experiment_id": experiment, "environment_version": VERSION, "verifier_version": VERIFIER_VERSION,
              "budgets": BUDGET, "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "provenance": provenance(),
              "errors": [], "events": []}
    env = TerminalEnvironment(task_id)
    started = time.monotonic()
    try:
        if agent == "oracle":
            env.reset(seed)
            run_oracle(env)
        elif agent == "nothing":
            env.reset(seed)
            run_nothing(env)
        else:
            adapter = make_adapter(agent)
            record["model"] = adapter.metadata()
            record["events"] = run_model(env, adapter, seed)
        record["verifier"] = env.verify()
        record["status"] = "passed" if record["verifier"]["passed"] else "failed"
        if env.reason == "model_error" or record["verifier"].get("grader_exception"):
            # Provider failures and grader crashes are counted separately, never as a pass or a fail.
            record["status"] = "error"
    except Exception as exc:
        record["status"] = "error"
        record["errors"].append({"kind": type(exc).__name__, "detail": str(exc)[:2000]})
    finally:
        save_workspace(env, run_id, record)
        record["steps"] = getattr(env, "steps", [])
        record["termination"] = {"terminated": getattr(env, "terminated", False), "truncated": getattr(env, "truncated", False),
                                 "reason": getattr(env, "reason", None)}
        env.close()
        record["duration_seconds"] = round(time.monotonic() - started, 2)
        OUTPUT.mkdir(parents=True, exist_ok=True)
        temporary = OUTPUT / (run_id + ".json.tmp")
        temporary.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n")
        temporary.replace(OUTPUT / (run_id + ".json"))  # atomic: readers never see half a file
    print(json.dumps({"run_id": run_id, "status": record["status"], "steps": len(record["steps"]),
                      "seconds": record["duration_seconds"],
                      "failed_checks": [k for k, v in record.get("verifier", {}).get("checks", {}).items() if not v["passed"]]}),
          flush=True)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--task", choices=TASK_IDS, required=True)
    run.add_argument("--agent", default="oracle")
    run.add_argument("--seed", type=int, default=101)
    suite = sub.add_parser("suite")
    suite.add_argument("--agent", required=True)
    suite.add_argument("--seeds", type=int, nargs="+", default=[101, 202, 303])
    suite.add_argument("--tasks", nargs="+", default=TASK_IDS, choices=TASK_IDS)
    suite.add_argument("--experiment")
    again = sub.add_parser("regrade")
    again.add_argument("run_id")
    args = parser.parse_args()
    if args.command == "regrade":
        return regrade(args.run_id)
    if args.command == "run":
        raise SystemExit(0 if trial(args.task, args.agent, args.seed)["status"] == "passed" else 1)
    for seed in args.seeds:
        for task_id in args.tasks:
            trial(task_id, args.agent, seed, args.experiment)


if __name__ == "__main__":
    main()
