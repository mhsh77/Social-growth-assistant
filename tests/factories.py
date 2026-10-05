"""Builders for X GraphQL payloads shaped like what x.com's web app receives.

These mirror the real SearchTimeline / ListLatestTweetsTimeline structure closely enough to
exercise the parser. If X changes the shape, capture a real payload with
`sga collect --save-raw` and add it under tests/fixtures/.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def x_date(dt: datetime) -> str:
    return dt.strftime("%a %b %d %H:%M:%S %z %Y")


def user(handle: str, followers: int, new_schema: bool = True) -> dict:
    result = {
        "__typename": "User",
        "rest_id": f"u_{handle}",
        "legacy": {"followers_count": followers},
    }
    if new_schema:
        result["core"] = {"screen_name": handle, "name": handle.title()}
    else:
        result["legacy"].update({"screen_name": handle, "name": handle.title()})
    return {"result": result}


def tweet(
    tweet_id: str,
    text: str,
    handle: str = "builder",
    followers: int = 1500,
    age_hours: float = 2,
    lang: str = "en",
    reply_to: str | None = None,
    new_schema: bool = True,
    note_text: str | None = None,
    retweet_of: dict | None = None,
) -> dict:
    legacy = {
        "id_str": tweet_id,
        "full_text": text,
        "created_at": x_date(NOW - timedelta(hours=age_hours)),
        "lang": lang,
    }
    if reply_to:
        legacy["in_reply_to_status_id_str"] = reply_to
    if retweet_of:
        legacy["retweeted_status_result"] = {"result": retweet_of}
    node = {
        "__typename": "Tweet",
        "rest_id": tweet_id,
        "core": {"user_results": user(handle, followers, new_schema)},
        "legacy": legacy,
    }
    if note_text:
        node["note_tweet"] = {"note_tweet_results": {"result": {"text": note_text}}}
    return node


def entry(result: dict, promoted: bool = False) -> dict:
    item = {"itemType": "TimelineTweet", "tweet_results": {"result": result}}
    if promoted:
        item["promotedMetadata"] = {"advertiser_results": {}}
    return {"entryId": "tweet-x", "content": {"itemContent": item}}


def search_payload(*entries: dict) -> dict:
    return {
        "data": {
            "search_by_raw_query": {
                "search_timeline": {
                    "timeline": {
                        "instructions": [{"type": "TimelineAddEntries", "entries": list(entries)}]
                    }
                }
            }
        }
    }
