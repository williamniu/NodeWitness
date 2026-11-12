"""Real-shell terminal tasks in a hardened container; grading happens outside it.

Rules (shared with agent_env):
- The agent container gets the shared HARDENING flags plus three tmpfs mounts. No bind mounts,
  no network, no Docker socket. Inference runs on the host and only sends shell commands.
- Task tests, oracle solutions, hidden inputs and expected values never enter the agent container.
- Verification copies /workspace out as bytes, loads it into a *fresh* verifier container that
  never ran agent processes, runs the agent's artifacts on hidden inputs there, and returns raw
  observations. All comparisons happen on the host against host-only expectations.
"""

import importlib.util
import io
import json
import subprocess
import tarfile
import time
import uuid
from pathlib import Path

from agent_env.runner import HARDENING, digest

IMAGE = "nodewitness-terminal:1"
TASKS_DIR = Path(__file__).resolve().parent / "tasks"
TASK_IDS = sorted(p.name for p in TASKS_DIR.iterdir() if (p / "task.py").exists())
BUDGET = {"tool_calls": 30, "command_seconds": 20, "output_chars": 6000, "episode_seconds": 900}
TMPFS = ["--tmpfs", "/workspace:rw,exec,nosuid,size=64m,uid=10001,gid=10001",
         "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m,uid=10001,gid=10001",
         "--tmpfs", "/home/agent:rw,noexec,nosuid,size=16m,uid=10001,gid=10001"]
TOOLS = {"bash": {"command": str}, "submit": {"summary": str}}


