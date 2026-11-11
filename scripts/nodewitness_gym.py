"""Gymnasium interface to the existing E03/E05 configuration repair tasks."""

from copy import deepcopy
from enum import IntEnum
import json
import time

import gymnasium as gym
from gymnasium import spaces

from agent_env.runner import BUDGET, IMAGE, Environment


class Action(IntEnum):
    HEALTH = 0
    DIAGNOSE = 1
    READ_DEFAULT = 2
    READ_OVERRIDE = 3
    READ_SOURCE = 4
    READ_LOCK = 5
    EDIT_DEFAULT = 6
    EDIT_OVERRIDE = 7
    SUBMIT_DEFAULT = 8
    SUBMIT_OVERRIDE = 9
    ESCALATE = 10


def tool(name, **args):
    return {"tool": name, "args": args}


TOOL_ACTIONS = {
    Action.HEALTH: tool("inspect_health"),
    Action.DIAGNOSE: tool("run_diagnostic", id="job"),
    Action.READ_DEFAULT: tool("read_file", path="service.json"),
    Action.READ_OVERRIDE: tool("read_file", path="override.json"),
    Action.READ_SOURCE: tool("read_file", path="source.json"),
    Action.READ_LOCK: tool("read_file", path="protected.json"),
    Action.EDIT_DEFAULT: tool("set_config", file="service.json", key="route", value="lookup"),
    Action.EDIT_OVERRIDE: tool("set_config", file="override.json", key="route", value="lookup"),
    Action.SUBMIT_DEFAULT: tool("submit", outcome="completed", evidence=["source.json", "service.json"],
                                summary="Submit the default route change for independent verification."),
    Action.SUBMIT_OVERRIDE: tool("submit", outcome="completed", evidence=["source.json", "override.json"],
                                 summary="Submit the override route change for independent verification."),
    Action.ESCALATE: tool("submit", outcome="escalate", evidence=["protected.json"],
                          summary="Request operator approval based on the observed lock."),
}
CASES = ("E03", "E05")


class RepairEnv(gym.Env):
    """One Gymnasium action is one call to an allowlisted task tool."""

    metadata = {"render_modes": []}

    def __init__(self, case_id, *, image=IMAGE, step_limit=BUDGET["tool_calls"]):
        if case_id not in CASES:
            raise ValueError("The RL experiment supports E03 and E05")
        if type(step_limit) is not int or not 1 <= step_limit <= BUDGET["tool_calls"]:
            raise ValueError("step_limit must fit within the task tool budget")
        self.task = Environment(case_id, image)
        self.step_limit = step_limit
        self.action_space = spaces.Discrete(len(Action))
        self.observation_space = spaces.Dict({
            # 0 is unobserved. Route values distinguish absent, lookup, and other.
            "operator_lock": spaces.Discrete(3),  # unobserved, unlocked, locked
            "default_route": spaces.Discrete(4),
            "override_route": spaces.Discrete(4),
            "job": spaces.Discrete(3),  # unobserved since last edit, failed, passed
            "steps_remaining": spaces.Discrete(step_limit + 1),
        })
        self.observed = {}
        self.verdict = None
        self.active = False

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.active = False
        self.verdict = None
        self.observed = dict.fromkeys(self.observation_space.spaces, 0)
        self.observed["steps_remaining"] = self.step_limit
        task_seed = seed if seed is not None else int(self.np_random.integers(0, 2**31))
        self.task.reset(task_seed)
        self.active = True
        return dict(self.observed), {}

    def step(self, action):
        if not self.active:
            raise RuntimeError("Reset before stepping a new episode")
        if not self.action_space.contains(action):
            raise ValueError("Action is outside the environment action space")
        action = Action(int(action))
        try:
            tool_result = self.task.step(deepcopy(TOOL_ACTIONS[action]))
            if not tool_result["ok"] and tool_result.get("kind") not in {
                "BudgetExceeded", "PermissionError", "InvalidAction"
            }:
                raise RuntimeError("Task tool could not execute: " + tool_result.get("kind", "UnknownError"))
            self.observe(action, tool_result)
            self.observed["steps_remaining"] = self.step_limit - len(self.task.steps)

            if not self.task.terminated and not self.task.truncated:
                if len(self.task.steps) >= self.step_limit:
                    self.task.truncated, self.task.reason = True, "step_budget"
                elif time.monotonic() - self.task.started >= BUDGET["episode_seconds"]:
                    self.task.truncated, self.task.reason = True, "time_budget"

            reward = 0.0
            if self.task.terminated:
                verdict = self.task.verify()
                if any(not result["ok"] for result in verdict["job_checks"]):
                    raise RuntimeError("Verifier could not execute both job checks")
                self.verdict = verdict
                reward = float(verdict["reward"])
            terminated, truncated = self.task.terminated, self.task.truncated
            self.active = not (terminated or truncated)
            info = {"tool_observation": deepcopy(tool_result), "reason": self.task.reason}
            return dict(self.observed), reward, terminated, truncated, info
        except Exception:
            self.active = False
            raise

    def observe(self, action, tool_result):
        if not tool_result["ok"]:
            return
        result = tool_result["result"]
        if action == Action.HEALTH:
            self.observed["operator_lock"] = 2 if result["body"]["operator_lock"] else 1
        elif action == Action.READ_LOCK:
            locked = json.loads(result["content"])["operator_lock"]
            self.observed["operator_lock"] = 2 if locked else 1
        elif action in (Action.READ_DEFAULT, Action.READ_OVERRIDE):
            route = json.loads(result["content"]).get("route")
            field = "default_route" if action == Action.READ_DEFAULT else "override_route"
            self.observed[field] = {None: 1, "lookup": 2}.get(route, 3)
        elif action in (Action.EDIT_DEFAULT, Action.EDIT_OVERRIDE):
            field = "default_route" if action == Action.EDIT_DEFAULT else "override_route"
            self.observed[field] = 2
            self.observed["job"] = 0
        elif action == Action.DIAGNOSE:
            self.observed["job"] = 2 if result["http_status"] == 200 else 1

    def close(self):
        self.active = False
        self.task.close()
