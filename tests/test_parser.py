from factories import entry, search_payload, tweet

from sga.parser import extract_posts


def test_extracts_basic_fields():
    payload = search_payload(entry(tweet("1", "How do you evaluate RAG?", "alice", 900)))
    [post] = extract_posts(payload)
    assert post.id == "1"
    assert post.text == "How do you evaluate RAG?"
    assert post.author_handle == "alice"
    assert post.author_followers == 900
    assert post.lang == "en"
    assert post.url == "https://x.com/alice/status/1"
    assert post.created_at.tzinfo is not None


def test_supports_old_user_schema():
    payload = search_payload(entry(tweet("1", "hi", "bob", new_schema=False)))
    [post] = extract_posts(payload)
    assert post.author_handle == "bob"


def test_unwraps_visibility_wrapper():
    wrapped = {"__typename": "TweetWithVisibilityResults", "tweet": tweet("7", "wrapped")}
    [post] = extract_posts(search_payload(entry(wrapped)))
    assert post.id == "7"


def test_skips_promoted_posts():
    payload = search_payload(entry(tweet("ad", "Buy now"), promoted=True), entry(tweet("2", "ok")))
    assert [p.id for p in extract_posts(payload)] == ["2"]


def test_retweet_yields_original_post():
    original = tweet("orig", "original thought", "carol", 3000)
    rt = tweet("rt", "RT @carol: original thought", "dave", retweet_of=original)
    [post] = extract_posts(search_payload(entry(rt)))
    assert (post.id, post.author_handle) == ("orig", "carol")


def test_prefers_long_note_text():
    t = tweet("1", "short…", note_text="the full long-form post")
    [post] = extract_posts(search_payload(entry(t)))
    assert post.text == "the full long-form post"


def test_marks_replies_and_dedupes_ids():
    payload = search_payload(
        entry(tweet("1", "a reply", reply_to="0")), entry(tweet("1", "a reply", reply_to="0"))
    )
    [post] = extract_posts(payload)
    assert post.is_reply


def test_ignores_incomplete_and_garbage():
    broken = {"__typename": "Tweet", "legacy": {"full_text": "no id or user"}}
    assert extract_posts(search_payload(entry(broken))) == []
    assert extract_posts(None) == []
    assert extract_posts({"data": "unexpected"}) == []
