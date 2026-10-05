"""SQLite storage.

Two kinds of data, kept on different clocks:
  * Other people's posts (`candidates`, `shortlist`) are a short-lived cache, deleted
    after `storage.cache_ttl_hours`.
  * Your own activity (`events`, `runs`) is kept so you can track what worked. It holds
    post URLs, author handles and your reply text, not other people's post text.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterable
from pathlib import Path

from .models import Post, ShortlistItem

SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    captured_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS shortlist (
    run_id TEXT NOT NULL,
    rank INTEGER NOT NULL,
    post_id TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (run_id, rank)
);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    captured INTEGER NOT NULL,
    after_filters INTEGER NOT NULL,
    shortlisted INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    run_id TEXT NOT NULL,
    post_id TEXT NOT NULL,
    post_url TEXT NOT NULL,
    author_handle TEXT NOT NULL,
    action TEXT NOT NULL,          -- shown | approved | edited | skipped | opened
    draft_index INTEGER,
    draft_text TEXT,
    final_text TEXT,
    why TEXT
);
"""


class Store:
    def __init__(self, path: Path | str):
        path = Path(path)
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: the capture server writes from its handler threads.
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # --- candidates (short-lived cache) -------------------------------------------

    def add_candidates(self, posts: Iterable[Post], now: float | None = None) -> int:
        """Insert posts, merging `sources` when a post was already captured. Returns new count."""
        now = time.time() if now is None else now
        added = 0
        with self.conn:
            for post in posts:
                row = self.conn.execute(
                    "SELECT data FROM candidates WHERE id = ?", (post.id,)
                ).fetchone()
                if row is None:
                    self.conn.execute(
                        "INSERT INTO candidates (id, data, captured_at) VALUES (?, ?, ?)",
                        (post.id, post.model_dump_json(), now),
                    )
                    added += 1
                    continue
                existing = Post.model_validate_json(row["data"])
                merged = post.model_copy(
                    update={"sources": sorted(set(existing.sources) | set(post.sources))}
                )
                self.conn.execute(
                    "UPDATE candidates SET data = ? WHERE id = ?",
                    (merged.model_dump_json(), post.id),
                )
        return added

    def candidates(self, since: float | None = None) -> list[Post]:
        query, args = "SELECT data FROM candidates", ()
        if since is not None:
            query, args = query + " WHERE captured_at >= ?", (since,)
        return [Post.model_validate_json(r["data"]) for r in self.conn.execute(query, args)]

    def candidate_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]

    # --- shortlist ----------------------------------------------------------------

    def save_shortlist(self, run_id: str, items: list[ShortlistItem], now: float | None = None):
        now = time.time() if now is None else now
        with self.conn:
            self.conn.execute("DELETE FROM shortlist WHERE run_id = ?", (run_id,))
            for rank, item in enumerate(items, start=1):
                self.conn.execute(
                    "INSERT INTO shortlist (run_id, rank, post_id, data, created_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (run_id, rank, item.post.id, item.model_dump_json(), now),
                )

    def shortlisted_post_ids(self, run_ids: list[str]) -> set[str]:
        if not run_ids:
            return set()
        marks = ",".join("?" * len(run_ids))
        rows = self.conn.execute(
            f"SELECT DISTINCT post_id FROM shortlist WHERE run_id IN ({marks})", run_ids
        )
        return {r["post_id"] for r in rows}

    def latest_run_id(self) -> str | None:
        row = self.conn.execute(
            "SELECT run_id FROM shortlist ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        return row["run_id"] if row else None

    def shortlist(self, run_id: str) -> list[ShortlistItem]:
        rows = self.conn.execute(
            "SELECT data FROM shortlist WHERE run_id = ? ORDER BY rank", (run_id,)
        )
        return [ShortlistItem.model_validate_json(r["data"]) for r in rows]

    # --- your activity (kept) -----------------------------------------------------

    def record_run(
        self, run_id: str, captured: int, after_filters: int, shortlisted: int, now=None
    ) -> None:
        now = time.time() if now is None else now
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO runs VALUES (?, ?, ?, ?, ?)",
                (run_id, now, captured, after_filters, shortlisted),
            )

    def log_event(
        self,
        run_id: str,
        item: ShortlistItem,
        action: str,
        draft_index: int | None = None,
        final_text: str | None = None,
        now: float | None = None,
    ) -> None:
        draft_text = (
            item.drafts[draft_index].text
            if draft_index is not None and draft_index < len(item.drafts)
            else None
        )
        with self.conn:
            self.conn.execute(
                "INSERT INTO events (ts, run_id, post_id, post_url, author_handle, action,"
                " draft_index, draft_text, final_text, why) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    time.time() if now is None else now,
                    run_id,
                    item.post.id,
                    item.post.url,
                    item.post.author_handle,
                    action,
                    draft_index,
                    draft_text,
                    final_text,
                    item.why,
                ),
            )

    def acted_post_ids(self) -> set[str]:
        """Posts you already approved or skipped; never shortlist them again."""
        rows = self.conn.execute(
            "SELECT DISTINCT post_id FROM events WHERE action IN ('approved', 'edited', 'skipped')"
        )
        return {r["post_id"] for r in rows}

    def events_between(self, start: float, end: float) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT * FROM events WHERE ts >= ? AND ts < ? ORDER BY ts", (start, end)
            )
        )

    def runs_between(self, start: float, end: float) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT * FROM runs WHERE ts >= ? AND ts < ? ORDER BY ts", (start, end)
            )
        )

    # --- retention ----------------------------------------------------------------

    def purge(self, ttl_hours: float, now: float | None = None) -> int:
        cutoff = (time.time() if now is None else now) - ttl_hours * 3600
        with self.conn:
            a = self.conn.execute("DELETE FROM candidates WHERE captured_at < ?", (cutoff,))
            b = self.conn.execute("DELETE FROM shortlist WHERE created_at < ?", (cutoff,))
        return a.rowcount + b.rowcount
