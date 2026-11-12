# Incident report: failed-request p95 per user

`/workspace/logs/` holds an API gateway's rotated logs. Write `/workspace/p95.py`.

Usage: `python3 p95.py LOGDIR`. It prints CSV to stdout. Hidden tests run it on **other** log directories, so do not hard-code results.

## Input

- Read only files named `app.log`, `app.log.N` or `app.log.N.gz` (N is a positive integer) in LOGDIR. Ignore every other file.
- `.gz` files are gzip-compressed text. A `.gz` file can be **truncated** (the writer crashed). Use every complete line (one that ends in a newline) before the damage.
- Two line formats exist:
  - JSON: `{"ts": "2026-11-01T10:00:00+02:00", "user": "alice", "request_id": "r1a2b", "status": 503, "latency_ms": 412}`. `status` can be a number or a string of digits. `latency_ms` can be a number or a string such as `"412ms"`. `ts` is ISO 8601 with a `Z` or `±HH:MM` offset.
  - Legacy: `2026-11-01T08:00:00Z user=alice req=r1a2b status=503 ms=412`
- Skip lines that match neither format.
- User names are case-insensitive. Output them in lower case.

## Rules

1. A request can appear several times (client retries), possibly in different files. For each `request_id`, keep only the attempt with the **latest timestamp** (compare real instants, not strings).
2. The request failed if that last attempt has status >= 500.
3. For each user with at least one failed request, compute the p95 of the last-attempt `latency_ms` over their failed requests. Use nearest-rank: sort ascending, take element `ceil(0.95 * n)` (1-based).

## Output

Header `user,failures,p95_ms`, then one row per user with at least one failure. Sort by `failures` descending, then `user` ascending. Integers only. If no user has a failure, print only the header.
