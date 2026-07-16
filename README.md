<div align="center">

```
   ████████╗██████╗ ███████╗███╗   ██╗██████╗ ███████╗
   ╚══██╔══╝██╔══██╗██╔════╝████╗  ██║██╔══██╗██╔════╝
      ██║   ██████╔╝█████╗  ██╔██╗ ██║██║  ██║███████╗
      ██║   ██╔══██╗██╔══╝  ██║╚██╗██║██║  ██║╚════██║
      ██║   ██║  ██║███████╗██║ ╚████║██████╔╝███████║
      ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═══╝╚═════╝ ╚══════╝
   ███████╗██╗   ██╗██████╗ ███████╗███████╗██████╗
   ██╔════╝██║   ██║██╔══██╗██╔════╝██╔════╝██╔══██╗
   ███████╗██║   ██║██████╔╝█████╗  █████╗  ██████╔╝
   ╚════██║██║   ██║██╔══██╗██╔══╝  ██╔══╝  ██╔══██╗
   ███████║╚██████╔╝██║  ██║██║     ███████╗██║  ██║
   ╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝     ╚══════╝╚═╝  ╚═╝
```

**Natural-language Google Trends for Claude — through a stealth browser.**

</div>

---

**Trends Surfer** is a Claude Code plugin that lets Claude answer Google Trends
questions in plain language. Ask *"compare interest in bitcoin vs ethereum over
the last 3 months and show me the rising related queries"* — Claude maps that to
a `trends_fetch` call, the plugin pulls the data through a stealth Chrome
session, saves the full result to a temp file, and returns only a compact index.
Claude then reads the exact slice it needs with `trends_query`.

> The MCP server, package and tools keep the identifier `trends_surfer` /
> `trends_*`; **Trends Surfer** is just the friendly name.

## Why not pytrends directly

pytrends was archived in April 2025 and its `requests`-based calls carry
Python's TLS fingerprint, which Google rate-limits and blocks. Trends Surfer
re-implements the modern Trends endpoints and calls them via **in-page
`fetch()`** from a page already on `trends.google.com`, so every request
inherits a real Chrome's JA3 fingerprint and the live session cookies.

## How the protections work

- **Anti-detection**: Patchright + the real Google Chrome binary, headful under
  Xvfb, a 20-point stealth init script, and a humanised click-through for
  Cloudflare Turnstile (no paid solver). A persistent Chrome profile keeps
  cookies warm across calls.
- **Non-bypassable rate limit**: a randomized minimum delay (default **30–90s**)
  is enforced *inside the server* between `trends_fetch` calls. There is no
  parameter to skip it, the wait happens while the tool call blocks, and the
  timestamp is persisted to disk so it survives restarts. Claude cannot get
  around it.

## Tools

| Tool | Network? | Rate-limited? | Purpose |
|------|----------|---------------|---------|
| `trends_fetch` | yes | **yes** | Pull everything, write temp file, return compact index |
| `trends_query` | no | no | Read one slice of a saved result |
| `trends_list`  | no | no | List recent results to reuse instead of re-fetching |
| `trends_health`| no | no | Chrome/Xvfb availability + rate-limit countdown |

## Prompt (reusable methodology)

`find_opportunities` is an MCP **prompt** (not a tool) that injects a generic,
domain- and monetization-agnostic playbook telling the model how to use these
tools + web research to **discover trend opportunities and decide how to exploit
them** (the opportunity equation, the event-driven detection pattern, the SERP
beatability read, the full business-model menu, data-sourcing, and ranking by
difficulty × competition × financial potential). In Claude Code it appears as
`/mcp__trends_surfer__find_opportunities` and takes an optional `domain`
argument to scope the run. The text lives in `src/trends_surfer/playbook.py`.

## Requirements

