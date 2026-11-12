from datetime import datetime, timezone


def parse_ts(text):
    """Parse an ISO 8601 timestamp."""
    return datetime.fromisoformat(text.replace("Z", "")).replace(tzinfo=timezone.utc)


def day_bucket(text):
    """UTC calendar day of a timestamp."""
    return parse_ts(text).strftime("%Y-%m-%d")
