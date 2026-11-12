cat > /workspace/p95.py <<'PY'
import datetime, json, math, os, re, sys, zlib

NAME = re.compile(r"^app\.log(\.[1-9][0-9]*(\.gz)?)?$")
LEGACY = re.compile(r"^(\S+) user=(\S+) req=(\S+) status=(\d+) ms=(\d+)$")


def parse_ts(text):
    stamp = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("naive timestamp")
    return stamp


def lines(path):
    raw = open(path, "rb").read()
    if path.endswith(".gz"):
        # Decompress what is there; a truncated stream simply ends early.
        raw = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(raw)
    return raw.decode("utf-8", errors="replace").split("\n")[:-1]


def to_ms(value):
    if isinstance(value, str) and value.endswith("ms"):
        value = value[:-2]
    return int(value)


def records(path):
    for line in lines(path):
        line = line.strip()
        try:
            if line.startswith("{"):
                row = json.loads(line)
                yield parse_ts(row["ts"]), row["user"].lower(), row["request_id"], int(row["status"]), to_ms(row["latency_ms"])
            else:
                match = LEGACY.match(line)
                if match:
                    ts, user, rid, status, millis = match.groups()
                    yield parse_ts(ts), user.lower(), rid, int(status), int(millis)
        except (ValueError, KeyError, TypeError):
            continue


last = {}
for name in os.listdir(sys.argv[1]):
    if NAME.match(name):
        for ts, user, rid, status, ms in records(os.path.join(sys.argv[1], name)):
            if rid not in last or ts > last[rid][0]:
                last[rid] = (ts, user, status, ms)
failed = {}
for ts, user, status, ms in last.values():
    if status >= 500:
        failed.setdefault(user, []).append(ms)
rows = sorted(((u, len(v), sorted(v)[math.ceil(0.95 * len(v)) - 1]) for u, v in failed.items()), key=lambda r: (-r[1], r[0]))
print("user,failures,p95_ms")
for row in rows:
    print("%s,%d,%d" % row)
PY
