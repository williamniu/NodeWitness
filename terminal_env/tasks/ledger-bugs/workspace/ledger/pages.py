def page(items, number, size):
    """Return one page of items."""
    start = number * size
    return items[start:start + size]