- `uv` (the MCP server is launched via `uv run`)
- Headful Chrome beats Turnstile; without it Chrome runs headless and
  Turnstile is much more likely to fail. **Linux only:** since a Linux host
  usually has no display, this plugin fakes one with `Xvfb`. **Windows**
  already has a real desktop session, so headful Chrome runs natively there
  with no extra setup (`browser.py`'s `_IS_WINDOWS` guard). **macOS is not yet
  handled** — the code has no `_IS_MACOS` branch, so on a Mac it currently
  falls through to the Linux Xvfb/`chrome_available()` paths, which are wrong
  for that OS (no `Xvfb`, wrong Chrome path) and will likely fail Turnstile
  the same way unpatched Windows did.
- The real Chrome binary (checked at the standard per-OS install paths, e.g.
  `%ProgramFiles%\Google\Chrome\Application\chrome.exe` on Windows or
  `/usr/bin/google-chrome` on Linux) — or let `patchright install chrome`
  fetch its own build.

```bash
cd trends-surfer
uv sync                      # installs deps into .venv (Python pinned to 3.12)
uv run patchright install chrome    # or: uv run playwright install chromium
# Linux only: sudo apt-get install -y xvfb (Debian/Ubuntu)
```

## Smoke test

```bash
uv run python scripts/smoke.py bitcoin
```

Prints the index, writes the result file, and reads a `related_queries` slice
back. The first run downloads dependencies and may take a while.

## Install as a plugin

The plugin declares its MCP server in `.mcp.json` using
`${CLAUDE_PLUGIN_ROOT}`. Add this directory as a local plugin (e.g. via a local
marketplace pointing at the repo, or `claude plugin` install flow), then verify
the four `trends_*` tools appear and `trends_health` reports
`chrome_available: true`.

Configuration via `.mcp.json` env: `TTT_MIN_DELAY`, `TTT_MAX_DELAY`,
`TTT_DATA_DIR`, and `TTT_FORCE_XVFB` (default `1` — always run Chrome on a
private virtual display so no window ever appears on your desktop; set to `0`
to reuse an existing `DISPLAY`). `TTT_FORCE_XVFB` is a Linux-only knob — on
Windows it's ignored since headful Chrome runs on the real desktop directly
(a visible Chrome window will appear there).

## Windows Installation

If an AI agent is doing this setup, follow these steps in
order and verify each before moving on:

1. **Check for `uv`**: run `uv --version`. If missing, install with
   `python -m pip install --user uv`, then re-check.
2. **Install the browser binary** (this is the step that is easy to miss —
   it does *not* happen automatically when the MCP server starts):
   ```
   cd <copied-folder>
   uv run patchright install chrome
   ```
   If it reports Chrome is already installed on the system, that's fine —
   `chrome_available()` will find it at the standard install path either way.
3. **Register and install the plugin**:
   ```
   /plugin marketplace add <absolute-path-to-copied-folder>
   /plugin install trends_surfer@trends-surfer-local
   /reload-plugins
   ```
4. **Verify** by calling the `trends_health` tool. Expect
   `"chrome_available": true` and `"xvfb_headful": true`. If either is
   `false`, re-check steps 2-3 rather than assuming the code is broken —
   this exact code was already verified working on Windows elsewhere.
5. **Known gotcha on reinstall**: if the plugin is ever uninstalled and
   reinstalled in the same session, `/plugin install` can fail with
   `EPERM: operation not permitted, rm` on the plugin's cached `.venv`. This
   means a previous `trends-surfer-server`/`uv.exe`/`python.exe` process (from
   the old install) is still running and holding files open. Find and stop
   them first (e.g. via `Get-CimInstance Win32_Process` filtered on
   `trends-surfer-local` or `trends_surfer`, then `Stop-Process -Force`),
   *then* retry the install.

### Notes on Google's moving target

Google's old `/api/dailytrends` JSON endpoint now returns 404, so trending-now
comes from the `/trending` UI (volumes, growth, age) with the
`/trending/rss?geo=XX` feed as a fallback.

Google rate-limits `/trends/api/widgetdata/*` hard with HTTP 429 — and the
budget is only a handful of calls per session-window. **This bites hardest when
you land on a page that spends the budget for you**: `/trends/explore?q=…` fires
the same widget XHRs we're about to request, so the plugin used to 429 itself
before asking for anything (fixed — `prepare_session` now lands on the neutral
`/trends/` home). A 429 here means "these calls were already made", not "your IP
is blocked": if you're debugging one, count the widget calls the page made
before yours. The fetcher also retries with an exponential backoff honoring
`Retry-After`.

The Google-facing logic is isolated in `trends.py` for easy re-adaptation when
endpoints shift again.

### On search volume

`trending_now` items carry a `volume` int parsed from Google's own label
(`"5M+"` → `5000000`). Two caveats worth knowing before you build on it:

- It is a **bucket floor**, not a count — `5M+` means "at least 5M", and Google
  never publishes anything finer.
- It exists **only for trending terms**. Google publishes no absolute volume for
  an arbitrary keyword; `interest_over_time` is a 0-100 *relative* index, and no
  amount of scraping turns it into searches/month. For that you need a keyword
  tool (Keyword Planner, DataForSEO, …).

Category filtering is not supported: `/trending?category=` is silently ignored
by the page — the picker only applies through a UI click, so a category argument
here would quietly return everything.
