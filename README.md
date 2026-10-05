# Social Growth Assistant

A daily 10-minute helper for finding X conversations about RAG, LLM evals and Web3/DAO
tooling, and drafting thoughtful replies. **It prepares; you decide and click.**

- It **never posts, replies, likes or follows**. Approving a draft opens X's reply box in
  your own browser with the text filled in; you read it and click Reply.
- It **makes no requests to X**. A small browser extension reads posts that X already loaded
  on search and List pages *you* opened, and passes them to this tool on `127.0.0.1`.
  No bot login, no polling, no scraping traffic.
- It **keeps other people's data briefly**: captured posts and shortlists are deleted after
  72 hours (configurable). What's kept long-term is your own activity: which post URLs you
  approved, edited or skipped, and the text you sent.

👉 **Setup and the parts only you can do: [docs/YOUR_STEPS.md](docs/YOUR_STEPS.md)**

## Daily use

```bash
sga daily
```
1. Your keyword searches and X Lists open in browser tabs. Scroll each for ~30 s and press Enter.
2. You see yesterday's summary, then today's ranked shortlist (default 7) with 2 drafts each.
3. For each post: `1`/`2` approve a draft, `e1`/`e2` edit it, `w` write your own, `s` skip,
   `q` stop and resume later with `sga review`.

Other commands: `sga collect` (capture only), `sga candidates` (what passed filters, no AI),
`sga shortlist` (rank + draft), `sga review`, `sga summary --days 7`, `sga init`.

## How it works

```
your browser (x.com search / List tabs you opened)
   │  extension copies the timeline JSON X already sent you
   ▼
127.0.0.1:8765  capture server ──► SQLite cache (72h TTL)
                                       │
            filters: age · follower range · replies · language · dedupe · already reviewed
                                       │
            Claude: relevance / reply-opportunity / pitch-risk scores  ──► ranked shortlist
                                       │
            Claude: 2 drafts per post ──► rule checks (length, no hashtag stuffing,
                                          no generic openers, no salesy CTAs, project
                                          only when relevant and never first) ──► 1 retry
                                       │
            `sga review` ──► you approve one item ──► browser opens X reply box ──► you click Reply
```

| Module | Responsibility |
|---|---|
| `extension/` | Chrome MV3 extension; forwards search/List timeline responses to localhost only |
| `sga/ingest.py` | Local capture server (localhost, extension origins, JSON only) |
| `sga/parser.py` | Extract the minimum post fields from X's GraphQL JSON |
| `sga/filters.py` | Age, followers, replies, language, own/excluded handles, dedupe |
| `sga/llm.py` | Model calls via the `claude` CLI (default) or the Anthropic API |
| `sga/ranking.py` | LLM scoring, combined score, thresholds, one post per author |
| `sga/drafting.py` | Draft generation, X-weighted length and rule checks, retry |
| `sga/review.py` | Interactive per-item review and reply-intent links |
| `sga/summary.py` | Daily summary from run/activity logs |
| `sga/store.py` | SQLite cache (TTL) and activity log |

## Configuration

Everything lives in `config.yaml` (created by `sga init` from
[config.example.yaml](config.example.yaml)).

**Claude access:** by default the tool runs the `claude` command (Claude Code) in
non-interactive mode, so it uses the Claude subscription you're logged in with. No API
key is needed. Each call runs with all tools and MCP servers disabled: it only reads the
prompt and returns JSON. To pay per token instead, set `llm.backend: api` and put
`ANTHROPIC_API_KEY` in `.env`.

Key settings: `sources.keywords`, `sources.list_urls`, `filters.max_age_hours`,
`filters.min_followers` / `max_followers`, `ranking.shortlist_size`, `ranking.model` /
`drafting.model`, `review.reply_mode`.

**Usage:** X costs nothing. A run makes about 6 ranking calls (60 posts in batches of 10)
plus about 7 drafting calls (3 at a time), which count toward your Claude plan's usage
limits. A 5-post test run took under 20 seconds. To use less, lower
`ranking.max_to_rank`, or set `ranking.model: claude-haiku-4-5` with
`ranking.effort: null`.

## Scheduling

Capturing needs you in the loop on purpose, so a scheduler can only *remind* you. Set
`sga daily` as a calendar reminder once or twice a day, or add a desktop notification:

```bash
# crontab -e   (weekdays 09:00 and 17:00)
# Linux:
0 9,17 * * 1-5  DISPLAY=:0 notify-send "Social Growth Assistant" "Time for: sga daily"
# macOS:
0 9,17 * * 1-5  osascript -e 'display notification "Time for: sga daily" with title "SGA"'
```
On Windows, use Task Scheduler with action `powershell -Command "sga daily"` (with the venv
activated) so a terminal opens at the scheduled time.

## Development

```bash
pip install -e ".[dev]"
pytest          # filtering, dedupe, ranking, drafting rules, review flow, capture server
ruff check src tests
```
Tests use recorded-shape X payloads and a fake model client; no network needed.

## Limits worth knowing

- The extension relies on X's internal web-app JSON. When X changes it, capture may stop;
  `sga collect --save-raw` saves a sample so the parser can be updated (see YOUR_STEPS).
- Reading data through the extension is still outside X's terms on paper, even though it
  only sees what you browse and adds no traffic. Keep the tool to your own reading.
- The tool can't see replies already posted under a post, so check the thread before sending.
