"""Fetch OpenGraph metadata for link previews."""
import re
import requests
from bs4 import BeautifulSoup


TIMEOUT = 4


def fetch_link_preview(url):
    """Return dict {title, description, image} or {} on failure."""
    if not url or not re.match(r"^https?://", url):
        return {}
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Nielit Community LinkPreview)"},
            timeout=TIMEOUT,
            allow_redirects=True,
        )
        if resp.status_code >= 400 or "text/html" not in resp.headers.get("Content-Type", ""):
            return {}
        soup = BeautifulSoup(resp.content, "html.parser")

        def meta(prop):
            tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            return tag["content"].strip() if tag and tag.get("content") else ""

        title = meta("og:title") or (soup.title.string.strip() if soup.title and soup.title.string else "")
        desc = meta("og:description") or meta("description")
        image = meta("og:image")
        return {
            "title": title[:300],
            "description": desc[:500],
            "image": image[:500],
        }
    except Exception:
        return {}
