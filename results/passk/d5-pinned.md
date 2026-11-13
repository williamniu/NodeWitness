# pass@k — d5-pinned

| Model | pass@1 (95% CI) | pass@5 (95% CI) | git-rescue | incident-p95 | ledger-bugs | sqlite-migration | Errors |
|---|---|---|---|---|---|---|---|
| qwen36 | 0.35 [0.00, 0.75] | 0.50 [0.00, 1.00] | 0/5 | 3/5 | 0/5 | 4/5 | 0 |

Errored trials count as failures. 95% CI: percentile bootstrap, 10000 resamples (pass@1: tasks then trials; pass@k>1: tasks).

When n = k, pass@k per task only means "passed at least once", and its CI (tasks resampled) can collapse to one value. Read it as a count of tasks solved at least once.
