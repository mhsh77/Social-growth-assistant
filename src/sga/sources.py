"""Work out why a captured post is in front of us (which keyword, list or account)."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from .config import Sources
from .models import Post


def source_for_page(page_url: str, sources: Sources) -> str | None:
    """Label for the page a capture came from, or None if it isn't a page we collect from."""
    parsed = urlparse(page_url)
    if parsed.hostname not in {"x.com", "twitter.com", "mobile.x.com"}:
        return None
    if parsed.path.startswith("/i/lists/"):
        return "list"
    if parsed.path == "/search":
        query = (parse_qs(parsed.query).get("q") or [""])[0]
        for keyword in sources.keywords:
            if keyword.lower() in query.lower():
                return f"search:{keyword}"
        return f"search:{query}" if query else None
    return None


def matched_keywords(post: Post, sources: Sources) -> list[str]:
    text = post.text.lower()
    return [k for k in sources.keywords if k.lower() in text]


def describe_why(post: Post, sources: Sources) -> str:
    """Short 'why suggested' line built from where the post was found."""
    parts: list[str] = []
    searched = sorted({s.split(":", 1)[1] for s in post.sources if s.startswith("search:")})
    if searched:
        parts.append("search: " + ", ".join(f'"{k}"' for k in searched))
    in_text = [k for k in matched_keywords(post, sources) if k not in searched]
    if in_text:
        parts.append("mentions: " + ", ".join(f'"{k}"' for k in in_text))
    if post.author_handle.lower() in sources.monitored_set():
        parts.append(f"monitored account @{post.author_handle}")
    elif "list" in post.sources:
        parts.append("from your X List")
    return "; ".join(parts) or "captured while browsing"
