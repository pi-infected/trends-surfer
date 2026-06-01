"""FastMCP server for trends_surfer.

Exposes four tools:

  - ``trends_fetch``   the only network-touching tool; subject to the
                       non-bypassable rate limit. Pulls everything, writes a
                       temp file, returns a compact index.
  - ``trends_query``   read one slice of a saved result (no network, no wait).
  - ``trends_list``    list recent saved results so prior data can be reused.
  - ``trends_health``  browser/Xvfb availability + rate-limit countdown.

Claude does the natural-language → parameters mapping itself; the tools only
expose clean structured arguments.
"""
from __future__ import annotations

import os
import time

from mcp.server.fastmcp import FastMCP

from . import store
from .browser import chrome_available, ensure_xvfb, open_session
from .playbook import opportunity_playbook
from .ratelimit import RateLimiter
from .trends import TrendsError, fetch_all, prepare_session

_DATA_DIR = os.environ.get("TTT_DATA_DIR") or os.path.join(
    os.path.expanduser("~"), ".trends_surfer"
)
_MIN_DELAY = float(os.environ.get("TTT_MIN_DELAY", "30"))
_MAX_DELAY = float(os.environ.get("TTT_MAX_DELAY", "90"))
_PROFILE_DIR = os.path.join(_DATA_DIR, "chrome-profile")

mcp = FastMCP("trends_surfer")
_limiter = RateLimiter(
    state_path=os.path.join(_DATA_DIR, ".ratelimit.json"),
    min_delay=_MIN_DELAY,
    max_delay=_MAX_DELAY,
)


@mcp.tool()
async def trends_fetch(
    keywords: list[str],
    timeframe: str = "today 12-m",
    geo: str = "",
    category: int = 0,
    gprop: str = "",
    include_region: bool = True,
    include_related: bool = True,
    include_trending: bool = False,
    region_resolution: str = "COUNTRY",
    hl: str = "en-US",
    tz: int = -120,
) -> dict:
    """Fetch ALL Google Trends data for one or more keywords, save it to a temp
    file, and return only a compact index (NOT the full series).

    Use this once per question, then call `trends_query` to read the specific
    slice you need — this keeps large time series out of the context window.

    A randomized minimum delay (default 30-90s) is enforced between fetches
    inside the server and cannot be skipped; the call simply blocks until the
    gap has elapsed. Reuse a recent result via `trends_list`/`trends_query`
    instead of re-fetching when you can.

    Args:
        keywords: 1-5 search terms (compared against each other).
        timeframe: e.g. "today 12-m", "today 3-m", "now 7-d", "2023-01-01 2023-12-31".
        geo: ISO country/region code (e.g. "US", "FR", "US-CA"). "" = worldwide.
        category: Google Trends category id (0 = all categories).
        gprop: "" (web), "images", "news", "youtube", or "froogle".
        include_region: also pull interest-by-region.
        include_related: also pull related queries + topics.
        include_trending: also pull trending-now for the geo (keyword-independent).
        region_resolution: "COUNTRY", "REGION", or "CITY" for interest-by-region.
        hl: interface/output language (e.g. "fr", "es", "de", "ja", "en-US").
            For keyword research in another language, set the keywords in that
            language, `geo` to the country, and `hl` to match — related-topic
            titles and labels then come back localized. Related *queries* are
            already returned in the local language regardless.
        tz: timezone offset in minutes (e.g. -120 = UTC+2 Paris, 300 = UTC-5
            US-East) used for time bucketing.

    Returns:
        {file, md_file, protections, index} — `file` is the full JSON result to
        query; `index` is the compact summary.
    """
    keywords = [k.strip() for k in keywords if k and k.strip()]
    if not keywords:
        return {"error": "provide at least one keyword"}
    if len(keywords) > 5:
        return {"error": "Google Trends compares at most 5 keywords at once"}

    try:
        async with _limiter:
            async with open_session(_PROFILE_DIR) as page:
                protections = await prepare_session(page, keywords, geo)
                sections = await fetch_all(
                    page, keywords,
                    timeframe=timeframe, geo=geo, category=category, gprop=gprop,
                    include_region=include_region,
                    include_related=include_related,
                    include_trending=include_trending,
                    region_resolution=region_resolution,
                    hl=hl, tz=tz,
                )
    except TrendsError as e:
        return {"error": f"Trends fetch failed: {e}",
                "hint": "Google may have blocked the session or the keyword has no data. "
                        "Try again later (the rate-limit gap also applies to retries)."}
    except Exception as e:  # noqa: BLE001
        return {"error": f"unexpected error: {type(e).__name__}: {e}"}

    meta = {
        "keywords": keywords,
        "timeframe": timeframe,
        "geo": geo,
        "category": category,
        "gprop": gprop,
        "hl": hl,
        "tz": tz,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    json_path, md_path = store.write_result(_DATA_DIR, meta, sections)
    return {
        "file": json_path,
        "md_file": md_path,
        "protections": protections,
        "index": store.build_index(meta, sections),
    }


@mcp.tool()
async def trends_query(
    file: str,
    section: str,
    keyword: str = "",
    top: int = 0,
) -> dict:
    """Read ONE slice of a saved `trends_fetch` result (no network, no delay).

    Args:
        file: the `file` path returned by `trends_fetch`.
        section: "interest_over_time" | "interest_by_region" | "related_queries"
                 | "related_topics" | "trending_now".
        keyword: restrict to one keyword (optional).
        top: cap the number of rows returned (0 = all). For interest_over_time,
             `top` returns the most recent N points.
    """
    return store.query(
        file, section,
        keyword=keyword or None,
        top=top or None,
    )


@mcp.tool()
async def trends_list(limit: int = 20) -> dict:
    """List recent saved Trends results (so you can reuse data instead of re-fetching)."""
    return {"results": store.list_results(_DATA_DIR, limit=limit)}


@mcp.tool()
async def trends_health() -> dict:
    """Report browser/Xvfb availability and the current rate-limit countdown."""
    return {
        "data_dir": _DATA_DIR,
        "chrome_available": chrome_available(),
        "xvfb_headful": ensure_xvfb(),
        "rate_limit": _limiter.status(),
    }


@mcp.prompt(title="Find & exploit trend opportunities")
def find_opportunities(domain: str = "") -> str:
    """Generic, reusable methodology for discovering trend-driven opportunities
    and deciding how to turn each into a website/business — using the
    trends_surfer tools + web research.

    Domain-agnostic (works for any vertical) and monetization-agnostic (presents
    the full menu of revenue models and how to choose, not one prescribed model).
    Pass `domain` to scope the run to a specific vertical, or leave blank.
    """
    return opportunity_playbook(domain)


def main() -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    mcp.run()


if __name__ == "__main__":
    main()
