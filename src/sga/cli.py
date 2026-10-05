"""Command-line entry point: `sga --help`."""

from __future__ import annotations

import shutil
import webbrowser
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .config import Config, load_config
from .filters import apply_filters
from .ingest import CaptureServer
from .store import Store

app = typer.Typer(
    help="Find relevant X posts you browsed and draft replies. Never posts on its own.",
    no_args_is_help=True,
)
console = Console()

ConfigOption = typer.Option(Path("config.yaml"), "--config", "-c", help="Path to config.yaml")


def _open(config_path: Path) -> tuple[Config, Store]:
    try:
        config = load_config(config_path)
    except FileNotFoundError as err:
        console.print(f"[red]{err}[/red]")
        raise typer.Exit(1) from err
    store = Store(config.storage.db_path)
    store.purge(config.storage.cache_ttl_hours)
    return config, store


@app.command()
def init(config_path: Path = ConfigOption):
    """Create config.yaml and .env from the examples (never overwrites)."""
    for src, dst in (("config.example.yaml", config_path), (".env.example", Path(".env"))):
        if Path(dst).exists():
            console.print(f"{dst} already exists, leaving it alone.")
        else:
            shutil.copy(src, dst)
            console.print(f"Created {dst}. Edit it before your first run.")


def collect_posts(config: Config, store: Store, open_pages: bool, save_raw: bool) -> int:
    """Run the capture server while the user browses. Returns how many new posts arrived."""
    raw_dir = config.storage.data_dir / "raw" if save_raw else None
    try:
        server = CaptureServer(store, config.sources, config.server.port, raw_dir)
    except OSError as err:
        console.print(
            f"[red]Can't listen on 127.0.0.1:{config.server.port} ({err}). "
            "Is another `sga collect` already running?[/red]"
        )
        raise typer.Exit(1) from err
    server.start()
    urls = config.sources.page_urls()
    console.print(f"[green]Capture server listening on 127.0.0.1:{server.port}[/green]")
    if not urls:
        console.print("[yellow]No keywords or list_urls in config.yaml; nothing to open.[/yellow]")
    elif open_pages:
        console.print(f"Opening {len(urls)} page(s) in your browser:")
        for url in urls:
            console.print(f"  {url}")
            webbrowser.open_new_tab(url)
    else:
        console.print("Open these pages yourself:")
        for url in urls:
            console.print(f"  {url}")
    console.print(
        "\n[bold]YOUR TURN:[/bold] in each tab, scroll for ~30 seconds so X loads recent posts.\n"
        "The extension badge shows how many posts are cached. Press Enter here when done."
    )
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        server.stop()
    console.print(f"Captured {server.accepted} new post(s) ({server.received} seen).")
    if raw_dir:
        console.print(
            f"[yellow]Raw payloads saved in {raw_dir}. They contain other people's posts: "
            "delete them once you've shared what's needed.[/yellow]"
        )
    return server.accepted


@app.command()
def collect(
    config_path: Path = ConfigOption,
    open_pages: bool = typer.Option(True, "--open/--no-open", help="Open source pages for you"),
    save_raw: bool = typer.Option(False, help="Debug: save raw payloads to data/raw/"),
):
    """Start capture, open your search/List pages, and wait while you scroll them."""
    config, store = _open(config_path)
    collect_posts(config, store, open_pages, save_raw)


@app.command()
def candidates(config_path: Path = ConfigOption, limit: int = 20):
    """Show cached posts that pass your filters (no LLM calls)."""
    config, store = _open(config_path)
    kept, dropped = apply_filters(
        store.candidates(),
        config.filters,
        config.sources,
        own_handle=config.profile.handle,
        exclude_ids=store.acted_post_ids(),
    )
    table = Table(title=f"{len(kept)} post(s) pass filters")
    for col in ("Author", "Followers", "Posted (UTC)", "Sources", "Text"):
        table.add_column(col, overflow="fold")
    for post in kept[:limit]:
        table.add_row(
            f"@{post.author_handle}",
            str(post.author_followers),
            post.created_at.strftime("%m-%d %H:%M"),
            ", ".join(post.sources),
            post.text[:140],
        )
    console.print(table)
    if dropped:
        console.print("Filtered out: " + ", ".join(f"{k}: {v}" for k, v in dropped.items()))
