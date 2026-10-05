"""Interactive, one-item-at-a-time review. The only outward action is opening a browser tab
for a single item you approved; you still read it and click Reply yourself on X."""

from __future__ import annotations

import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlencode

import click
import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .config import Config
from .drafting import check_draft, x_length
from .models import ShortlistItem
from .store import Store


def reply_url(item: ShortlistItem, text: str, mode: str) -> str:
    """URL that opens X's reply composer for this post with `text` pre-filled."""
    if mode == "open_post":
        return item.post.url
    return "https://x.com/intent/tweet?" + urlencode({"in_reply_to": item.post.id, "text": text})


def _ago(dt: datetime) -> str:
    minutes = int((datetime.now(timezone.utc) - dt).total_seconds() // 60)
    return f"{minutes}m ago" if minutes < 60 else f"{minutes // 60}h ago"


@dataclass
class ReviewStats:
    approved: int = 0
    edited: int = 0
    skipped: int = 0
    remaining: int = 0


class Reviewer:
    def __init__(
        self,
        config: Config,
        store: Store,
        console: Console | None = None,
        ask: Callable[[str], str] | None = None,
        edit: Callable[[str], str | None] | None = None,
        open_url: Callable[[str], object] = webbrowser.open_new_tab,
    ):
        self.config = config
        self.store = store
        self.console = console or Console()
        self.ask = ask or (lambda prompt: typer.prompt(prompt, default="", show_default=False))
        self.edit = edit or (lambda text: click.edit(text))
        self.open_url = open_url

    def run(self, run_id: str, items: list[ShortlistItem]) -> ReviewStats:
        done = self.store.acted_post_ids()
        pending = [i for i in items if i.post.id not in done]
        stats = ReviewStats()
        if not pending:
            self.console.print("Nothing left to review in this shortlist.")
            return stats
        for n, item in enumerate(pending, start=1):
            self.store.log_event(run_id, item, "shown")
            self.show(item, n, len(pending))
            outcome = self.decide(run_id, item)
            if outcome == "quit":
                stats.remaining = len(pending) - n + 1
                self.console.print(
                    f"Stopped. {stats.remaining} item(s) left; run `sga review` to continue."
                )
                break
            setattr(stats, outcome, getattr(stats, outcome) + 1)
        return stats

    def show(self, item: ShortlistItem, n: int, total: int) -> None:
        post, s = item.post, item.scores
        header = (
            f"[{n}/{total}]  @{post.author_handle} ({post.author_name}) · "
            f"{post.author_followers} followers · {_ago(post.created_at)}"
        )
        body = Text(post.text + "\n\n", style="bold")
        body.append(f"{post.url}\n", style="link " + post.url)
        body.append(
            f"Why: {item.why}\nScores: relevance {s.relevance:.0f} · opportunity "
            f"{s.opportunity:.0f} · pitch risk {s.pitch_risk:.0f}",
            style="dim",
        )
        self.console.print(Panel(body, title=header, title_align="left"))
        if not item.drafts:
            self.console.print("[yellow]No drafts. Write your own (w) or skip (s).[/yellow]")
        for i, draft in enumerate(item.drafts, start=1):
            length = x_length(draft.text)
            warn = f"  [yellow]⚠ {', '.join(draft.warnings)}[/yellow]" if draft.warnings else ""
            self.console.print(
                f"[cyan]Draft {i}[/cyan] [dim]({length}/{self.config.drafting.max_chars}) "
                f"{draft.angle}[/dim]{warn}"
            )
            self.console.print(f"  {draft.text}\n")

    def _prompt_text(self, item: ShortlistItem) -> str:
        n = len(item.drafts)
        choices = []
        if n:
            nums = range(1, n + 1)
            choices += [
                f"[{'/'.join(str(i) for i in nums)}] approve draft",
                f"[{'/'.join(f'e{i}' for i in nums)}] edit draft",
            ]
        choices += ["[w] write your own", "[s] skip", "[q] quit"]
        return " · ".join(choices)

    def decide(self, run_id: str, item: ShortlistItem) -> str:
        while True:
            choice = self.ask(self._prompt_text(item)).strip().lower()
            if choice == "s":
                self.store.log_event(run_id, item, "skipped")
                return "skipped"
            if choice == "q":
                return "quit"
            if choice.isdigit() and 1 <= int(choice) <= len(item.drafts):
                index = int(choice) - 1
                text = item.drafts[index].text
                self.store.log_event(run_id, item, "approved", index, final_text=text)
                self._send_to_browser(item, text)
                return "approved"
            if choice == "w" or (
                choice.startswith("e")
                and choice[1:].isdigit()
                and 1 <= int(choice[1:]) <= len(item.drafts)
            ):
                index = None if choice == "w" else int(choice[1:]) - 1
                start = "" if index is None else item.drafts[index].text
                text = self._edit_and_confirm(item, start)
                if text is None:
                    continue  # back to the menu
                self.store.log_event(run_id, item, "edited", index, final_text=text)
                self._send_to_browser(item, text)
                return "edited"
            self.console.print("[red]Not a valid choice.[/red]")

    def _edit_and_confirm(self, item: ShortlistItem, start: str) -> str | None:
        edited = self.edit(start)
        text = (edited if edited is not None else start).strip()
        if not text:
            self.console.print("Empty text, back to the menu.")
            return None
        p = self.config.profile
        problems = check_draft(
            text, self.config.drafting.max_chars, True, p.project_name, p.project_url
        )
        self.console.print(Panel(text, title=f"Your reply ({x_length(text)} chars)"))
        if problems:
            self.console.print(f"[yellow]⚠ {', '.join(problems)}[/yellow]")
        answer = self.ask("Open X's reply box with this text? [y/N]").strip().lower()
        return text if answer == "y" else None

    def _send_to_browser(self, item: ShortlistItem, text: str) -> None:
        mode = self.config.review.reply_mode
        self.open_url(reply_url(item, text, mode))
        if mode == "open_post":
            self.console.print(Panel(text, title="Copy this, paste it as your reply"))
        self.console.print(
            "[green]Opened in your browser. Read it there and click Reply yourself.[/green]\n"
        )
