def to_cents(text):
    """Parse a decimal amount string into integer cents."""
    return int(float(text) * 100)


def split(total_cents, n):
    """Split an amount into n near-equal parts."""
    part = total_cents // n
    return [part] * n


def allocate(total_cents, weights):
    """Split an amount in proportion to weights."""
    return [round(total_cents * w / sum(weights)) for w in weights]
