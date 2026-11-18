"""Shorten long strings for display."""


def truncate(text, limit, suffix="..."):
    """Cut `text` to at most `limit` characters, adding `suffix` when something was cut."""
    if limit < len(suffix):
        raise ValueError("limit is shorter than the suffix")
    if len(text) <= limit:
        return text
    return text[: limit - len(suffix)] + suffix
