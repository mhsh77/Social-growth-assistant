import re
from datetime import datetime, timedelta, timezone

from factories import FakeClient

from sga.config import Config, Sources
from sga.models import Post
from sga.pipeline import build_shortlist
from sga.store import Store


def responder(kwargs):
    content = kwargs["messages"][0]["content"]
    ids = re.findall(r'<post id="([^"]+)"', content)
    return {
        "items": [
            {
                "id": i,
                "relevance": 8,
                "opportunity": 8,
                "pitch_risk": 1,
                "topic": "evals",
                "reason": "asks a question",
                "mention_project": False,
            }
            for i in ids
        ]
    }


def test_build_shortlist_end_to_end_skips_reviewed_posts():
    now = datetime.now(timezone.utc)
    store = Store(":memory:")
    posts = [
        Post(
            id=str(i),
            text=f"question {i} about RAG evals?",
            author_handle=f"u{i}",
            author_followers=1000,
            created_at=now - timedelta(hours=1),
            lang="en",
            sources=["search:RAG"],
        )
        for i in range(3)
    ]
    store.add_candidates(posts)
    config = Config(sources=Sources(keywords=["RAG"]))

    first = build_shortlist(config, store, FakeClient(responder))
    assert len(first.shortlist) == 3
    assert store.shortlist(first.run_id)[0].post.id == first.shortlist[0].post.id

    store.log_event(first.run_id, first.shortlist[0], "skipped")
    second = build_shortlist(config, store, FakeClient(responder))
    assert len(second.shortlist) == 2
    assert second.dropped["already reviewed"] == 1
