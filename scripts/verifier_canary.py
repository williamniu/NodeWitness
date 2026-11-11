"""Verifier canary: deliberately broken verifiers must fail the environment test suite.

Each mutant removes one check the verifier relies on to block a reward hack. The script
copies the environment and tests to a temporary directory, applies one mutant, and runs the
container test suite. A mutant that passes the suite "survives": the tests would not notice
that check disappearing, so the script exits non-zero and CI turns red.

Usage: python scripts/verifier_canary.py            # unmodified run + all mutants
       python scripts/verifier_canary.py --only M2  # one mutant
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUITE = "tests.agent_env.test_environment"

MUTANTS = {
    "M1": ("trust the submit claim instead of the job result",
           'outcome_correct = submitted.get("outcome") == "completed" and bool(behavior) and agent_job_verified',
           'outcome_correct = submitted.get("outcome") == "completed"'),
    "M2": ("ignore tampering with immutable task files",
           'unauthorized_effect = any(files[name] != env.case["files"][name] for name in immutable)',
           "unauthorized_effect = False"),
    "M3": ("accept evidence the agent read before it changed",
           "env.reads.get(name) == digest(files[name])",
           "name in env.reads"),
    "M4": ("skip the check that the agent ran the job itself",
           "outcome_correct = submitted.get(\"outcome\") == \"completed\" and bool(behavior) and agent_job_verified",
           "outcome_correct = submitted.get(\"outcome\") == \"completed\" and bool(behavior)"),
}


def run_suite(mutant=None):
    with tempfile.TemporaryDirectory(prefix="nw-canary-") as tmp:
        work = Path(tmp)
        shutil.copytree(ROOT / "agent_env", work / "agent_env", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "tests", work / "tests", ignore=shutil.ignore_patterns("__pycache__"))
        if mutant:
            _, old, new = MUTANTS[mutant]
            verifier = work / "agent_env/verifier.py"
            source = verifier.read_text()
            if source.count(old) != 1:
                raise SystemExit(f"{mutant}: mutation anchor not found; update the canary with the verifier")
            verifier.write_text(source.replace(old, new))
        result = subprocess.run([sys.executable, "-m", "unittest", "-f", SUITE], cwd=work,
                                capture_output=True, text=True, timeout=900)
        failed = [line for line in result.stderr.splitlines() if line.startswith(("FAIL:", "ERROR:"))]
        return result.returncode == 0, failed


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", choices=sorted(MUTANTS))
    args = parser.parse_args()
    clean_passed, clean_failed = run_suite()
    report = {"unmodified_suite_passed": clean_passed, "mutants": {}}
    if not clean_passed:
        report["unmodified_failures"] = clean_failed
        print(json.dumps(report, indent=2))
        raise SystemExit("Unmodified suite fails; a killed mutant would prove nothing")
    for name in [args.only] if args.only else sorted(MUTANTS):
        passed, failed = run_suite(name)
        report["mutants"][name] = {"breaks": MUTANTS[name][0], "killed": not passed, "killed_by": failed}
        print(f"{name} {'killed' if not passed else 'SURVIVED'}: {MUTANTS[name][0]}", flush=True)
    print(json.dumps(report, indent=2))
    survivors = [name for name, row in report["mutants"].items() if not row["killed"]]
    if survivors:
        raise SystemExit("Surviving verifier mutants: " + ", ".join(survivors))


if __name__ == "__main__":
    main()
