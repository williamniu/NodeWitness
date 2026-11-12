# Migrate a SQLite database from schema v1 to v2

`/workspace/app.db` is a v1 database (`PRAGMA user_version = 1`). Write `/workspace/migrate.py`.

Usage: `python3 migrate.py PATH`. It migrates the database at PATH in place. Hidden tests run it on **other** v1 databases, then run it a second time on the result. Standard library only.

## v1 schema

```
users(id INTEGER PRIMARY KEY, email TEXT, full_name TEXT)
orders(id INTEGER PRIMARY KEY, user_id INTEGER, amount TEXT, created_at TEXT)
```

## v2 schema and rules

```
users(id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, first_name TEXT NOT NULL, last_name TEXT NOT NULL)
orders(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), amount_cents INTEGER NOT NULL, created_at TEXT NOT NULL)
index idx_orders_user_id ON orders(user_id)
PRAGMA user_version = 2
```

1. `email` is the v1 email trimmed and lower-cased. Users whose email is NULL or blank are deleted, together with their orders. If several v1 users have the same email after that, keep only the user with the smallest `id`, and move the other users' orders to that user.
2. Names: trim `full_name` and treat any run of whitespace as one space. The last word is `last_name`; the words before it, joined by single spaces, are `first_name`. One word: it is `first_name` and `last_name` is `''`. Empty or NULL: both are `''`.
3. `amount` is text such as `12`, `12.5`, `$1,234.50` or ` 7.05 `: an optional `$`, digits with optional `,` thousands separators, and up to two decimals. Refunds are negative, written `-12.50`, `-$12.50` or in accounting style `($12.50)`. Store exact integer cents.
4. Delete orders whose `user_id` does not match any v1 user.
5. Keep every other value (`id`, `created_at`) unchanged. Only the tables `users` and `orders` may remain.
6. Running `migrate.py` on a v2 database must change nothing.
7. **All or nothing.** If any `amount` does not match rule 3, exit with a non-zero status and leave the database exactly as it was (still v1, every row unchanged).
