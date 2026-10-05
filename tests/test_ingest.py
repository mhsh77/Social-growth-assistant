import json
import urllib.error
import urllib.request

import pytest
from factories import entry, search_payload, tweet

from sga.config import Sources
from sga.ingest import CaptureServer
from sga.sources import describe_why, source_for_page
from sga.store import Store

SEARCH_PAGE = "https://x.com/search?q=%22RAG%20hallucination%22%20lang%3Aen&f=live"


@pytest.fixture
def server():
    store = Store(":memory:")
    srv = CaptureServer(store, Sources(keywords=["RAG hallucination"]), port=0)
    srv.start()
    yield srv
    srv.stop()


def post_json(srv, body, headers=None):
    req = urllib.request.Request(
        f"http://127.0.0.1:{srv.port}/ingest",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read())


def test_ingest_stores_posts_with_source_label(server):
    payload = search_payload(entry(tweet("1", "RAG hallucination is killing us")))
    status, result = post_json(
        server,
        {"operation": "SearchTimeline", "pageUrl": SEARCH_PAGE, "payload": payload},
        {"Origin": "chrome-extension://abc"},
    )
    assert status == 200 and result["accepted"] == 1
    [stored] = server.store.candidates()
    assert stored.sources == ["search:RAG hallucination"]


def test_same_post_from_two_pages_merges_sources(server):
    payload = search_payload(entry(tweet("1", "hello")))
    post_json(server, {"pageUrl": SEARCH_PAGE, "payload": payload})
    _, result = post_json(server, {"pageUrl": "https://x.com/i/lists/123", "payload": payload})
    assert result["accepted"] == 0
    [stored] = server.store.candidates()
    assert stored.sources == ["list", "search:RAG hallucination"]


def test_ignores_pages_we_do_not_collect_from(server):
    payload = search_payload(entry(tweet("1", "home timeline post")))
    _, result = post_json(server, {"pageUrl": "https://x.com/home", "payload": payload})
    assert result["accepted"] == 0
    assert server.store.candidate_count() == 0


def test_rejects_web_page_origins_and_non_json(server):
    status, _ = post_json(server, {"pageUrl": SEARCH_PAGE}, {"Origin": "https://evil.example"})
    assert status == 403
    req = urllib.request.Request(
        f"http://127.0.0.1:{server.port}/ingest",
        data=b"x",
        method="POST",
        headers={"Content-Type": "text/plain"},
    )
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(req)
    assert err.value.code == 415


def test_source_for_page_labels():
    s = Sources(keywords=["DAO treasury"])
    url = "https://x.com/search?q=%22DAO%20treasury%22"
    assert source_for_page(url, s) == "search:DAO treasury"
    assert source_for_page("https://x.com/i/lists/42", s) == "list"
    assert source_for_page("https://x.com/home", s) is None
    assert source_for_page("https://evil.example/search?q=x", s) is None


def test_describe_why_combines_reasons():
    from factories import NOW

    from sga.models import Post

    s = Sources(keywords=["DAO treasury", "RAG"], monitored_accounts=["@alice"])
    p = Post(
        id="1",
        text="Our DAO treasury bot uses RAG",
        author_handle="Alice",
        created_at=NOW,
        sources=["search:DAO treasury", "list"],
    )
    assert describe_why(p, s) == (
        'search: "DAO treasury"; mentions: "RAG"; monitored account @Alice'
    )
