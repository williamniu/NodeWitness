"""incident-p95: parse rotated mixed-format logs; hidden tests rerun the agent's script on new logs."""

import datetime as dt
import gzip
import json
import math
import random
import re
import zlib

USERS = ["alice", "bob", "chen", "dara", "emeka", "farah", "goran", "hana"]
EPOCH = dt.datetime(2026, 11, 1, tzinfo=dt.timezone.utc)
OFFSETS = [dt.timedelta(hours=h) for h in (0, 2, -5, 5.5, 9, -8)]


def generate(seed, failure_rate=0.3, requests=260):
    rng = random.Random(seed)
    attempts = []
    for index in range(requests):
        rid = "r%05x" % rng.randrange(16 ** 5) + str(index)
        user = rng.choice(USERS)
        moment = EPOCH + dt.timedelta(seconds=rng.randrange(0, 2 * 86400))
        for _ in range(rng.choice([1, 1, 1, 2, 2, 3])):
            failed = rng.random() < failure_rate
            status = rng.choice([500, 502, 503, 504]) if failed else rng.choice([200, 200, 200, 201, 404, 429])
            attempts.append({"ts": moment, "user": user, "request_id": rid, "status": status,
                             "latency_ms": rng.randrange(15, 3000)})
            moment += dt.timedelta(seconds=rng.randrange(1, 40), milliseconds=rng.randrange(1, 999))
    attempts.sort(key=lambda a: a["ts"])
    # Oldest quarter-chunks go to older rotated files; legacy format in .gz files only.
    names = ["app.log.3.gz", "app.log.2.gz", "app.log.1", "app.log"]
    chunks = {name: [] for name in names}
    for position, attempt in enumerate(attempts):
        chunks[names[min(3, position * 4 // len(attempts))]].append(attempt)
    files = {}
    for name, rows in chunks.items():
        rng.shuffle(rows)
        lines = []
        for row in rows:
            if name.endswith(".gz"):
                lines.append("%s user=%s req=%s status=%d ms=%d" % (row["ts"].strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                             row["user"], row["request_id"], row["status"], row["latency_ms"]))
            else:
                offset = rng.choice(OFFSETS)
                local = row["ts"].astimezone(dt.timezone(offset))
                stamp = local.isoformat(timespec="milliseconds").replace("+00:00", "Z")
                status = str(row["status"]) if rng.random() < 0.2 else row["status"]
                user = rng.choice([row["user"], row["user"].upper(), row["user"].title()])
                latency = "%dms" % row["latency_ms"] if rng.random() < 0.2 else row["latency_ms"]
                lines.append(json.dumps({"ts": stamp, "user": user, "request_id": row["request_id"],
                                         "status": status, "latency_ms": latency}))
            if rng.random() < 0.03:
                lines.append(rng.choice(["WARN log rotated", '{"ts": "2026-11-01T', "", "user=bob req= status=503"]))
        text = "\n".join(lines) + "\n"
        if name.endswith(".gz"):
            blob = gzip.compress(text.encode(), mtime=0)
            # The oldest rotated file is cut mid-stream, as if the writer crashed.
            files[name] = blob[:int(len(blob) * 0.8)] if name == "app.log.3.gz" else blob
        else:
            files[name] = text
    decoy = [json.dumps({"ts": "2026-11-02T00:00:00Z", "user": "mallory", "request_id": "d%d" % i,
                         "status": 503, "latency_ms": 999}) for i in range(5)]
    files["audit.log"] = "\n".join(decoy) + "\n"
    files["app.log.bak"] = "\n".join(decoy) + "\n"
    return files, attempts


NAME = re.compile(r"^app\.log(\.[1-9][0-9]*(\.gz)?)?$")
LEGACY = re.compile(r"^(\S+) user=(\S+) req=(\S+) status=(\d+) ms=(\d+)$")


def complete_lines(name, content):
    if name.endswith(".gz"):
        text = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(content).decode(errors="replace")
    else:
        text = content
    return text.split("\n")[:-1]  # the piece after the last newline is incomplete or empty


def reference_rows(files):
    for name, content in files.items():
        if not NAME.match(name):
            continue
        for line in complete_lines(name, content):
            line = line.strip()
            try:
                if line.startswith("{"):
                    row = json.loads(line)
                    latency = row["latency_ms"]
                    latency = int(latency[:-2]) if isinstance(latency, str) and latency.endswith("ms") else int(latency)
                    yield dt.datetime.fromisoformat(row["ts"].replace("Z", "+00:00")), row["user"].lower(), row["request_id"], int(row["status"]), latency
                else:
                    match = LEGACY.match(line)
                    if match:
                        ts, user, rid, status, ms = match.groups()
                        yield dt.datetime.fromisoformat(ts.replace("Z", "+00:00")), user.lower(), rid, int(status), int(ms)
            except (ValueError, KeyError, TypeError):
                continue


def expected_csv(files):
    last = {}
    for ts, user, rid, status, ms in reference_rows(files):
        if rid not in last or ts > last[rid][0]:
            last[rid] = (ts, user, status, ms)
    failed = {}
    for ts, user, status, ms in last.values():
        if status >= 500:
            failed.setdefault(user, []).append(ms)
    rows = []
    for user, values in failed.items():
        values.sort()
        rows.append((user, len(values), values[math.ceil(0.95 * len(values)) - 1]))
    rows.sort(key=lambda row: (-row[1], row[0]))
    return "\n".join(["user,failures,p95_ms"] + ["%s,%d,%d" % row for row in rows])


def workspace(seed):
    files, _ = generate(seed)
    return {"logs/" + name: content for name, content in files.items()}


HIDDEN = {"A": lambda seed: generate(seed + 1000), "B": lambda seed: generate(seed + 2000, requests=400),
          "C": lambda seed: generate(seed + 3000, failure_rate=0.0, requests=40)}


def hidden_inputs(seed):
    out = {}
    for key, make in HIDDEN.items():
        files, _ = make(seed)
        out.update({key + "/" + name: content for name, content in files.items()})
    return out


def check(sandbox, seed):
    exists = sandbox.exec("test -f /workspace/p95.py")["exit_code"] == 0
    checks = {"script_exists": {"passed": exists}}
    for key, make in HIDDEN.items():
        expected = expected_csv(make(seed)[0])
        run = sandbox.exec("python3 -I /workspace/p95.py /tmp/hidden/" + key, timeout=30, workdir="/tmp")
        got = run["stdout"].decode(errors="replace").replace("\r\n", "\n").strip()
        checks["hidden_logs_" + key] = {"passed": run["exit_code"] == 0 and got == expected,
                                        "exit_code": run["exit_code"], "first_mismatch": _diff(got, expected)}
    return checks


def _diff(got, expected):
    a, b = got.splitlines(), expected.splitlines()
    for index in range(max(len(a), len(b))):
        left = a[index] if index < len(a) else None
        right = b[index] if index < len(b) else None
        if left != right:
            return {"line": index + 1, "got": left, "expected": right}
    return None