def _load(task_id):
    if task_id not in TASK_IDS:
        raise ValueError("Unknown terminal task: " + str(task_id))
    spec = importlib.util.spec_from_file_location("nw_term_" + task_id.replace("-", "_"), TASKS_DIR / task_id / "task.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = TASKS_DIR / task_id
    module.INSTRUCTION = (module.ROOT / "instruction.md").read_text()
    return module


def tar_bytes(files, prefix=""):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, content in sorted(files.items()):
            data = content.encode() if isinstance(content, str) else content
            info = tarfile.TarInfo(prefix + name)
            info.size, info.mode, info.mtime = len(data), 0o755 if name.endswith(".sh") else 0o644, 1767225600
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


class Sandbox:
    """One hardened container. Used for the agent episode and, separately, for verification."""

    def __init__(self, image=IMAGE, label="agent"):
        self.name = "nwterm-" + label + "-" + uuid.uuid4().hex[:12]
        self.image = image
        self.alive = False

    def start(self):
        self._run(["docker", "run", "-d", "--name", self.name, "--label", "nodewitness.task=terminal",
                   *HARDENING, *TMPFS, self.image], timeout=30)
        self.alive = True
        return self

    def _run(self, args, data=None, timeout=30):
        result = subprocess.run(args, input=data, capture_output=True, timeout=timeout, check=False)
        if result.returncode:
            raise RuntimeError(result.stderr.decode(errors="replace").strip()[:2000] or "docker command failed")
        return result.stdout

    def put(self, tar, dest="/workspace"):
        self._run(["docker", "exec", "-i", self.name, "tar", "-x", "-C", dest], data=tar)

    def get(self, src="/workspace"):
        return self._run(["docker", "exec", self.name, "tar", "-c", "-C", src, "."], timeout=60)

    def exec(self, command, *, stdin=None, timeout=20, workdir="/workspace", env=None):
        """Run a shell command; return exit code and bounded output. Never raises on non-zero."""
        args = ["docker", "exec", "-i", "-w", workdir]
        for key, value in (env or {}).items():
            args += ["-e", key + "=" + value]
        args += [self.name, "timeout", "-k", "2", str(timeout), "bash", "-c", command]
        try:
            result = subprocess.run(args, input=stdin, capture_output=True, timeout=timeout + 10, check=False)
        except subprocess.TimeoutExpired:
            return {"exit_code": 124, "stdout": b"", "stderr": b"host timeout"}
        return {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}

    def close(self):
        if self.alive:
            subprocess.run(["docker", "rm", "--force", self.name], capture_output=True, timeout=30, check=False)
            self.alive = False


def validate(action):
    if not isinstance(action, dict) or set(action) != {"tool", "args"}:
        raise ValueError("Action must contain only tool and args")
    name, args = action["tool"], action["args"]
    if name not in TOOLS:
        raise PermissionError("Unknown tool; only bash and submit exist")
    if not isinstance(args, dict) or set(args) != set(TOOLS[name]) or not all(isinstance(v, str) for v in args.values()):
        raise ValueError("Tool arguments do not match the schema")
    if len(json.dumps(args)) > 20000:
        raise ValueError("Action exceeds input budget")


class TerminalEnvironment:
    def __init__(self, task_id, image=IMAGE):
        self.task_id, self.image = task_id, image
        self.task = _load(task_id)
        self.sandbox = None

    def reset(self, seed):
        self.close()
        self.seed = seed
        self.steps, self.submission, self.workspace_tar = [], None, None
        self.terminated = self.truncated = False
        self.reason = None
        self.started = time.monotonic()
        self.sandbox = Sandbox(self.image).start()
        self.sandbox.put(tar_bytes(self.task.workspace(seed)))
        setup = getattr(self.task, "setup_script", None)
        if setup:
            # Trusted setup is piped through stdin, never written into the container.
            result = self.sandbox.exec("bash -s", stdin=setup(seed).encode(), timeout=60)
            if result["exit_code"]:
                raise RuntimeError("Task setup failed: " + result["stderr"].decode(errors="replace")[:1000])
        self.initial_digest = digest(self.listing())
        return {"schema": "nw.terminal-observation@1", "task": self.task.INSTRUCTION,
                "tools": {"bash": "Run one bash command in /workspace; returns exit code and output.",
                          "submit": "End the episode. Grading is done by hidden tests outside the container."},
                "budgets": BUDGET}

    def listing(self):
        out = self.sandbox.exec("find . -path ./repo/.git -prune -o -type f -print0 | sort -z | xargs -0 -r sha256sum")
        return out["stdout"].decode(errors="replace")

    def step(self, action):
        if self.terminated or self.truncated:
            raise RuntimeError("Episode ended; reset before taking another action")
        if len(self.steps) >= BUDGET["tool_calls"] or time.monotonic() - self.started > BUDGET["episode_seconds"]:
            self.truncated, self.reason = True, "budget"
            return {"ok": False, "kind": "BudgetExceeded", "error": "Episode budget exhausted"}
        begin = time.monotonic()
        try:
            validate(action)
            if action["tool"] == "submit":
                self.submission = action["args"]
                self.terminated, self.reason = True, "submitted"
                result = {"ok": True, "result": "submitted"}
            else:
                run = self.sandbox.exec(action["args"]["command"], timeout=BUDGET["command_seconds"])
                text = (run["stdout"] + run["stderr"]).decode(errors="replace")
                limit = BUDGET["output_chars"]
                result = {"ok": True, "result": {"exit_code": run["exit_code"],
                                                 "output": text[:limit] + ("\n[truncated]" if len(text) > limit else "")}}
        except PermissionError as exc:
            result = {"ok": False, "kind": "PermissionError", "error": str(exc)}
        except ValueError as exc:
            result = {"ok": False, "kind": "InvalidAction", "error": str(exc)}
        self.steps.append({"index": len(self.steps), "action": action, "observation": result,
                           "duration_seconds": round(time.monotonic() - begin, 3)})
        return result

    def verify(self):
        from .verifier import verify
        if self.workspace_tar is None:
            self.workspace_tar = self.sandbox.get()
        return verify(self.task, self.seed, self.workspace_tar, self.image)

    def close(self):
        if self.sandbox:
            self.sandbox.close()
            self.sandbox = None


def run_oracle(env):
    """Trusted oracle: the task's reference shell solution, sent through the agent's own bash tool."""
    script = (env.task.ROOT / "solution" / "oracle.sh").read_text()
    env.step({"tool": "bash", "args": {"command": script}})
    env.step({"tool": "submit", "args": {"summary": "oracle"}})


def run_nothing(env):
    env.step({"tool": "submit", "args": {"summary": "I did nothing."}})
