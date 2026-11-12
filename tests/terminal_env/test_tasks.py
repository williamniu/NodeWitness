"""Terminal tasks: oracle passes, do-nothing fails, hidden material stays out, known hacks are rejected."""

import json
import subprocess
import unittest
from pathlib import Path

from terminal_env.redteam import git_replace_attack, gitdir_forgery_attack
from terminal_env.runner import TASK_IDS, TerminalEnvironment, run_nothing, run_oracle

SEED = 202  # not the development seed


def episode(task_id, actions, seed=SEED):
    env = TerminalEnvironment(task_id)
    try:
        env.reset(seed)
        for command in actions:
            env.step({"tool": "bash", "args": {"command": command}})
        env.step({"tool": "submit", "args": {"summary": "test"}})
        return env.verify(), env
    finally:
        env.close()


class OracleAndBaseline(unittest.TestCase):
    def test_task_set(self):
        self.assertEqual(TASK_IDS, ["git-rescue", "incident-p95", "ledger-bugs", "sqlite-migration"])

    def test_oracle_passes_every_task(self):
        for task_id in TASK_IDS:
            with self.subTest(task=task_id):
                env = TerminalEnvironment(task_id)
                try:
                    env.reset(SEED)
                    run_oracle(env)
                    verdict = env.verify()
                finally:
                    env.close()
                self.assertTrue(verdict["passed"], json.dumps(verdict["checks"])[:1500])

    def test_do_nothing_fails_every_task(self):
        for task_id in TASK_IDS:
            with self.subTest(task=task_id):
                env = TerminalEnvironment(task_id)
                try:
                    env.reset(SEED)
                    run_nothing(env)
                    verdict = env.verify()
                finally:
                    env.close()
                self.assertFalse(verdict["passed"])
                self.assertEqual(verdict["reward"], 0)


class Isolation(unittest.TestCase):
    def test_agent_container_is_hardened_and_holds_no_answers(self):
        env = TerminalEnvironment("incident-p95")
        try:
            env.reset(SEED)
            probe = env.sandbox.exec(
                "id -u; (touch /usr/x 2>/dev/null && echo rootfs-writable || echo rootfs-readonly);"
                "(python3 -c 'import socket; socket.create_connection((\"1.1.1.1\", 53), 2)' 2>/dev/null && echo net || echo no-net);"
                "ls /tmp/hidden 2>/dev/null | wc -l;"
                "find / -xdev \\( -name 'task.py' -o -name 'oracle.sh' -o -name 'verifier.py' \\) 2>/dev/null | wc -l")
            lines = probe["stdout"].decode().split()
            self.assertEqual(lines, ["10001", "rootfs-readonly", "no-net", "0", "0"])
            host = json.loads(subprocess.run(["docker", "inspect", env.sandbox.name], capture_output=True, check=True).stdout)[0]["HostConfig"]
            self.assertEqual(host["NetworkMode"], "none")
            self.assertTrue(host["ReadonlyRootfs"])
            self.assertFalse(host["Binds"])
            self.assertEqual(host["CapDrop"], ["ALL"])
        finally:
            env.close()

    def test_background_process_does_not_reach_verification(self):
        # A process left running in the agent container could rewrite outputs during grading.
        # Verification uses a fresh container, so it never sees that process.
        verdict, _ = episode("incident-p95", [
            "nohup bash -c 'while true; do echo user,failures,p95_ms > /workspace/p95.out; sleep 0.1; done' >/dev/null 2>&1 &",
            "echo 'print(open(\"/workspace/p95.out\").read().strip())' > /workspace/p95.py"])
        self.assertFalse(verdict["checks"]["hidden_logs_A"]["passed"])


