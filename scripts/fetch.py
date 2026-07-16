"""Reusable CLI over the trends_surfer fetcher (for research, outside MCP).

    uv run python scripts/fetch.py --keywords "kw1,kw2" --timeframe "now 7-d" \
        --geo US --trending --no-region

Writes the full result + index into TTT_DATA_DIR (defaults to
``research/trends-data`` under the project) and prints the compact index.
Respects the persistent rate limit so manual research stays polite.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from trends_surfer import store  # noqa: E402
from trends_surfer.browser import open_session  # noqa: E402
from trends_surfer.ratelimit import RateLimiter  # noqa: E402
from trends_surfer.trends import fetch_all, prepare_session  # noqa: E402


async def main(a: argparse.Namespace) -> None:
    default_dir = os.path.join(os.path.dirname(__file__), "..", "research", "trends-data")
    data_dir = os.path.abspath(os.environ.get("TTT_DATA_DIR") or default_dir)
    os.makedirs(data_dir, exist_ok=True)
    profile = os.path.join(data_dir, "chrome-profile")
    limiter = RateLimiter(
        os.path.join(data_dir, ".ratelimit.json"),
        float(os.environ.get("TTT_MIN_DELAY", "30")),
        float(os.environ.get("TTT_MAX_DELAY", "90")),
    )
    kws = [k.strip() for k in a.keywords.split(",") if k.strip()]

    async with limiter:
        async with open_session(profile) as page:
            prot = await prepare_session(page, kws, a.geo)
            secs = await fetch_all(
                page, kws,
                timeframe=a.timeframe, geo=a.geo, gprop=a.gprop,
                include_region=not a.no_region,
                include_related=not a.no_related,
                include_trending=a.trending,
                trending_hours=a.trending_hours,
            )

    meta = {
        "keywords": kws, "timeframe": a.timeframe, "geo": a.geo,
        "category": 0, "gprop": a.gprop,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    jp, mp = store.write_result(data_dir, meta, secs)
    print(json.dumps(
        {"file": jp, "protections": prot, "index": store.build_index(meta, secs)},
        ensure_ascii=False, indent=2,
    ))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--keywords", required=True, help="comma-separated, 1-5 terms")
    ap.add_argument("--timeframe", default="today 12-m")
    ap.add_argument("--geo", default="")
    ap.add_argument("--gprop", default="")
    ap.add_argument("--trending", action="store_true")
    ap.add_argument("--trending-hours", type=int, default=24,
                    help="trending window: 24, 48 or 168 (past 7 days)")
    ap.add_argument("--no-region", action="store_true")
    ap.add_argument("--no-related", action="store_true")
    asyncio.run(main(ap.parse_args()))
