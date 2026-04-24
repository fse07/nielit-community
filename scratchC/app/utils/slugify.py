"""Slug generation."""
import re
import uuid


def slugify(text):
    text = (text or "").lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:60] or uuid.uuid4().hex[:8]


def unique_slug(base, exists_fn):
    s = slugify(base)
    cand = s
    i = 2
    while exists_fn(cand):
        cand = f"{s}-{i}"
        i += 1
    return cand
