"""pass@k report with 95% bootstrap confidence intervals, from recorded terminal trials.

    python3 scripts/passk_report.py EXPERIMENT_ID [--k 1 5] [--out results/passk]

- Unit of analysis: (model, task). Each trial passes only if the external verifier passed it.
  Errored trials (infrastructure or provider failures) stay in the denominator as failures and
  are also counted separately.
- Per task: unbiased pass@k = 1 - C(n-c, k) / C(n, k)  (Chen et al., 2021), needs n >= k.
- Per model: mean over tasks. 95% CI, 10,000 percentile-bootstrap resamples, one fixed seed per
  (experiment, model, k), so a CI does not depend on which other k values are requested:
  pass@1 resamples tasks, then trials within each task; pass@k for k > 1 resamples tasks only and
  keeps each task's unbiased estimate (resampling trials with replacement biases pass@k down).
- Every model must have trials on the same task set, or the script stops. Unreadable trial files
  (e.g. half-written) are skipped and counted.
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
    rows, unreadable = {}, 0
    for path in sorted(TRIALS.glob("*.json")):
        try:
            record = json.loads(path.read_text())
        except ValueError:
            unreadable += 1
            continue
        if record.get("experiment_id") != experiment:
            continue
        rows.setdefault(record["agent"], {}).setdefault(record["task"], []).append(
            {"passed": record["status"] == "passed", "error": record["status"] == "error", "run_id": record["run_id"]})
    return rows, unreadable


def summarize(per_task, k, rng):
    tasks = sorted(per_task)
    def mean_passk(sample):
        return sum(pass_at_k(len(t), sum(t), k) for t in sample) / len(sample)
    observed = mean_passk([[r["passed"] for r in per_task[t]] for t in tasks])
    estimate = {t: pass_at_k(len(per_task[t]), sum(r["passed"] for r in per_task[t]), k) for t in tasks}
    stats = []
    for _ in range(RESAMPLES):
        picked = [rng.choice(tasks) for _ in tasks]
        if k == 1:
            stats.append(mean_passk([[rng.choice(per_task[t])["passed"] for _ in per_task[t]] for t in picked]))
        else:
            stats.append(sum(estimate[t] for t in picked) / len(picked))
    stats.sort()
    return {"pass_at_k": round(observed, 4), "ci95": [round(stats[int(0.025 * RESAMPLES)], 4), round(stats[int(0.975 * RESAMPLES) - 1], 4)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("experiment")
    parser.add_argument("--k", type=int, nargs="+", default=[1, 5])
    parser.add_argument("--out", type=Path, default=ROOT / "results/passk")
    args = parser.parse_args()
    data, unreadable = load(args.experiment)
    if not data:
        raise SystemExit("No trials recorded for " + args.experiment)
    task_sets = {model: sorted(per_task) for model, per_task in data.items()}
    if len({tuple(v) for v in task_sets.values()}) > 1:
        raise SystemExit("Models were run on different task sets: " + json.dumps(task_sets))
    report = {"experiment": args.experiment, "method": __doc__.strip().splitlines()[3:],
              "resamples": RESAMPLES, "unreadable_trial_files": unreadable, "models": {}}
    for model in sorted(data):
        per_task = data[model]
        row = {"trials": sum(len(v) for v in per_task.values()),
               "errors": sum(r["error"] for v in per_task.values() for r in v),
               "tasks": {t: {"n": len(v), "passed": sum(r["passed"] for r in v)} for t, v in sorted(per_task.items())}}
        for k in args.k:
            if min(len(v) for v in per_task.values()) >= k:
                row["pass@%d" % k] = summarize(per_task, k, random.Random(f"{args.experiment}|{model}|k={k}"))
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
    lines += ["", "Errored trials count as failures. 95%% CI: percentile bootstrap, %d resamples (pass@1: tasks then trials; pass@k>1: tasks)." % RESAMPLES]
    (args.out / (args.experiment + ".md")).write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
