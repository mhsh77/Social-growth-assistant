"""Configuration loading. All settings live in config.yaml; secrets live in .env."""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from urllib.parse import quote

import yaml
from pydantic import BaseModel, Field


class Profile(BaseModel):
    handle: str = ""
    name: str = ""
    project_name: str = ""
    project_url: str = ""
    offer: str = (
        "Freelance AI engineer: I build and evaluate RAG systems and LLM agents, "
        "including tooling for Web3 / DeFi / DAO teams."
    )
    voice_examples: list[str] = Field(default_factory=list)
    topics: list[str] = Field(
        default_factory=lambda: [
            "RAG and retrieval quality, hallucination reduction",
            "Evaluating LLM systems (evals, benchmarks, regression testing)",
            "AI agents for Web3, DeFi and DAO tooling",
            "Freelance / independent AI engineering",
        ]
    )


class Sources(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    list_urls: list[str] = Field(default_factory=list)
    monitored_accounts: list[str] = Field(default_factory=list)
    search_language: str = "en"

    def search_query(self, keyword: str) -> str:
        query = f'"{keyword}"'
        if self.search_language:
            query += f" lang:{self.search_language}"
        return query

    def search_url(self, keyword: str) -> str:
        return f"https://x.com/search?q={quote(self.search_query(keyword))}&f=live"

    def page_urls(self) -> list[str]:
        return [self.search_url(k) for k in self.keywords] + list(self.list_urls)

    def monitored_set(self) -> set[str]:
        return {h.lstrip("@").lower() for h in self.monitored_accounts}


class Filters(BaseModel):
    max_age_hours: float = 24
    min_followers: int = 200
    max_followers: int = 200_000
    follower_filter_applies_to_monitored: bool = False
    languages: list[str] = Field(default_factory=lambda: ["en"])
    include_replies: bool = False
    exclude_handles: list[str] = Field(default_factory=list)


Effort = Literal["low", "medium", "high", "xhigh", "max"]


class Ranking(BaseModel):
    model: str = "claude-opus-5-5"
    effort: Effort | None = "low"  # None for models without effort support (e.g. Haiku 4.5)
    shortlist_size: int = Field(default=7, ge=1, le=50)
    min_relevance: float = 5
    min_opportunity: float = 4
    batch_size: int = Field(default=10, ge=1, le=50)
    max_to_rank: int = Field(default=60, ge=1)  # caps classification cost per run


class Drafting(BaseModel):
    model: str = "claude-opus-5-5"
    effort: Effort | None = "medium"
    drafts_per_post: int = Field(default=2, ge=1, le=3)
    max_chars: int = 280


class Review(BaseModel):
    reply_mode: Literal["intent", "open_post"] = "intent"


class LLM(BaseModel):
    refusal_fallback: bool = True


class Storage(BaseModel):
    data_dir: Path = Path("data")
    cache_ttl_hours: float = 72

    @property
    def db_path(self) -> Path:
        return self.data_dir / "sga.sqlite3"


class Server(BaseModel):
    port: int = 8765


class Config(BaseModel):
    profile: Profile = Field(default_factory=Profile)
    sources: Sources = Field(default_factory=Sources)
    filters: Filters = Field(default_factory=Filters)
    ranking: Ranking = Field(default_factory=Ranking)
    drafting: Drafting = Field(default_factory=Drafting)
    review: Review = Field(default_factory=Review)
    llm: LLM = Field(default_factory=LLM)
    storage: Storage = Field(default_factory=Storage)
    server: Server = Field(default_factory=Server)


def load_config(path: Path | str = "config.yaml") -> Config:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `sga init` to create it from config.example.yaml."
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Config.model_validate(data)
