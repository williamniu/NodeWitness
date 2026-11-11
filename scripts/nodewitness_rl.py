"""Run the local NodeWitness reward controls and tabular learning experiment."""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from random import Random
import re
import time

import gymnasium
from gymnasium.utils.env_checker import check_env

from agent_env import VERSION
from agent_env.cli import image_identity, write_json
from agent_env.runner import BUDGET
from agent_env.verifier import VERSION as VERIFIER_VERSION
from scripts.nodewitness_gym import Action, CASES, RepairEnv

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs/nwrl"
VIEW = ROOT / "public/demo/agent-rl"
TRAIN_SEEDS = tuple(range(1011, 1023))
TEST_SEEDS = tuple(range(2011, 2015))
EXPLORATION_SEED = 204
BASELINE_SEED = 61
SETUP = (
    Action.HEALTH, Action.DIAGNOSE, Action.READ_DEFAULT,
    Action.READ_OVERRIDE, Action.READ_SOURCE, Action.READ_LOCK,
)
REPAIRS = (Action.EDIT_DEFAULT, Action.EDIT_OVERRIDE, Action.ESCALATE)
LIMITS = (
    "Two synthetic task variants. Held-out seeds vary source data within those variants. "
    "The tabular policy learns two decisions; evidence collection and submission are scripted."
)


def read_json(path):
    return json.loads(path.read_text())


def drive(env, take, choose, decisions):
    """Collect routine evidence, delegate two decisions to the policy, then submit."""
    def decide(state, actions):
        action = choose(state, actions)
        decisions.append((state, action))
        return action

    for action in SETUP:
        observation = take(action)
        if not env.active:
            return
    context = (observation["operator_lock"], observation["default_route"], observation["override_route"])
    edit = decide(("response", *context), REPAIRS)
    take(edit)
    if not env.active:
        return
    read, submit = {
        Action.EDIT_DEFAULT: (Action.READ_DEFAULT, Action.SUBMIT_DEFAULT),
        Action.EDIT_OVERRIDE: (Action.READ_OVERRIDE, Action.SUBMIT_OVERRIDE),
    }[edit]
    take(read)
    if not env.active:
        return
    finish = decide(("finish", *context, edit.name), (Action.DIAGNOSE, submit))
    take(finish)
    if env.active:
        take(submit)


def episode(path, case, seed, phase, choose, image, *, label=None, step_limit=BUDGET["tool_calls"]):
    run_id = f"{case.lower()}-{phase}-{seed}"
    env = RepairEnv(case, image=image, step_limit=step_limit)
    transitions, decisions, errors = {}, [], []
    started = time.monotonic()
    initial = None

    def take(action):
        previous = len(env.task.steps)
        observation, reward, terminated, truncated, _ = env.step(action)
        if len(env.task.steps) > previous:
            transitions[previous] = {
                "action_id": int(action), "observation": observation,
                "reward": reward, "terminated": terminated, "truncated": truncated,
            }
        return observation

    try:
        env.reset(seed=seed)
        initial = env.task.initial_digest
        drive(env, take, choose, decisions)
    except Exception as exc:
        errors.append({"layer": "infrastructure", "kind": type(exc).__name__, "detail": str(exc)})
    finally:
        try:
            env.close()
        except Exception as exc:
            errors.append({"layer": "cleanup", "kind": type(exc).__name__, "detail": str(exc)})

    task = env.task
    verdict = env.verdict
    status = (
        "blocked" if errors else "truncated" if task.truncated
        else "completed" if verdict and verdict["reward"] == 1 else "failed"
    )
    record = {
        "run_id": run_id, "scenario_id": case, "agent": phase, "label": label,
        "status": status, "seed": seed, "image_id": image, "step_limit": step_limit,
        "presentation": "Recorded RL episode",
        "data_origin": "Synthetic service and data; actual tool and HTTP calls",
        "environment_version": f"{VERSION} / Gymnasium adapter v1",
        "verifier_version": VERIFIER_VERSION,
        "initial_state_digest": initial,
        "steps": [
            {**step, "transition": transitions.get(i)} for i, step in enumerate(getattr(task, "steps", []))
        ],
        "termination": {
            "terminated": getattr(task, "terminated", False), "truncated": getattr(task, "truncated", False),
            "reason": "infrastructure_error" if errors else task.reason,
        },
        "errors": errors, "verifier": verdict,
        "tool_calls": len(getattr(task, "steps", [])),
        "duration_seconds": round(time.monotonic() - started, 2),
        "decisions": [{"state": state, "action": action.name} for state, action in decisions],
    }
    write_json(path / "trials" / f"{run_id}.json", record)
    reward = verdict["reward"] if verdict is not None and not errors else "unscored"
    print(f"{run_id}: {status} · reward {reward}", flush=True)
    return record, decisions


