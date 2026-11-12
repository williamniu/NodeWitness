# ledger — specification

## ledger.money

`to_cents(text: str) -> int`
- `text` is an optional sign, one or more digits, and an optional `.` followed by one or more digits. Surrounding whitespace is allowed. Anything else raises `ValueError`.
- Convert exactly (no binary floating point) and round to whole cents, **half away from zero**: `"2.675"` → `268`, `"-1.005"` → `-101`, `"0.004"` → `0`.

`split(total_cents: int, n: int) -> list[int]`
- Split `total_cents` into `n` integer parts that sum exactly to `total_cents` and whose absolute values differ by at most 1.
- Parts with the larger absolute value come first. All non-zero parts have the sign of `total_cents`.
- `n < 1` raises `ValueError`.
- Example: `split(100, 3)` → `[34, 33, 33]`; `split(-5, 3)` → `[-2, -2, -1]`.

`allocate(total_cents: int, weights: list[int]) -> list[int]`
- Split `total_cents` in proportion to `weights` (non-negative integers). An empty list, a negative weight, or weights that sum to 0 raise `ValueError`.
- Each part's exact share is `total_cents * w / sum(weights)`. Start from every share truncated toward zero. Then give the cents still missing, one each, to the parts with the largest discarded fractional parts; on a tie, the lower index wins.
- The parts sum exactly to `total_cents`, and every non-zero part has its sign.
- Examples: `allocate(10, [1, 2])` → `[3, 7]`; `allocate(100, [1, 1, 1])` → `[34, 33, 33]`; `allocate(-7, [1, 1])` → `[-4, -3]`; `allocate(5, [3, 0, 2])` → `[3, 0, 2]`.

## ledger.pages

`page(items: list, number: int, size: int) -> list`
- Pages are 1-indexed: page 1 is `items[0:size]`.
- A page past the end returns `[]`.
- `number < 1` or `size < 1` raises `ValueError`.

## ledger.dates

`parse_ts(text: str) -> datetime.datetime`
- Parse ISO 8601 with a `Z` or `±HH:MM` offset. Return an aware datetime **converted to UTC** (`tzinfo` is `datetime.timezone.utc`).
- A timestamp without an offset raises `ValueError`.

`day_bucket(text: str) -> str`
- The UTC calendar date of `parse_ts(text)` as `YYYY-MM-DD`.
