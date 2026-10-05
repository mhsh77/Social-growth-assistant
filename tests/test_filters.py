from datetime import timedelta

from factories import NOW

from sga.config import Filters, Sources
from sga.filters import apply_filters, dedupe, normalize_text
from sga.models import Post


def post(id, text=None, handle="alice", followers=1000, age_h=1, **kw):
    return Post(
        id=id,
        text=text or f"post {id} about RAG evals",
        author_handle=handle,
        author_followers=followers,
        created_at=NOW - timedelta(hours=age_h),
        lang=kw.pop("lang", "en"),
        **kw,
    )


def run(posts, filters=None, sources=None, **kw):
    return apply_filters(posts, filters or Filters(), sources or Sources(), now=NOW, **kw)


def test_normalize_ignores_links_mentions_and_punctuation():
    assert normalize_text("@bob Great point!! https://t.co/x") == normalize_text("great point")


def test_dedupe_merges_sources_for_same_id():
    a = post("1", sources=["search:RAG"])
    b = post("1", sources=["list"])
    [only] = dedupe([a, b])
    assert only.sources == ["list", "search:RAG"]


def test_dedupe_keeps_earliest_copy_of_identical_text():
    original = post("1", "Same text here", handle="orig", age_h=5)
    copy = post("2", "same text here!! https://spam.link", handle="copycat", age_h=1)
    assert [p.id for p in dedupe([copy, original])] == ["1"]


def test_drops_old_posts():
    kept, dropped = run([post("1", age_h=30), post("2", age_h=2)])
    assert [p.id for p in kept] == ["2"]
    assert dropped["too old"] == 1


def test_follower_thresholds():
    posts = [post("1", followers=10), post("2", followers=5000), post("3", followers=10**6)]
    kept, dropped = run(posts)
    assert [p.id for p in kept] == ["2"]
    assert dropped["too few followers"] == 1
    assert dropped["too many followers"] == 1


def test_monitored_accounts_bypass_follower_filter_by_default():
    sources = Sources(monitored_accounts=["@BigProtocol"])
    big = post("1", handle="bigprotocol", followers=900_000)
    kept, _ = run([big], sources=sources)
    assert kept == [big]
    kept, _ = run([big], Filters(follower_filter_applies_to_monitored=True), sources)
    assert kept == []


def test_unknown_followers_dropped_for_non_monitored():
    _, dropped = run([post("1", followers=None)])
    assert dropped["follower count unknown"] == 1


def test_excludes_own_handle_replies_language_and_reviewed():
    posts = [
        post("1", handle="Me"),
        post("2", is_reply=True),
        post("3", lang="es"),
        post("4"),
        post("5", text="another distinct text"),
    ]
    kept, dropped = run(posts, own_handle="@me", exclude_ids={"4"})
    assert [p.id for p in kept] == ["5"]
    assert dropped == {
        "excluded account": 1,
        "is a reply": 1,
        "language": 1,
        "already reviewed": 1,
    }


def test_replies_allowed_when_configured():
    kept, _ = run([post("1", is_reply=True)], Filters(include_replies=True))
    assert len(kept) == 1
