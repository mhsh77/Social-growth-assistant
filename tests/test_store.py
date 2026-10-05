from factories import NOW

from sga.models import Post
from sga.store import Store


def p(id, sources=("list",)):
    return Post(id=id, text="t", author_handle="a", created_at=NOW, sources=list(sources))


def test_add_candidates_counts_only_new():
    store = Store(":memory:")
    assert store.add_candidates([p("1"), p("2")]) == 2
    assert store.add_candidates([p("2", ["search:x"]), p("3")]) == 1
    merged = {c.id: c for c in store.candidates()}["2"]
    assert merged.sources == ["list", "search:x"]


def test_purge_removes_only_expired_cache():
    store = Store(":memory:")
    store.add_candidates([p("old")], now=1_000)
    store.add_candidates([p("new")], now=1_000 + 71 * 3600)
    removed = store.purge(ttl_hours=72, now=1_000 + 73 * 3600)
    assert removed == 1
    assert [c.id for c in store.candidates()] == ["new"]