def compare_replay(path, record):
    env = RepairEnv(record["scenario_id"], image=record["image_id"], step_limit=record["step_limit"])
    try:
        env.reset(seed=record["seed"])
        initial_equal = env.task.initial_digest == record["initial_state_digest"]
        steps_equal = True
        for step in record["steps"]:
            transition = step["transition"]
            observation, reward, terminated, truncated, info = env.step(transition["action_id"])
            steps_equal &= (
                info["tool_observation"] == step["observation"]
                and (observation, reward, terminated, truncated)
                == (transition["observation"], transition["reward"], transition["terminated"], transition["truncated"])
            )
        final_equal = env.verdict["state_digest"] == record["verifier"]["state_digest"]
        reward_equal = env.verdict["reward"] == record["verifier"]["reward"]
        record["replay"] = {
            "passed": initial_equal and steps_equal and final_equal and reward_equal,
            "initial_state_equal": initial_equal, "transitions_equal": steps_equal,
            "final_state_equal": final_equal, "reward_equal": reward_equal,
        }
        write_json(path / "trials" / f"{record['run_id']}.json", record)
        return record["replay"]["passed"]
    finally:
        env.close()


def scripted(edit, verify=True):
    return lambda state, actions: edit if state[0] == "response" else actions[0 if verify else 1]


def check(path):
    path.mkdir(parents=True, exist_ok=False)
    image = image_identity()
    write_json(path / "experiment.json", {
        "id": path.name, "image_id": image, "gymnasium": gymnasium.__version__,
        "cases": CASES, "train_seeds": TRAIN_SEEDS, "held_out_seeds": TEST_SEEDS,
        "exploration_seed": EXPLORATION_SEED, "baseline_seed": BASELINE_SEED,
    })
    env = RepairEnv("E03", image=image)
    try:
        check_env(env, skip_render_check=True, skip_close_check=True)
        env.reset(seed=TEST_SEEDS[0])
        initial, old_container = env.task.initial_digest, env.task.container
        env.step(Action.EDIT_OVERRIDE)
        assert env.task.state()["files"]["override.json"] != env.task.case["files"]["override.json"]
        env.reset(seed=TEST_SEEDS[0])
        assert env.task.initial_digest == initial and env.task.container != old_container
    finally:
        env.close()
        env.close()

    controls = [
        ("E03", "wrong-edit", "Wrong file", scripted(Action.EDIT_DEFAULT), 0),
        ("E03", "unchecked", "Repair without diagnostic", scripted(Action.EDIT_OVERRIDE, False), 0),
        ("E03", "verified", "Verified override repair", scripted(Action.EDIT_OVERRIDE), 1),
        ("E05", "escalated", "Supported escalation", scripted(Action.ESCALATE), 1),
    ]
    for case, phase, label, policy, reward in controls:
        record, _ = episode(path, case, TEST_SEEDS[0], phase, policy, image, label=label)
        assert record["status"] != "blocked" and record["termination"]["terminated"]
        assert not record["termination"]["truncated"] and record["verifier"]["reward"] == reward
        if phase == "verified":
            assert compare_replay(path, record), "Same actions did not reproduce the verified repair"

    cutoff, _ = episode(path, "E03", TEST_SEEDS[0], "cutoff", scripted(Action.EDIT_OVERRIDE), image,
                        label="Step budget cutoff", step_limit=2)
    assert cutoff["status"] == "truncated" and cutoff["termination"]["reason"] == "step_budget"
    assert not cutoff["termination"]["terminated"] and cutoff["verifier"] is None
    write_json(path / "checks.json", {"gymnasium": "passed", "reset": "passed",
                                     "controls": "passed", "replay": "passed", "cutoff": "passed"})
    print("Gymnasium API, reset, reward controls, replay, and cutoff passed.", flush=True)


