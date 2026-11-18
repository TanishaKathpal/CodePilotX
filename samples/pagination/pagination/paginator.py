"""Page arithmetic. Pages are numbered starting at 1."""


def total_pages(total_items, per_page):
    """How many pages are needed to show `total_items` items."""
    if per_page <= 0:
        raise ValueError("per_page must be positive")
    return (total_items + per_page - 1) // per_page


def paginate(items, page, per_page):
    """Return the items that belong on the given page (1-based)."""
    if per_page <= 0:
        raise ValueError("per_page must be positive")
    if page < 1:
        raise ValueError("page must be >= 1")
    start = page * per_page
    return items[start:start + per_page]


def has_next_page(total_items, page, per_page):
    """True when there is at least one more page after `page`."""
    return page < total_pages(total_items, per_page)
