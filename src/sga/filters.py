"""Cheap, deterministic filtering before any LLM call."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone

from .config import Filters, Sources
from .models import Post

_URL = re.compile(r"https?://\S+")
_MENTION = re.compile(r"@\w+")
_NON_WORD = re.compile(r"[^\w]+")


def normalize_text(text: str) -> str:
    """Text fingerprint for spotting copy-paste duplicates (bot rings, reposted threads)."""
    text = _URL.sub(" ", text.lower())
    text = _MENTION.sub(" ", text)
    return _NON_WORD.sub(" ", text).strip()


def dedupe(posts: Iterable[Post]) -> list[Post]:
    """Drop repeated IDs (merging their sources) and posts with identical normalized text.

    For identical text the earliest post wins: it's the original, the rest are copies.
    """
    by_id: dict[str, Post] = {}
    for post in posts:
        if post.id in by_id:
            kept = by_id[post.id]
            by_id[post.id] = kept.model_copy(
                update={"sources": sorted(set(kept.sources) | set(post.sources))}
            )
        else:
            by_id[post.id] = post

    by_text: dict[str, Post] = {}
    for post in sorted(by_id.values(), key=lambda p: p.created_at):
        key = normalize_text(post.text)
        if not key:
            continue
        by_text.setdefault(key, post)
    return sorted(by_text.values(), key=lambda p: p.created_at, reverse=True)


def apply_filters(
    posts: Iterable[Post],
    filters: Filters,
    sources: Sources,
    own_handle: str = "",
    exclude_ids: set[str] | None = None,
    now: datetime | None = None,
) -> tuple[list[Post], Counter]:
    """Return (kept posts, Counter of drop reasons). Dedupes first."""
    now = now or datetime.now(timezone.utc)
    exclude_ids = exclude_ids or set()
    excluded_handles = {h.lstrip("@").lower() for h in filters.exclude_handles}
    if own_handle:
        excluded_handles.add(own_handle.lstrip("@").lower())
    monitored = sources.monitored_set()
    languages = {lang.lower() for lang in filters.languages}
    max_age = timedelta(hours=filters.max_age_hours)

    posts = list(posts)
    unique = dedupe(posts)
    dropped: Counter = Counter()
    if len(unique) < len(posts):
        dropped["duplicate"] = len(posts) - len(unique)

    kept: list[Post] = []
    for post in unique:
        reason = _drop_reason(
            post, filters, monitored, languages, excluded_handles, exclude_ids, max_age, now
        )
        if reason:
            dropped[reason] += 1
        else:
            kept.append(post)
    return kept, dropped


def _drop_reason(
    post: Post,
    filters: Filters,
    monitored: set[str],
    languages: set[str],
    excluded_handles: set[str],
    exclude_ids: set[str],
    max_age: timedelta,
    now: datetime,
) -> str | None:
    handle = post.author_handle.lower()
    if post.id in exclude_ids:
        return "already reviewed"
    if handle in excluded_handles:
        return "excluded account"
    if now - post.created_at > max_age:
        return "too old"
    if post.is_reply and not filters.include_replies:
        return "is a reply"
    if languages and (post.lang or "").lower() not in languages:
        return "language"
    if handle in monitored and not filters.follower_filter_applies_to_monitored:
        return None
    if post.author_followers is None:
        return "follower count unknown"
    if post.author_followers < filters.min_followers:
        return "too few followers"
    if post.author_followers > filters.max_followers:
        return "too many followers"
    return None
