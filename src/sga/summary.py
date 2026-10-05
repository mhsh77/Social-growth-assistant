"""Daily summary built from the run and activity logs."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from .store import Store

_SEARCH_RE = re.compile(r'"([^"]+)"')


@dataclass
class DaySummary:
    day: date
    runs: int = 0
    captured: int = 0
    after_filters: int = 0
    shortlisted: int = 0
    reviewed: int = 0
    approved: int = 0  # as-is
    edited: int = 0  # edited (or written) then approved
    skipped: int = 0
    approved_by_source: Counter = field(default_factory=Counter)

    @property
    def sent_to_browser(self) -> int:
        return self.approved + self.edited


def _day_bounds(day: date) -> tuple[float, float]:
    start = datetime.combine(day, time.min).astimezone()  # local midnight
    return start.timestamp(), (start + timedelta(days=1)).timestamp()


def summarize_day(store: Store, day: date) -> DaySummary:
    start, end = _day_bounds(day)
    summary = DaySummary(day=day)
    runs = store.runs_between(start, end)
    # Later runs re-read the same cache, so report peaks/unique posts instead of sums.
    for run in runs:
        summary.runs += 1
        summary.captured = max(summary.captured, run["captured"])
        summary.after_filters = max(summary.after_filters, run["after_filters"])
        summary.shortlisted = max(summary.shortlisted, run["shortlisted"])
    unique = store.shortlisted_post_ids([r["run_id"] for r in runs])
    summary.shortlisted = max(summary.shortlisted, len(unique))  # shortlists purge after TTL

    reviewed: set[str] = set()
    for event in store.events_between(start, end):
        action = event["action"]
        if action in ("approved", "edited", "skipped"):
            reviewed.add(event["post_id"])
            setattr(summary, action, getattr(summary, action) + 1)
        if action in ("approved", "edited"):
            why = (event["why"] or "").split("|", 1)[0]
            label = ", ".join(_SEARCH_RE.findall(why.split(";", 1)[0])) if "search:" in why else ""
            if "monitored account" in why:
                label = "monitored accounts"
            summary.approved_by_source[label or "other"] += 1
    summary.reviewed = len(reviewed)
    return summary


def format_summary(s: DaySummary) -> str:
    if not s.runs and not s.reviewed:
        return f"{s.day:%a %b %d}: no activity."
    lines = [
        f"{s.day:%a %b %d}: {s.runs} run(s), {s.captured} posts captured, "
        f"{s.after_filters} passed filters, {s.shortlisted} shortlisted.",
        f"  Reviewed {s.reviewed}: {s.approved} approved as-is, {s.edited} edited, "
        f"{s.skipped} skipped → {s.sent_to_browser} opened for you to send.",
    ]
    if s.approved_by_source:
        top = ", ".join(f"{k} ({v})" for k, v in s.approved_by_source.most_common(3))
        lines.append(f"  Approvals came from: {top}")
    return "\n".join(lines)
