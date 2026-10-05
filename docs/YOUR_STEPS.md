# Your steps (the parts only you can do)

The assistant prepares; you browse, decide and click. Every step below needs your
browser, your X account or your machine, which the code can't (and shouldn't) touch.
Tick them off once. After that, the daily routine is the short list at the bottom.

## One-time setup (about 20 minutes)

### 1. Install (terminal, ~3 min)
Python 3.10+ is required.
```bash
git clone <this repo> && cd Social-growth-assistant
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .
sga init                                                 # creates config.yaml and .env
```

### 2. Anthropic API key (~2 min)
Create a key at https://console.anthropic.com → API keys, then put it in `.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
```
`.env` is git-ignored. Never paste the key anywhere else.

### 3. Tell it who you are (`config.yaml` → `profile`, ~5 min)
- `handle`: your X handle (so your own posts are never suggested)
- `project_name`, `project_url`: mentioned only when directly relevant
- `offer`: 2–3 sentences on what you do
- `voice_examples`: paste 2–3 posts/replies you've written. This is what makes drafts
  sound like you instead of like a bot. **Highest-leverage step.**

### 4. Choose sources (in X + `config.yaml` → `sources`, ~5 min)
- **Keywords:** edit `sources.keywords`. Each becomes a "Latest" search tab.
- **Monitored accounts:** in X, create a **private List** (Lists → New List → Private),
  add the builders/protocols/DAOs you follow, then paste the List URL
  (`https://x.com/i/lists/<id>`) into `sources.list_urls`. Also put their handles in
  `sources.monitored_accounts` so suggestions say "monitored account @…".

### 5. Load the browser extension (Chrome, Brave, Edge or Arc, ~2 min)
1. Open `chrome://extensions` and switch on **Developer mode** (top right).
2. Click **Load unpacked** and select this repo's `extension/` folder.
3. Pin it (puzzle icon → pin) so you can see its badge.

What it does: on x.com search and List pages only, it copies the timeline data X already
sent to your browser and passes it to `127.0.0.1:8765` (your machine). It makes no requests
to X, can't read DMs or your home timeline, and can't post, like or follow.

### 6. First capture test (~3 min)
```bash
sga collect
```
Your search/List tabs open. Scroll each one for ~30 s. The badge should count up.
Press Enter in the terminal, then:
```bash
sga candidates
```
- **Badge says `off`:** `sga collect` isn't running, or port 8765 is taken.
- **Badge never appears or stays at 0:** X may have changed its web app. Run
  `sga collect --save-raw`, scroll one tab, press Enter, and send me **one** file from
  `data/raw/` (it holds public posts only; delete the folder afterwards). I'll update the
  parser against it.

### 7. Check the reply link once (~1 min, after Phase 4 exists)
On your first `sga review`, approve one item and confirm the X tab opens as **a reply to
that post** with the draft filled in. If it opens a blank or non-reply composer, set
`review.reply_mode: open_post` in `config.yaml` and tell me.

## Daily routine (~10 minutes, once or twice a day)
```bash
sga daily
```
1. Tabs open; scroll each ~30 s; press Enter.
2. Wait about a minute while it filters, ranks and drafts.
3. For each item: pick a draft, edit it, or skip. Approving opens X's reply box; **you** read
   it and click Reply. Nothing is ever sent without that click.

## Optional: reminders
A scheduler can only remind you, because capture needs you browsing. See "Scheduling" in
the [README](../README.md) for cron/Task Scheduler lines, or just set a calendar reminder.

## When to come back to me (Claude)
- Capture stops working (badge at 0): send one `data/raw/` file, as in step 6.
- Rankings feel off (wrong posts on top): tell me 2–3 examples of good and bad picks; I'll tune
  the scoring prompt and weights.
- Drafts don't sound like you: add more `voice_examples` first, then tell me what's off.
