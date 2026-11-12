cat > /workspace/migrate.py <<'PY'
import re
import sqlite3
import sys
from decimal import Decimal

NUMBER = r"\$?(\d{1,3}(,\d{3})+|\d+)(\.\d{1,2})?"
AMOUNT = re.compile(r"^(-?" + NUMBER + r"|\(" + NUMBER + r"\))$")


def cents(text):
    text = (text or "").strip()
    if not AMOUNT.match(text):
        raise ValueError("bad amount %r" % text)
    negative = text.startswith(("-", "("))
    value = int(Decimal(text.strip("()").lstrip("-").lstrip("$").replace(",", "")) * 100)
    return -value if negative else value


def split_name(name):
    words = (name or "").split()
    if not words:
        return "", ""
    if len(words) == 1:
        return words[0], ""
    return " ".join(words[:-1]), words[-1]


def migrate(path):
    db = sqlite3.connect(path)
    if db.execute("PRAGMA user_version").fetchone()[0] >= 2:
        db.close()
        return
    # Read and validate everything (every amount, even on orders that will be dropped) before the
    # first write, then write in one explicit transaction.
    keep, remap, users = {}, {}, []
    for uid, email, name in db.execute("SELECT id, email, full_name FROM users ORDER BY id"):
        normal = (email or "").strip().lower()
        if not normal:
            continue
        if normal in keep:
            remap[uid] = keep[normal]
            continue
        keep[normal] = remap[uid] = uid
        users.append((uid, normal) + split_name(name))
    rows = [(oid, uid, cents(amount), created)
            for oid, uid, amount, created in db.execute("SELECT id, user_id, amount, created_at FROM orders ORDER BY id")]
    orders = [(oid, remap[uid], amount, created) for oid, uid, amount, created in rows if uid in remap]
    db.isolation_level = None
    db.execute("BEGIN")
    try:
        db.execute("DROP TABLE orders")
        db.execute("DROP TABLE users")
        db.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, first_name TEXT NOT NULL, last_name TEXT NOT NULL)")
        db.execute("CREATE TABLE orders(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), amount_cents INTEGER NOT NULL, created_at TEXT NOT NULL)")
        db.execute("CREATE INDEX idx_orders_user_id ON orders(user_id)")
        db.executemany("INSERT INTO users VALUES (?,?,?,?)", users)
        db.executemany("INSERT INTO orders VALUES (?,?,?,?)", orders)
        db.execute("PRAGMA user_version = 2")
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise
    db.execute("VACUUM")
    db.close()


if __name__ == "__main__":
    try:
        migrate(sys.argv[1])
    except ValueError as exc:
        sys.exit("migration aborted, database unchanged: %s" % exc)
PY
cp /workspace/app.db /tmp/try.db && python3 /workspace/migrate.py /tmp/try.db && python3 /workspace/migrate.py /tmp/try.db && sqlite3 /tmp/try.db 'PRAGMA user_version; SELECT count(*) FROM users; SELECT count(*) FROM orders;'
