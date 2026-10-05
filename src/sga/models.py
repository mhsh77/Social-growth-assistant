"""Core data types shared across the pipeline."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Post(BaseModel):
    """The minimum we keep about someone else's post, and only for the cache TTL."""

    id: str
    text: str
    author_handle: str
    author_name: str = ""
    author_followers: int | None = None
    created_at: datetime
    lang: str | None = None
    is_reply: bool = False
    # Why we have this post: "search:<keyword>" or "list". A post can be found more than once.
    sources: list[str] = Field(default_factory=list)

    @property
    def url(self) -> str:
        return f"https://x.com/{self.author_handle}/status/{self.id}"


class Scores(BaseModel):
    relevance: float  # 0-10: fit with my work
    opportunity: float  # 0-10: would a substantive reply add value?
    pitch_risk: float  # 0-10: would any reply from me look like an unsolicited pitch?
    topic: str
    reason: str
    mention_project: bool  # is my project directly relevant to this conversation?


class Draft(BaseModel):
    text: str
    angle: str  # one line: what this draft contributes
    warnings: list[str] = Field(default_factory=list)  # validator findings that survived a retry


class ShortlistItem(BaseModel):
    post: Post
    scores: Scores
    combined: float
    why: str  # human-readable "why suggested"
    drafts: list[Draft] = Field(default_factory=list)
