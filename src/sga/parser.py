"""Extract posts from the GraphQL JSON that X's web app already downloaded.

The browser extension forwards those responses unchanged; this module keeps only the
fields in `Post` and discards the rest. X changes this JSON shape from time to time,
so the walk is deliberately tolerant: it looks for objects typed "Tweet" anywhere in
the payload instead of following one exact path.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any

from .models import Post

_X_DATE_FORMAT = "%a %b %d %H:%M:%S %z %Y"  # e.g. "Sun Oct 05 08:12:44 +0000 2026"


def extract_posts(payload: Any) -> list[Post]:
    """Return unique posts found in a GraphQL timeline payload, in first-seen order."""
    seen: dict[str, Post] = {}
    for raw in _walk(payload):
        post = _to_post(raw)
        if post is not None and post.id not in seen:
            seen[post.id] = post
    return list(seen.values())


def _walk(node: Any) -> Iterator[dict]:
    if isinstance(node, list):
        for item in node:
            yield from _walk(item)
        return
    if not isinstance(node, dict):
        return
    if "promotedMetadata" in node:  # ads
        return
    typename = node.get("__typename")
    if typename == "TweetWithVisibilityResults" and "tweet" in node:
        yield from _walk(node["tweet"])
        return
    if typename == "Tweet" and isinstance(node.get("legacy"), dict):
        retweeted = node["legacy"].get("retweeted_status_result", {}).get("result")
        # A retweet is someone else's post resurfaced; the original is what we'd reply to.
        yield from _walk(retweeted) if retweeted else iter([node])
        return  # don't descend: quoted posts weren't what the user was browsing
    for value in node.values():
        yield from _walk(value)


def _to_post(tweet: dict) -> Post | None:
    legacy = tweet.get("legacy") or {}
    user = ((tweet.get("core") or {}).get("user_results") or {}).get("result") or {}
    user_core = user.get("core") or {}
    user_legacy = user.get("legacy") or {}

    post_id = tweet.get("rest_id") or legacy.get("id_str")
    handle = user_core.get("screen_name") or user_legacy.get("screen_name")
    created_raw = legacy.get("created_at")
    note = (
        ((tweet.get("note_tweet") or {}).get("note_tweet_results") or {}).get("result") or {}
    ).get("text")
    text = note or legacy.get("full_text")
    if not (post_id and handle and created_raw and text):
        return None
    try:
        created_at = datetime.strptime(created_raw, _X_DATE_FORMAT)
    except ValueError:
        return None

    followers = user_legacy.get("followers_count")
    return Post(
        id=str(post_id),
        text=text,
        author_handle=handle,
        author_name=user_core.get("name") or user_legacy.get("name") or "",
        author_followers=int(followers) if followers is not None else None,
        created_at=created_at,
        lang=legacy.get("lang"),
        is_reply=bool(legacy.get("in_reply_to_status_id_str")),
    )
