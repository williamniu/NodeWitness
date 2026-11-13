# D5 — frozen trial records

40 terminal-task trials (2 local models × 4 tasks × seeds 1001–1005), copied byte-for-byte from `outputs/terminal/trials/` after the run. All on commit `fea503f`, clean `terminal_env/`, verifier `nw-terminal-verifier@2`.

- `trials/<run_id>.json` — full record: every bash command and its output, verifier checks, provenance, model settings.
- `workspaces/<run_id>.tar.gz` — the exact `/workspace` that was graded. (The record's `workspace_archive` field shows its original path under `outputs/`.)

Reproduce the report:

```bash
python3 scripts/passk_report.py d5 --trials results/d5/trials
```

`tests/reporting/test_passk.py` checks in CI that this regenerates `results/passk/d5.{json,md}` byte-for-byte.