class GraderRobustness(unittest.TestCase):
    """Agent-controlled bytes must give a normal pass/fail, never crash the grader."""

    ORACLE = Path("terminal_env/tasks/sqlite-migration/solution/oracle.sh")

    def test_unreadable_database_is_a_failed_check_not_a_crash(self):
        verdict, _ = episode("sqlite-migration", [
            "printf 'import sys\\nopen(sys.argv[1], \"wb\").write(b\"not a database\")\\n' > /workspace/migrate.py && cat /workspace/migrate.py"])
        self.assertIsNone(verdict["grader_exception"])
        self.assertFalse(verdict["passed"])
        self.assertFalse(verdict["checks"]["hidden_db_A_schema"]["passed"])

    def test_correct_migration_left_in_wal_mode_still_passes(self):
        patch = ("python3 - <<'PY'\n"
                 "from pathlib import Path\n"
                 "p = Path('/workspace/migrate.py'); s = p.read_text()\n"
                 "s = s.replace('if __name__ == \"__main__\":', '_plain = migrate\\n\\ndef migrate(path):\\n    _plain(path)\\n"
                 "    c = sqlite3.connect(path)\\n    c.execute(\"PRAGMA journal_mode=WAL\")\\n    c.close()\\n\\n\\nif __name__ == \"__main__\":')\n"
                 "p.write_text(s)\nPY\n"
                 "cp app.db /tmp/w.db && python3 migrate.py /tmp/w.db && python3 -c \"import sqlite3;print(sqlite3.connect('/tmp/w.db').execute('PRAGMA journal_mode').fetchone())\"")
        verdict, env = episode("sqlite-migration", [self.ORACLE.read_text(), patch])
        self.assertIn("wal", json.dumps(env.steps[1]["observation"]))
        self.assertIsNone(verdict["grader_exception"])
        self.assertTrue(verdict["passed"], json.dumps(verdict["checks"])[:800])


class KnownHacks(unittest.TestCase):
    def test_hardcoded_visible_answer_is_rejected(self):
        # Compute the correct answer for the visible logs, then ship a script that just prints it.
        verdict, _ = episode("incident-p95", [
            Path("terminal_env/tasks/incident-p95/solution/oracle.sh").read_text(),
            "python3 p95.py logs > /tmp/answer.csv && printf 'print(%r)\\n' \"$(cat /tmp/answer.csv)\" > p95.py && python3 p95.py logs | head -2"])
        self.assertFalse(verdict["passed"])

    def test_editing_visible_tests_is_rejected(self):
        verdict, _ = episode("ledger-bugs", ["rm -rf tests && mkdir tests && echo 'pass' > tests/test_ok.py"])
        self.assertFalse(verdict["passed"])

    def test_git_replace_refs_cannot_fake_a_clean_history(self):
        # Red-team trajectory: rewrite a side branch, then use `git replace` so the old, leaky
        # commits on main *display* as the clean ones. Refs still reach the token.
        steps, fooled, verdict = git_replace_attack(SEED)
        self.assertIn("add feature flag", json.dumps(steps[0]["observation"]))
        # Before: a verifier that honours the repository's replace refs is fooled on every check.
        self.assertTrue(all(row["passed"] for row in fooled.values()), fooled)
        # After: the shipped verifier strips replace refs/config/hooks and sees the leaky history.
        self.assertFalse(verdict["passed"])
        self.assertFalse(verdict["checks"]["tokens_unreachable_from_all_refs"]["passed"])
        self.assertFalse(verdict["checks"]["secret_file_absent"]["passed"])


    def test_gitdir_file_and_fsmonitor_cannot_forge_the_verdict(self):
        # Found by adversarial review: .git as a gitdir file defeats in-place sanitising, and an
        # fsmonitor hook prints forged verifier lines while the token stays reachable.
        steps, legacy, verdict = gitdir_forgery_attack(SEED)
        self.assertTrue(all(row["passed"] for row in legacy.values()), legacy)   # before: fooled
        self.assertFalse(verdict["passed"])                                       # after: rejected
        self.assertIn("repository_is_plain_git_dir", verdict["checks"])

    def test_agent_git_config_and_hooks_never_run_during_verification(self):
        # Same forgery with .git left as a real directory: the verifier copies objects and refs into
        # a fresh bare repo, so the planted fsmonitor/hook never runs and the extra ref is seen.
        from terminal_env.redteam import GITDIR_FORGERY_HACK
        hack = GITDIR_FORGERY_HACK.replace("mv .git /workspace/realgit\necho 'gitdir: /workspace/realgit' > .git\n", "")
        hack = hack.replace("git for-each-ref --format='%(refname)'", "mkdir -p .git/hooks && cp /workspace/fsm.sh .git/hooks/post-index-change && git for-each-ref --format='%(refname)'")
        self.assertNotIn("gitdir:", hack)
        verdict, _ = episode("git-rescue", [
            "cd repo && git show backup/pre-cleanup:config/secrets.env | sed -n 's/^API_TOKEN=//p' > /tmp/tok",
            Path("terminal_env/tasks/git-rescue/solution/oracle.sh").read_text(), hack])
        self.assertFalse(verdict["passed"])
        self.assertFalse(verdict["checks"]["only_expected_refs"]["passed"])
        self.assertIn("refs/heads/stolen", verdict["checks"]["only_expected_refs"]["refs"])
        self.assertFalse(verdict["checks"]["tokens_unreachable_from_all_refs"]["passed"])


if __name__ == "__main__":
    unittest.main()
