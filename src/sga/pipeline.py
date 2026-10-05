"""Filter → rank → draft → save. Shared by `sga shortlist` and `sga daily`."""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .config import Config
from .drafting import draft_replies
from .filters import apply_filters
from .models import ShortlistItem
from .ranking import prioritize_for_scoring, score_posts, select_shortlist
from .store import Store


@dataclass
class RunResult:
    run_id: str
    captured: int
    after_filters: int
    scored: int
    shortlist: list[ShortlistItem]
    dropped: Counter
    warnings: list[str] = field(default_factory=list)


def new_run_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def build_shortlist(
    config: Config, store: Store, client: Any, with_drafts: bool = True
) -> RunResult:
    run_id = new_run_id()
    captured = store.candidates()
    kept, dropped = apply_filters(
        captured,
        config.filters,
        config.sources,
        own_handle=config.profile.handle,
        exclude_ids=store.acted_post_ids(),
    )
    to_score = prioritize_for_scoring(kept, config.sources, config.ranking.max_to_rank)
    warnings: list[str] = []
    if len(kept) > len(to_score):
        warnings.append(
            f"{len(kept) - len(to_score)} post(s) not ranked (ranking.max_to_rank="
            f"{config.ranking.max_to_rank})."
        )
    scores, score_warnings = score_posts(client, to_score, config) if to_score else ({}, [])
    warnings += score_warnings
    shortlist = select_shortlist(to_score, scores, config.ranking, config.sources)
    if with_drafts and shortlist:
        warnings += draft_replies(client, shortlist, config)

    store.save_shortlist(run_id, shortlist)
    store.record_run(run_id, len(captured), len(kept), len(shortlist))
    return RunResult(
        run_id=run_id,
        captured=len(captured),
        after_filters=len(kept),
        scored=len(scores),
        shortlist=shortlist,
        dropped=dropped,
        warnings=warnings,
    )
