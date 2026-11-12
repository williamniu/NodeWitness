"""Host-side verifier for terminal tasks.

The agent's /workspace arrives as tar bytes. It is loaded into a fresh, equally hardened container
that never ran agent processes, so background jobs, shell state and PATH tricks from the episode
do not carry over. Hidden inputs go to /tmp/hidden in that container only. Each task's
`check(sandbox, seed)` runs the agent's artifacts there and compares raw outputs with values the
host computes from the seed. Expected values never enter any container.
"""

import hashlib

from .runner import Sandbox, tar_bytes

VERSION = "nw-terminal-verifier@2"


def verify(task, seed, workspace_tar, image):
    sandbox = Sandbox(image, "verify").start()
    try:
        sandbox.put(workspace_tar)
        hidden = task.hidden_inputs(seed) if hasattr(task, "hidden_inputs") else {}
        if hidden:
            sandbox.put(tar_bytes(hidden, prefix="hidden/"), dest="/tmp")
        try:
            checks = task.check(sandbox, seed)
            grader_exception = None
        except Exception as exc:  # agent bytes must never crash grading silently; surface it instead
            grader_exception = type(exc).__name__ + ": " + str(exc)[:500]
            checks = {"grader_exception": {"passed": False, "error": grader_exception}}
    finally:
        sandbox.close()
    passed = bool(checks) and all(row["passed"] for row in checks.values())
    return {"version": VERSION, "task": task.ROOT.name, "seed": seed, "passed": passed,
            "reward": int(passed), "checks": checks, "grader_exception": grader_exception,
            "workspace_sha256": hashlib.sha256(workspace_tar).hexdigest()}
