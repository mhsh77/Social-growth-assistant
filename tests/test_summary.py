from datetime import date, datetime, time, timedelta

from factories import NOW

from sga.models import Post, Scores, ShortlistItem
from sga.store import Store
from sga.summary import format_summary, summarize_day

DAY = date(2026, 10, 4)
NOON = datetime.combine(DAY, time(12)).astimezone().timestamp()


def item(id, why):
    post = Post(id=id, text="t", author_handle="a", created_at=NOW)
    s = Scores(
        relevance=8, opportunity=8, pitch_risk=0, topic="t", reason="r", mention_project=False
    )
    return ShortlistItem(post=post, scores=s, combined=8, why=why)


def test_summarize_day_counts_only_that_day():
    store = Store(":memory:")
    store.record_run("r1", captured=80, after_filters=30, shortlisted=7, now=NOON)
    store.record_run("r2", captured=95, after_filters=10, shortlisted=3, now=NOON + 3600)
    store.record_run("other", captured=999, after_filters=999, shortlisted=9, now=NOON + 86400)
    a = item("1", 'search: "DAO treasury" | t: r')
    b = item("2", "monitored account @x | t: r")
    c = item("3", 'search: "RAG" | t: r')
    store.log_event("r1", a, "shown", now=NOON)
    store.log_event("r1", a, "approved", now=NOON)
    store.log_event("r1", b, "edited", now=NOON)
    store.log_event("r1", c, "skipped", now=NOON)
    store.log_event("r1", c, "approved", now=NOON + 86400)  # next day

    s = summarize_day(store, DAY)
    assert (s.runs, s.captured, s.after_filters, s.shortlisted) == (2, 95, 30, 7)
    assert (s.reviewed, s.approved, s.edited, s.skipped) == (3, 1, 1, 1)
    assert s.approved_by_source == {"DAO treasury": 1, "monitored accounts": 1}
    text = format_summary(s)
    assert "2 opened for you to send" in text and "DAO treasury (1)" in text


def test_empty_day():
    assert "no activity" in format_summary(summarize_day(Store(":memory:"), DAY - timedelta(1)))


def test_shortlisted_counts_unique_posts_across_runs():
    store = Store(":memory:")
    store.record_run("r1", captured=5, after_filters=5, shortlisted=2, now=NOON)
    store.record_run("r2", captured=6, after_filters=5, shortlisted=2, now=NOON + 60)
    store.save_shortlist("r1", [item("1", ""), item("2", "")], now=NOON)
    store.save_shortlist("r2", [item("2", ""), item("3", "")], now=NOON + 60)
    assert summarize_day(store, DAY).shortlisted == 3
