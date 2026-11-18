"""Tiny in-memory search used by the demo app."""


def search(records, term, field="title"):
    """Return the records whose `field` contains `term` (case-insensitive)."""
    term = term.lower()
    return [r for r in records if term in str(r.get(field, "")).lower()]
