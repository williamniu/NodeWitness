cat > /workspace/ledger/money.py <<'PY'
import re
from decimal import ROUND_HALF_UP, Decimal

_AMOUNT = re.compile(r"^\s*[+-]?\d+(\.\d+)?\s*$")


def to_cents(text):
    """Parse a decimal amount string into integer cents, rounding half away from zero."""
    if not isinstance(text, str) or not _AMOUNT.match(text):
        raise ValueError("invalid amount: %r" % (text,))
    return int(Decimal(text.strip()).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)


def split(total_cents, n):
    """Split an amount into n parts; larger absolute parts first."""
    if n < 1:
        raise ValueError("n must be >= 1")
    sign = -1 if total_cents < 0 else 1
    base, extra = divmod(abs(total_cents), n)
    return [sign * (base + 1)] * extra + [sign * base] * (n - extra)


def allocate(total_cents, weights):
    """Largest-remainder allocation; ties go to the lower index."""
    if not weights or any(w < 0 for w in weights) or sum(weights) == 0:
        raise ValueError("weights must be non-negative with a positive sum")
    sign, total = (-1 if total_cents < 0 else 1), abs(total_cents)
    whole = sum(weights)
    parts = [total * w // whole for w in weights]
    remainders = [total * w % whole for w in weights]
    for index in sorted(range(len(weights)), key=lambda i: (-remainders[i], i))[:total - sum(parts)]:
        parts[index] += 1
    return [sign * p for p in parts]
PY
cat > /workspace/ledger/pages.py <<'PY'
def page(items, number, size):
    """Return one 1-indexed page of items."""
    if number < 1 or size < 1:
        raise ValueError("page number and size must be >= 1")
    return items[(number - 1) * size:number * size]
PY
cat > /workspace/ledger/dates.py <<'PY'
from datetime import datetime, timezone


def parse_ts(text):
    """Parse ISO 8601 with an offset; return an aware UTC datetime."""
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("timestamp needs an offset")
    return value.astimezone(timezone.utc)


def day_bucket(text):
    """UTC calendar day of a timestamp."""
    return parse_ts(text).strftime("%Y-%m-%d")
PY
cd /workspace && python3 -m unittest discover -s tests
