"""ledger-bugs: fix a package to its spec; hidden cases come from the host and differ per seed."""

import datetime as dt
import json
import random
import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
AMOUNT = re.compile(r"^\s*[+-]?\d+(\.\d+)?\s*$")

# Runs inside the fresh verifier container; piped through stdin, never stored there.
HARNESS = r'''
import json, sys
sys.path.insert(0, "/workspace")
cases = json.load(open(sys.argv[1]))
out = []
for fn, args in cases:
    module, name = fn.rsplit(".", 1)
    try:
        func = getattr(__import__(module, fromlist=[name]), name)
        value = func(*args)
        if hasattr(value, "isoformat"):
            value = {"datetime": value.isoformat(), "tz": repr(value.tzinfo)}
        out.append({"value": value})
    except Exception as exc:
        out.append({"error": type(exc).__name__})
print(json.dumps(out))
'''


def workspace(seed):
    root = HERE / "workspace"
    return {str(p.relative_to(root)): p.read_text() for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def ref_to_cents(text):
    if not isinstance(text, str) or not AMOUNT.match(text):
        raise ValueError(text)
    return int(Decimal(text.strip()).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)


def ref_split(total, n):
    if n < 1:
        raise ValueError(n)
    sign = -1 if total < 0 else 1
    base, extra = divmod(abs(total), n)
    return [sign * (base + 1)] * extra + [sign * base] * (n - extra)


def ref_allocate(total, weights):
    from fractions import Fraction
    if not weights or any(w < 0 for w in weights) or sum(weights) == 0:
        raise ValueError(weights)
    shares = [Fraction(abs(total) * w, sum(weights)) for w in weights]
    parts = [int(s) for s in shares]
    order = sorted(range(len(weights)), key=lambda i: (-(shares[i] - parts[i]), i))
    for i in order[:abs(total) - sum(parts)]:
        parts[i] += 1
    return [(-p if total < 0 else p) for p in parts]


def ref_page(items, number, size):
    if number < 1 or size < 1:
        raise ValueError((number, size))
    return items[(number - 1) * size:number * size]


def ref_parse_ts(text):
    value = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError(text)
    return value.astimezone(dt.timezone.utc)


def ref_day_bucket(text):
    return ref_parse_ts(text).strftime("%Y-%m-%d")


REFERENCE = {"ledger.money.to_cents": ref_to_cents, "ledger.money.split": ref_split,
             "ledger.money.allocate": ref_allocate, "ledger.pages.page": ref_page, "ledger.dates.parse_ts": ref_parse_ts,
             "ledger.dates.day_bucket": ref_day_bucket}


def cases(seed):
    rng = random.Random(seed + 77)
    out = []
    for text in ["2.675", "-1.005", "0.005", "0.004", " 7 ", "+3.1", "1.2.3", "abc", "", ".5", "1e2", "-0.015"]:
        out.append(("ledger.money.to_cents", [text]))
    for _ in range(12):
        whole, frac = rng.randrange(0, 5000), rng.choice(["5", "05", "005", "995", "125", "675", "1"])
        out.append(("ledger.money.to_cents", [rng.choice(["", "-"]) + "%d.%s" % (whole, frac)]))
    for total, n in [(100, 3), (-5, 3), (0, 4), (7, 0), (1, 5)] + [(rng.randrange(-999, 999), rng.randrange(1, 9)) for _ in range(10)]:
        out.append(("ledger.money.split", [total, n]))
    for total, weights in [(10, [1, 2]), (100, [1, 1, 1]), (-7, [1, 1]), (5, [3, 0, 2]), (1, [1, 1, 1]),
                           (0, [1, 2]), (9, []), (9, [0, 0]), (9, [2, -1]), (-100, [1, 1, 1])] + \
                          [(rng.randrange(-5000, 5000), [rng.randrange(0, 9) for _ in range(rng.randrange(2, 7))] + [rng.randrange(1, 9)]) for _ in range(14)]:
        out.append(("ledger.money.allocate", [total, weights]))
    items = list(range(rng.randrange(5, 30)))
    for number, size in [(1, 3), (0, 3), (2, 0), (99, 4)] + [(rng.randrange(1, 8), rng.randrange(1, 7)) for _ in range(8)]:
        out.append(("ledger.pages.page", [items, number, size]))
    for _ in range(8):
        moment = dt.datetime(2026, 11, 1, tzinfo=dt.timezone.utc) + dt.timedelta(minutes=rng.randrange(0, 4000))
        offset = dt.timezone(dt.timedelta(hours=rng.choice([-8, -5, 2, 9, 13])))
        text = moment.astimezone(offset).isoformat()
        out.append(("ledger.dates.parse_ts", [text]))
        out.append(("ledger.dates.day_bucket", [text]))
    out += [("ledger.dates.parse_ts", ["2026-11-01T10:00:00Z"]), ("ledger.dates.parse_ts", ["2026-11-01T10:00:00"]),
            ("ledger.dates.day_bucket", ["2026-11-01T23:30:00-05:00"])]
    return out


def expected(seed):
    rows = []
    for fn, args in cases(seed):
        try:
            value = REFERENCE[fn](*args)
            if isinstance(value, dt.datetime):
                value = {"datetime": value.isoformat(), "tz": repr(value.tzinfo)}
            rows.append({"value": value})
        except ValueError:
            rows.append({"error": "ValueError"})
    return rows


def hidden_inputs(seed):
    return {"cases.json": json.dumps(cases(seed))}


def check(sandbox, seed):
    run = sandbox.exec("python3 -I - /tmp/hidden/cases.json", stdin=HARNESS.encode(), timeout=30, workdir="/tmp")
    try:
        got = json.loads(run["stdout"].decode().strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"harness_ran": {"passed": False, "stderr": run["stderr"].decode(errors="replace")[-500:]}}
    want = expected(seed)
    checks = {"harness_ran": {"passed": len(got) == len(want)}}
    groups = {}
    for (fn, args), left, right in zip(cases(seed), got, want):
        row = groups.setdefault(fn, {"passed": True, "cases": 0, "failed": []})
        row["cases"] += 1
        if left != right:
            row["passed"] = False
            if len(row["failed"]) < 3:
                row["failed"].append({"args": args if fn != "ledger.pages.page" else args[1:], "got": left, "expected": right})
    checks.update(groups)
    return checks
