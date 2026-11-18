"""URL slug generation."""
import re


def slugify(title):
    """'Hello, World!' -> 'hello-world'."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower())
    return slug.strip("-")
