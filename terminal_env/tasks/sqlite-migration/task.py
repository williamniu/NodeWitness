"""sqlite-migration: v1→v2 schema migration; hidden tests migrate other databases twice."""

import base64
import random
import re
import sqlite3
from decimal import Decimal

FIRST = ["Ada", "Grace", "Alan", "Linus", "Mary Ann", "Jean", "Wei", "Amara", "José", "Li"]
LAST = ["Lovelace", "Hopper", "Turing", "Torvalds", "de la Cruz", "Okafor", "Zhang", "Nakamura"]


def make_v1(seed, users=36, orders=110, bad_amount=False):
    rng = random.Random(seed)
    rows, emails = [], []
    for uid in range(1, users + 1):
        if emails and rng.random() < 0.12:
            base = rng.choice(emails)
            email = rng.choice([base.upper(), " " + base, base.title() + "  "])
        else:
            base = "user%d.%s@example.test" % (uid, rng.choice(["a", "b", "c"]))
            emails.append(base)
            email = rng.choice([base, base.upper(), "  " + base])
        if rng.random() < 0.06:
            email = rng.choice([None, "", "   "])
        style = rng.random()
        if style < 0.1:
            name = None
        elif style < 0.15:
            name = "   "
        elif style < 0.3:
            name = rng.choice(FIRST).split()[0]
        else:
            name = rng.choice(["", " ", "  "]) + rng.choice(FIRST) + rng.choice([" ", "  ", "\t"]) + rng.choice(LAST) + rng.choice(["", " "])
        rows.append((uid, email, name))
    rng.shuffle(rows)
    order_rows = []
    for oid in range(1, orders + 1):
        user = rng.randrange(1, users + 6)  # ids above `users` are orphans
        cents = rng.randrange(1, 300000)
        whole, frac = divmod(cents, 100)
        style = rng.random()
        if style < 0.25:
            text = "$" + format(whole, ",") + ".%02d" % frac
        elif style < 0.45 and frac % 10 == 0:
            text = "%d.%d" % (whole, frac // 10)
        elif style < 0.55 and frac == 0:
            text = str(whole)
        elif style < 0.7:
            text = " %d.%02d " % (whole, frac)
        else:
            text = "%d.%02d" % (whole, frac)
        if rng.random() < 0.12:
            text = rng.choice(["-" + text.strip(), "-$%d.%02d" % (whole, frac), "($%d.%02d)" % (whole, frac), "(%d.%02d)" % (whole, frac)])
        stamp = "2026-%02d-%02dT%02d:%02d:00Z" % (rng.randrange(1, 11), rng.randrange(1, 28), rng.randrange(24), rng.randrange(60))
        order_rows.append((oid, user, text, stamp))
    if bad_amount:
        oid, user, _, stamp = order_rows[len(order_rows) // 2]
        order_rows[len(order_rows) // 2] = (oid, user, "N/A", stamp)
    db = sqlite3.connect(":memory:")
    db.executescript("CREATE TABLE users(id INTEGER PRIMARY KEY, email TEXT, full_name TEXT);"
                     "CREATE TABLE orders(id INTEGER PRIMARY KEY, user_id INTEGER, amount TEXT, created_at TEXT);"
                     "PRAGMA user_version = 1;")
    db.executemany("INSERT INTO users VALUES (?,?,?)", rows)
    db.executemany("INSERT INTO orders VALUES (?,?,?,?)", order_rows)
    db.commit()
    data = db.serialize()
    db.close()
    return data, rows, order_rows


def to_cents(text):
    clean = text.strip()
    negative = clean.startswith("(") or clean.startswith("-")
    clean = clean.strip("()").lstrip("-").lstrip("$").replace(",", "")
    return (-1 if negative else 1) * int(Decimal(clean) * 100)


def raw_state(data):
    db = sqlite3.connect(":memory:")
    db.deserialize(data)
    tables = sorted(r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'"))
    state = {"user_version": db.execute("PRAGMA user_version").fetchone()[0],
             "schema": sorted(r[0] for r in db.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL")),
             "rows": {t: [list(r) for r in db.execute("SELECT * FROM %s ORDER BY rowid" % t)] for t in tables}}
    db.close()
    return state


def expected(seed, **size):
    _, users, orders = make_v1(seed, **size)
    keep, remap = {}, {}
    for uid, email, name in sorted(users):
        if not (email or "").strip():
            continue
        normal = email.strip().lower()
        if normal in keep:
            remap[uid] = keep[normal][0]
            continue
        words = (name or "").split()
        first, last = (" ".join(words[:-1]), words[-1]) if len(words) > 1 else ((words[0], "") if words else ("", ""))
        keep[normal] = (uid, normal, first, last)
        remap[uid] = uid
    out_users = sorted(keep.values())
    out_orders = sorted((oid, remap[user], to_cents(text), stamp) for oid, user, text, stamp in orders if user in remap)
    return {"user_version": 2, "users": [list(r) for r in out_users], "orders": [list(r) for r in out_orders]}


def workspace(seed):
    return {"app.db": make_v1(seed)[0]}


HIDDEN = {"A": (1000, {}), "B": (2000, {"users": 60, "orders": 200})}
BAD = (3000, {"bad_amount": True})


def hidden_inputs(seed):
    files = {key + "/app.db": make_v1(seed + offset, **size)[0] for key, (offset, size) in HIDDEN.items()}
    files["C/app.db"] = make_v1(seed + BAD[0], **BAD[1])[0]
    return files


def inspect(data):
    db = sqlite3.connect(":memory:")
    db.deserialize(data)
    tables = sorted(r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
    state = {"tables": tables, "user_version": db.execute("PRAGMA user_version").fetchone()[0]}
    if tables == ["orders", "users"]:
        info = {t: {r[1]: {"notnull": bool(r[3]) or bool(r[5]), "pk": bool(r[5])} for r in db.execute("PRAGMA table_info(%s)" % t)} for t in tables}
        state["columns"] = {t: sorted(info[t]) for t in tables}
        state["notnull_ok"] = all(c["notnull"] for t in info.values() for c in t.values())
        unique = [db.execute("PRAGMA index_info(%s)" % ("'" + r[1] + "'")).fetchall() for r in db.execute("PRAGMA index_list(users)") if r[2]]
        state["email_unique"] = any([c[2] for c in cols] == ["email"] for cols in unique)
        indexes = [db.execute("PRAGMA index_info('%s')" % r[1]).fetchall() for r in db.execute("PRAGMA index_list(orders)")]
        state["user_id_index"] = any([c[2] for c in cols] == ["user_id"] for cols in indexes)
        state["fk"] = [(r[2], r[3], r[4]) for r in db.execute("PRAGMA foreign_key_list(orders)")]
        try:
            state["users"] = [list(r) for r in db.execute("SELECT id, email, first_name, last_name FROM users ORDER BY id")]
            state["orders"] = [list(r) for r in db.execute("SELECT id, user_id, amount_cents, created_at FROM orders ORDER BY id")]
        except sqlite3.Error as exc:
            state["error"] = str(exc)
    db.close()
    return state


def check(sandbox, seed):
    checks = {"script_exists": {"passed": sandbox.exec("test -f /workspace/migrate.py")["exit_code"] == 0}}
    for key, (offset, size) in HIDDEN.items():
        want = expected(seed + offset, **size)
        path = "/tmp/hidden/%s/app.db" % key
        snapshots, codes = [], []
        for _ in range(2):
            codes.append(sandbox.exec("python3 -I /workspace/migrate.py " + path, timeout=30, workdir="/tmp")["exit_code"])
            dump = sandbox.exec("base64 -w0 " + path)
            snapshots.append(inspect(base64.b64decode(dump["stdout"])) if dump["exit_code"] == 0 else {"error": "missing"})
        first = snapshots[0]
        schema_ok = (first.get("columns") == {"orders": ["amount_cents", "created_at", "id", "user_id"],
                                              "users": ["email", "first_name", "id", "last_name"]}
                     and first.get("notnull_ok") and first.get("email_unique") and first.get("user_id_index")
                     and first.get("fk") == [("users", "user_id", "id")] and first.get("user_version") == 2)
        rows_ok = first.get("users") == want["users"] and first.get("orders") == want["orders"]
        checks["hidden_db_%s_schema" % key] = {"passed": bool(schema_ok and codes[0] == 0),
                                              **{k: first.get(k) for k in ("tables", "user_version", "columns", "email_unique", "user_id_index", "fk")}}
        checks["hidden_db_%s_rows" % key] = {"passed": bool(rows_ok), "users_ok": first.get("users") == want["users"],
                                            "orders_ok": first.get("orders") == want["orders"]}
        checks["hidden_db_%s_idempotent" % key] = {"passed": codes[1] == 0 and snapshots[1] == first}
    # C has one unparseable amount: the migration must fail and change nothing.
    original = make_v1(seed + BAD[0], **BAD[1])[0]
    code = sandbox.exec("python3 -I /workspace/migrate.py /tmp/hidden/C/app.db", timeout=30, workdir="/tmp")["exit_code"]
    dump = sandbox.exec("base64 -w0 /tmp/hidden/C/app.db")
    after = raw_state(base64.b64decode(dump["stdout"])) if dump["exit_code"] == 0 else None
    checks["hidden_db_C_bad_amount_rejected"] = {"passed": code != 0, "exit_code": code}
    checks["hidden_db_C_unchanged"] = {"passed": after == raw_state(original)}
    return checks