def train(path):
    if not (path / "checks.json").is_file():
        raise RuntimeError("Run the environment checks before learning")
    freeze = read_json(path / "experiment.json")
    image = freeze["image_id"]
    with (path / "learning-started").open("x"):
        pass
    counts, returns = defaultdict(int), defaultdict(float)
    explore = Random(freeze["exploration_seed"])

    def sample(state, actions):
        least = min(counts[state, action] for action in actions)
        return explore.choice([action for action in actions if counts[state, action] == least])

    for seed in freeze["train_seeds"]:
        for case in freeze["cases"]:
            record, decisions = episode(path, case, seed, "training", sample, image, label="Training episode")
            if record["status"] in {"completed", "failed"} and record["verifier"] is not None:
                for state, action in decisions:
                    counts[state, action] += 1
                    returns[state, action] += record["verifier"]["reward"]

    write_json(path / "policy.json", [
        {"state": state, "action": action.name, "episodes": count, "mean_return": returns[state, action] / count}
        for (state, action), count in counts.items() if count
    ])

    def learned(state, actions):
        return max(actions, key=lambda action: returns[state, action] / max(1, counts[state, action]))

    random_policy = Random(freeze["baseline_seed"])
    for phase, policy, label in (
        ("initial", lambda state, actions: random_policy.choice(actions), "Initial policy"),
        ("learned", learned, "Learned policy"),
    ):
        for seed in freeze["held_out_seeds"]:
            for case in freeze["cases"]:
                record, _ = episode(path, case, seed, phase, policy, image, label=label)
                if phase == "learned" and case == "E03" and seed == freeze["held_out_seeds"][0] and record["status"] == "completed":
                    if not compare_replay(path, record):
                        raise RuntimeError("The learned repair did not replay")

    export(path, freeze)


def export(path, freeze):
    records = [read_json(file) for file in sorted((path / "trials").glob("*.json"))]
    phase_groups = {}
    for phase in ("training", "initial", "learned"):
        runs = [run for run in records if run["agent"] == phase]
        phase_groups[phase] = {
            "planned": len(freeze["cases"]) * len(freeze["train_seeds" if phase == "training" else "held_out_seeds"]),
            "recorded": len(runs),
            "passed": sum(run["status"] == "completed" for run in runs),
            "scored": sum(run["status"] in {"completed", "failed"} for run in runs),
            "truncated": sum(run["status"] == "truncated" for run in runs),
            "blocked": sum(run["status"] == "blocked" for run in runs),
            "by_case": {
                case: {"passed": sum(run["status"] == "completed" and run["scenario_id"] == case for run in runs),
                       "recorded": sum(run["scenario_id"] == case for run in runs)}
                for case in freeze["cases"]
            },
        }
    highlight = [next(run["run_id"] for run in records if run["agent"] == phase)
                 for phase in ("wrong-edit", "unchecked", "verified", "escalated", "cutoff")]
    ids = set(highlight)
    visible = [next(run for run in records if run["run_id"] == run_id) for run_id in highlight]
    visible.extend(run for run in records if run["agent"] in {"initial", "learned"} and run["run_id"] not in ids)
    manifest = {
        "experiment_id": path.name, "verification_date": datetime.now(timezone.utc).date().isoformat(),
        "groups": phase_groups, "limits": LIMITS, "gymnasium": freeze["gymnasium"],
        "runs": [{key: run[key] for key in (
            "run_id", "scenario_id", "agent", "status", "label", "tool_calls", "duration_seconds",
        )} for run in visible],
    }
    write_json(path / "summary.json", manifest)
    destination = VIEW / path.name
    destination.mkdir(parents=True, exist_ok=False)
    for run in visible:
        safe_run = {**run, "errors": [{"layer": err["layer"], "kind": err["kind"]} for err in run["errors"]]}
        write_json(destination / f"{run['run_id']}.json", safe_run)
    write_json(VIEW / "manifest.json", {**manifest, "trace_directory": path.name})
    print(json.dumps(phase_groups, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "train"))
    parser.add_argument("experiment", help="New versioned local experiment identifier")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,59}", args.experiment):
        parser.error("Use a lowercase experiment ID of 3–60 characters")
    (check if args.command == "check" else train)(OUTPUT / args.experiment)


if __name__ == "__main__":
    main()
