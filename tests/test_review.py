from urllib.parse import parse_qs, urlparse

from factories import NOW
from rich.console import Console

from sga.config import Config, Review
from sga.models import Draft, Post, Scores, ShortlistItem
from sga.review import Reviewer, reply_url
from sga.store import Store


def make_item(id):
    post = Post(
        id=id, text=f"post {id}?", author_handle=f"u{id}", author_followers=900, created_at=NOW
    )
    scores = Scores(
        relevance=8, opportunity=8, pitch_risk=1, topic="t", reason="r", mention_project=False
    )
    drafts = [
        Draft(text=f"draft A for {id}", angle="a"),
        Draft(text=f"draft B for {id}", angle="b"),
    ]
    return ShortlistItem(post=post, scores=scores, combined=8, why="w", drafts=drafts)


def reviewer(answers, edits=(), config=None, store=None):
    answers, edits = iter(answers), iter(edits)
    opened = []
    r = Reviewer(
        config or Config(),
        store or Store(":memory:"),
        console=Console(file=open("/dev/null", "w")),
        ask=lambda prompt: next(answers),
        edit=lambda text: next(edits),
        open_url=opened.append,
    )
    return r, opened


def actions(store):
    return [(r["post_id"], r["action"], r["final_text"]) for r in store.events_between(0, 1e12)]


def test_reply_url_prefills_text_and_targets_the_post():
    item = make_item("123")
    url = reply_url(item, "hi & bye", "intent")
    q = parse_qs(urlparse(url).query)
    assert url.startswith("https://x.com/intent/tweet?")
    assert q == {"in_reply_to": ["123"], "text": ["hi & bye"]}
    assert reply_url(item, "x", "open_post") == "https://x.com/u123/status/123"


def test_each_approval_opens_exactly_one_tab_and_skip_opens_none():
    store = Store(":memory:")
    items = [make_item("1"), make_item("2"), make_item("3")]
    r, opened = reviewer(["2", "s", "1"], store=store)
    stats = r.run("run", items)
    assert (stats.approved, stats.skipped) == (2, 1)
    assert len(opened) == 2
    assert "in_reply_to=1" in opened[0] and "in_reply_to=3" in opened[1]
    logged = [a for a in actions(store) if a[1] != "shown"]
    assert logged == [
        ("1", "approved", "draft B for 1"),
        ("2", "skipped", None),
        ("3", "approved", "draft A for 3"),
    ]


def test_quit_leaves_rest_for_later_and_nothing_opens():
    store = Store(":memory:")
    items = [make_item("1"), make_item("2")]
    r, opened = reviewer(["q"], store=store)
    stats = r.run("run", items)
    assert stats.remaining == 2 and opened == []
    r2, opened2 = reviewer(["s", "1"], store=store)
    assert r2.run("run", items).skipped == 1  # resumes with both still pending


def test_edit_then_confirm_logs_final_text():
    store = Store(":memory:")
    r, opened = reviewer(["e1", "y"], edits=["my tweaked reply"], store=store)
    assert r.run("run", [make_item("1")]).edited == 1
    assert "text=my+tweaked+reply" in opened[0]
    assert ("1", "edited", "my tweaked reply") in actions(store)


def test_declining_edit_returns_to_menu_without_opening():
    r, opened = reviewer(["e2", "n", "s"], edits=["changed"])
    stats = r.run("run", [make_item("1")])
    assert stats.skipped == 1 and opened == []


def test_write_your_own_and_invalid_input():
    r, opened = reviewer(["9", "w", "y"], edits=["from scratch"])
    assert r.run("run", [make_item("1")]).edited == 1
    assert "from+scratch" in opened[0]


def test_already_reviewed_items_are_not_shown_again():
    store = Store(":memory:")
    item = make_item("1")
    store.log_event("old", item, "approved", 0, "x")
    r, opened = reviewer([], store=store)
    stats = r.run("run", [item])
    assert stats.approved == 0 and opened == []


def test_open_post_mode_opens_the_post_itself():
    r, opened = reviewer(["1"], config=Config(review=Review(reply_mode="open_post")))
    r.run("run", [make_item("5")])
    assert opened == ["https://x.com/u5/status/5"]


def test_default_editor_uses_click_edit(monkeypatch):
    import click

    monkeypatch.setattr(click, "edit", lambda text: text + " (edited)")
    r = Reviewer(Config(), Store(":memory:"))
    assert r.edit("draft") == "draft (edited)"
