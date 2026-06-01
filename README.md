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
- `Xvfb` on the host (headful Chrome beats Turnstile; without it Chrome runs
  headless and Turnstile is much more likely to fail)
- The real Chrome binary:

```bash
cd trends-surfer
uv sync                      # installs deps into .venv (Python pinned to 3.12)
uv run patchright install chrome    # or: uv run playwright install chromium
# Debian/Ubuntu: sudo apt-get install -y xvfb
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
to reuse an existing `DISPLAY`).

### Notes on Google's moving target

Google's old `/api/dailytrends` JSON endpoint now returns 404, so trending-now
is pulled from the current `/trending/rss?geo=XX` feed instead. Google also
rate-limits the widget calls with HTTP 429 (heavily on datacenter IPs); the
fetcher retries with an exponential backoff that honors `Retry-After`, and on a
residential IP this is usually transient. The Google-facing logic is isolated in
`trends.py` for easy re-adaptation when endpoints shift again.
