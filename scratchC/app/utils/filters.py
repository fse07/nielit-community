"""Custom Jinja filters for templates."""
from datetime import datetime, timedelta
import bleach


ALLOWED_TAGS = ["b", "i", "em", "strong", "a", "br", "p"]
ALLOWED_ATTRS = {"a": ["href", "title", "rel"]}


def timeago(dt):
    if not dt:
        return ""
    now = datetime.utcnow()
    diff = now - dt
    secs = int(diff.total_seconds())
    if secs < 60:
        return "just now"
    if secs < 3600:
        m = secs // 60
        return f"{m}m"
    if secs < 86400:
        h = secs // 3600
        return f"{h}h"
    if secs < 604800:
        d = secs // 86400
        return f"{d}d"
    if secs < 2592000:
        w = secs // 604800
        return f"{w}w"
    if diff.days < 365:
        return dt.strftime("%b %d")
    return dt.strftime("%b %d, %Y")


def clean_html(text):
    if not text:
        return ""
    return bleach.clean(text, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)


def linkify(text):
    if not text:
        return ""
    return bleach.linkify(bleach.clean(text, tags=[], strip=True))


def nl2br(text):
    from markupsafe import Markup, escape
    if not text:
        return ""
    return Markup("<br>".join(escape(text).split("\n")))


def register_filters(app):
    app.jinja_env.filters["timeago"] = timeago
    app.jinja_env.filters["clean_html"] = clean_html
    app.jinja_env.filters["linkify"] = linkify
    app.jinja_env.filters["nl2br"] = nl2br
