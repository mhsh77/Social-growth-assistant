import pytest
from factories import NOW, FakeClient

from sga.config import Config, Profile
from sga.drafting import check_draft, draft_replies, drafts_for_item, first_sentence, x_length
from sga.llm import LLMError
from sga.models import Post, Scores, ShortlistItem

GOOD = (
    "We cut hallucinations most by scoring retrieval separately from generation. "
    "If recall@k is low, no prompt fixes it."
)


def item(mention_project=False):
    post = Post(
        id="1",
        text="How do you measure RAG hallucination?",
        author_handle="alice",
        author_followers=1000,
        created_at=NOW,
    )
    scores = Scores(
        relevance=9,
        opportunity=9,
        pitch_risk=1,
        topic="RAG evals",
        reason="asks how to measure",
        mention_project=mention_project,
    )
    return ShortlistItem(post=post, scores=scores, combined=9, why="search: RAG")


def config():
    return Config(profile=Profile(project_name="EvalKit", project_url="https://evalkit.dev"))


def check(text, allow=False):
    return check_draft(text, 280, allow, "EvalKit", "https://evalkit.dev")


# --- rule checks ---------------------------------------------------------------


def test_good_draft_passes():
    assert check(GOOD) == []


def test_x_length_counts_links_as_23_and_wide_chars_as_2():
    assert x_length("hi https://example.com/very/long/path/indeed") == 3 + 23
    assert x_length("日本") == 4
    assert x_length("café — ok") == 9


def test_too_long():
    assert "too long" in check("a" * 281)
    assert check("a" * 280) == []


@pytest.mark.parametrize(
    "text, problem",
    [
        ("Great post! " + GOOD, "generic opener"),
        ("love this. " + GOOD, "generic opener"),
        (GOOD + " #RAG #AI #LLM", "hashtag stuffing"),
        (GOOD + " DM me if you want help.", "salesy phrasing"),
        ("@alice " + GOOD, "starts with an @mention"),
        (GOOD + " see https://random.blog/post", "contains an unrelated link"),
    ],
)
def test_rule_violations(text, problem):
    assert problem in check(text)


def test_single_hashtag_is_fine():
    assert check(GOOD + " #RAG") == []


def test_project_mention_rules():
    late = GOOD + " We built EvalKit for exactly this: https://evalkit.dev"
    assert "mentions project when not relevant" in check(late, allow=False)
    assert check(late, allow=True) == []
    early = "EvalKit solves this. " + GOOD
    assert "project mentioned in first sentence" in check(early, allow=True)


def test_bare_link_drop():
    assert "bare link drop" in check("worth a look https://evalkit.dev", allow=True)


def test_first_sentence():
    assert first_sentence("One. Two? Three") == "One."
    assert first_sentence("line one\nline two") == "line one"


# --- generation with retry -----------------------------------------------------


def drafts_reply(*texts):
    return {"drafts": [{"text": t, "angle": "a"} for t in texts]}


def test_clean_drafts_need_one_call():
    client = FakeClient(lambda kw: drafts_reply(GOOD, GOOD + " What's your eval set?"))
    drafts = drafts_for_item(client, item(), config())
    assert len(drafts) == 2 and len(client.calls) == 1
    assert all(d.warnings == [] for d in drafts)


def test_bad_drafts_trigger_one_retry_with_feedback():
    replies = iter([drafts_reply("Great post!", "x" * 400), drafts_reply(GOOD, GOOD + " Why?")])
    client = FakeClient(lambda kw: next(replies))
    drafts = drafts_for_item(client, item(), config())
    assert len(client.calls) == 2
    assert "generic opener" in client.calls[1]["messages"][0]["content"]
    assert [d.text for d in drafts] == [GOOD, GOOD + " Why?"]


def test_hard_problems_dropped_soft_ones_kept_as_warnings_after_retry():
    bad = drafts_reply("Great post! " + GOOD, "y" * 400)
    client = FakeClient(lambda kw: bad)
    drafts = drafts_for_item(client, item(), config())
    assert len(client.calls) == 2  # one retry, never more
    assert len(drafts) == 1 and drafts[0].warnings == ["generic opener"]


def test_project_allowed_only_when_classifier_said_relevant():
    text = GOOD + " EvalKit does this."
    client = FakeClient(lambda kw: drafts_reply(text))
    assert drafts_for_item(client, item(mention_project=False), config()) == []
    assert "Do not mention any project" in client.calls[0]["messages"][0]["content"]
    client = FakeClient(lambda kw: drafts_reply(text))
    assert len(drafts_for_item(client, item(mention_project=True), config())) == 1


def test_draft_replies_survives_llm_failure():
    def responder(kw):
        raise LLMError("boom")

    items = [item()]
    warnings = draft_replies(FakeClient(responder), items, config())
    assert items[0].drafts == [] and "boom" in warnings[0]
