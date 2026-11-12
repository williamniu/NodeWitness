"""pass@k report with 95% bootstrap confidence intervals, from recorded terminal trials.

    python3 scripts/passk_report.py EXPERIMENT_ID [--k 1 5] [--out results/passk]

- Unit of analysis: (model, task). Each trial passes only if the external verifier passed it.
  Errored trials (infrastructure or provider failures) stay in the denominator as failures and
  are also counted separately.
- Per task: unbiased pass@k = 1 - C(n-c, k) / C(n, k)  (Chen et al., 2021), needs n >= k.
- Per model: mean over tasks. 95% CI: two-level bootstrap (resample tasks, then trials within
  each task), 10,000 resamples, percentile interval, fixed seed. Output is byte-identical on rerun.
"""

import argparse
import json
import random
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRIALS = ROOT / "outputs/terminal/trials"
RESAMPLES = 10_000


def pass_at_k(n, c, k):
    if n < k:
        raise ValueError("need at least k trials")
    return 1.0 if n - c < k else 1.0 - comb(n - c, k) / comb(n, k)


def load(experiment):
    rows = {}
    for path in sorted(TRIALS.glob("*.json")):
        record = json.loads(path.read_text())
        if record.get("experiment_id") != experiment:
            continue
        rows.setdefault(record["agent"], {}).setdefault(record["task"], []).append(
            {"passed": record["status"] == "passed", "error": record["status"] == "error", "run_id": record["run_id"]})
    return rows


def summarize(per_task, k, rng):
    tasks = sorted(per_task)
    def mean_passk(sample):
        return sum(pass_at_k(len(t), sum(t), k) for t in sample) / len(sample)
    observed = mean_passk([[r["passed"] for r in per_task[t]] for t in tasks])
    stats = []
    for _ in range(RESAMPLES):
        picked = [per_task[rng.choice(tasks)] for _ in tasks]
        stats.append(mean_passk([[rng.choice(rows)["passed"] for _ in rows] for rows in picked]))
    stats.sort()
    return {"pass_at_k": round(observed, 4), "ci95": [round(stats[int(0.025 * RESAMPLES)], 4), round(stats[int(0.975 * RESAMPLES) - 1], 4)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("experiment")
    parser.add_argument("--k", type=int, nargs="+", default=[1, 5])
    parser.add_argument("--out", type=Path, default=ROOT / "results/passk")
    args = parser.parse_args()
    data = load(args.experiment)
    if not data:
        raise SystemExit("No trials recorded for " + args.experiment)
    report = {"experiment": args.experiment, "method": __doc__.strip().splitlines()[3:],
              "resamples": RESAMPLES, "models": {}}
    for model in sorted(data):
        per_task = data[model]
        rng = random.Random(f"{args.experiment}|{model}")
        row = {"trials": sum(len(v) for v in per_task.values()),
               "errors": sum(r["error"] for v in per_task.values() for r in v),
               "tasks": {t: {"n": len(v), "passed": sum(r["passed"] for r in v)} for t, v in sorted(per_task.items())}}
        for k in args.k:
            if min(len(v) for v in per_task.values()) >= k:
                row["pass@%d" % k] = summarize(per_task, k, rng)
        report["models"][model] = row
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / (args.experiment + ".json")).write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    tasks = sorted({t for m in report["models"].values() for t in m["tasks"]})
    lines = ["# pass@k — " + args.experiment, "",
             "| Model | " + " | ".join("pass@%d (95%% CI)" % k for k in args.k) + " | " + " | ".join(tasks) + " | Errors |",
             "|---|" + "---|" * (len(args.k) + len(tasks) + 1)]
    for model, row in report["models"].items():
        cells = []
        for k in args.k:
            s = row.get("pass@%d" % k)
            cells.append("%.2f [%.2f, %.2f]" % (s["pass_at_k"], *s["ci95"]) if s else "n<k")
        cells += ["%d/%d" % (row["tasks"][t]["passed"], row["tasks"][t]["n"]) if t in row["tasks"] else "-" for t in tasks]
        lines.append("| %s | %s | %d |" % (model, " | ".join(cells), row["errors"]))
    lines += ["", "Errored trials count as failures. CI: two-level bootstrap over tasks and trials, %d resamples." % RESAMPLES]
    (args.out / (args.experiment + ".md")).write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
