import re
from datetime import timedelta

import pytest
from factories import NOW, FakeClient

from sga.config import Config, Ranking, Sources
from sga.llm import LLMError, complete_json
from sga.models import Post, Scores
from sga.ranking import (
    parse_scores,
    prioritize_for_scoring,
    score_posts,
    select_shortlist,
)


def post(id, handle=None, text=None, age_h=1):
    return Post(
        id=id,
        text=text or f"post {id}",
        author_handle=handle or f"user{id}",
        author_followers=1000,
        created_at=NOW - timedelta(hours=age_h),
    )


def scores(rel, opp, risk=0, mention=False):
    return Scores(
        relevance=rel,
        opportunity=opp,
        pitch_risk=risk,
        topic="t",
        reason="r",
        mention_project=mention,
    )


def test_parse_scores_clamps_and_ignores_unknown_ids():
    data = {
        "items": [
            {
                "id": "1",
                "relevance": 14,
                "opportunity": -3,
                "pitch_risk": "x",
                "topic": "RAG",
                "reason": "asks how to eval",
                "mention_project": True,
            },
            {
                "id": "ghost",
                "relevance": 9,
                "opportunity": 9,
                "pitch_risk": 0,
                "topic": "",
                "reason": "",
                "mention_project": False,
            },
            "garbage",
        ]
    }
    result = parse_scores(data, [post("1")])
    assert set(result) == {"1"}
    assert (result["1"].relevance, result["1"].opportunity, result["1"].pitch_risk) == (10, 0, 0)


def test_shortlist_orders_by_combined_score_and_applies_thresholds():
    posts = [post("a"), post("b"), post("c"), post("d")]
    s = {
        "a": scores(6, 6),  # 6.0
        "b": scores(9, 9),  # 9.0
        "c": scores(9, 2),  # below min_opportunity
        "d": scores(9, 9, risk=9),  # pitch risk cutoff
    }
    result = select_shortlist(posts, s, Ranking(), Sources())
    assert [i.post.id for i in result] == ["b", "a"]


def test_pitch_risk_lowers_rank_below_cutoff():
    posts = [post("safe"), post("salesy")]
    s = {"safe": scores(8, 8), "salesy": scores(8, 8, risk=6)}
    assert [i.post.id for i in select_shortlist(posts, s, Ranking(), Sources())] == [
        "safe",
        "salesy",
    ]


def test_monitored_bonus_breaks_close_calls():
    posts = [post("1", "stranger"), post("2", "friend")]
    s = {"1": scores(8, 8), "2": scores(8, 7.5)}
    result = select_shortlist(posts, s, Ranking(), Sources(monitored_accounts=["@Friend"]))
    assert [i.post.id for i in result] == ["2", "1"]
    assert "monitored account @friend" in result[0].why


def test_one_post_per_author_and_size_limit():
    posts = [post("1", "same"), post("2", "same"), post("3"), post("4"), post("5")]
    s = {p.id: scores(9, 9 - i * 0.1) for i, p in enumerate(posts)}
    result = select_shortlist(posts, s, Ranking(shortlist_size=3), Sources())
    assert [i.post.id for i in result] == ["1", "3", "4"]


def test_ties_prefer_newer_posts():
    posts = [post("old", age_h=10), post("new", age_h=1)]
    s = {"old": scores(8, 8), "new": scores(8, 8)}
    assert [i.post.id for i in select_shortlist(posts, s, Ranking(), Sources())] == ["new", "old"]


def test_prioritize_prefers_signal_then_recency():
    sources = Sources(keywords=["DAO treasury"], monitored_accounts=["vip"])
    posts = [
        post("plain-new", age_h=1),
        post("kw", text="our DAO treasury tooling", age_h=5),
        post("vip-kw", "vip", text="DAO treasury question", age_h=9),
    ]
    ordered = prioritize_for_scoring(posts, sources, limit=2)
    assert [p.id for p in ordered] == ["vip-kw", "kw"]


def _echo_scores(kwargs):
    ids = re.findall(r'<post id="([^"]+)"', kwargs["messages"][0]["content"])
    return {
        "items": [
            {
                "id": i,
                "relevance": 7,
                "opportunity": 7,
                "pitch_risk": 1,
                "topic": "t",
                "reason": "r",
                "mention_project": False,
            }
            for i in ids
        ]
    }


def test_score_posts_batches_and_survives_a_failed_batch():
    calls = {"n": 0}

    def responder(kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            return ("refusal", {})
        return _echo_scores(kwargs)

    config = Config(ranking=Ranking(batch_size=2))
    posts = [post(str(i)) for i in range(5)]
    client = FakeClient(responder)
    result, warnings = score_posts(client, posts, config)
    assert len(client.calls) == 3  # batches of 2, 2, 1
    assert set(result) == {"0", "1", "4"}
    assert len(warnings) == 1 and "declined" in warnings[0]


def test_request_shape_includes_schema_effort_and_fallback():
    client = FakeClient(lambda kw: {"items": []})
    complete_json(client, model="m", system="s", user="u", schema={"type": "object"}, effort="low")
    sent = client.calls[0]
    assert sent["output_config"]["effort"] == "low"
    assert sent["output_config"]["format"]["type"] == "json_schema"
    assert sent["fallbacks"] == "default"
    client = FakeClient(lambda kw: {"items": []})
    complete_json(client, model="m", system="s", user="u", schema={}, refusal_fallback=False)
    assert "fallbacks" not in client.calls[0] and "effort" not in client.calls[0]["output_config"]


@pytest.mark.parametrize(
    "reply", [("max_tokens", {}), ("end_turn", "not json"), ("end_turn", "[1, 2]")]
)
def test_complete_json_rejects_unusable_output(reply):
    with pytest.raises(LLMError):
        complete_json(FakeClient(lambda kw: reply), model="m", system="s", user="u", schema={})
