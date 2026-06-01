"""End-to-end smoke test, run outside the MCP harness.

    uv run python scripts/smoke.py [keyword]

Drives a real stealth-browser fetch, prints the index, writes the result
file, then reads one slice back via the store query path. Useful to confirm
the Google-facing endpoints + anti-detection still work before wiring the
plugin into Claude.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from trends_surfer import store  # noqa: E402
from trends_surfer.browser import chrome_available, ensure_xvfb, open_session  # noqa: E402
from trends_surfer.trends import fetch_all, prepare_session  # noqa: E402


async def run(keyword: str) -> None:
    data_dir = os.environ.get("TTT_DATA_DIR") or tempfile.mkdtemp(prefix="ttt-smoke-")
    profile = os.path.join(data_dir, "chrome-profile")
    print(f"data_dir={data_dir}")
    print(f"chrome_available={chrome_available()} xvfb_headful={ensure_xvfb()}")

    keywords = [keyword]
    async with open_session(profile) as page:
        print(f"stealth_kind={getattr(page, '_ttt_stealth_kind', '?')} "
              f"headful={getattr(page, '_ttt_headful', '?')}")
        protections = await prepare_session(page, keywords, "")
        print(f"protections={protections}")
        sections = await fetch_all(
            page, keywords, timeframe="today 3-m",
            include_region=True, include_related=True, include_trending=True,
        )

    meta = {"keywords": keywords, "timeframe": "today 3-m", "geo": "",
            "category": 0, "gprop": "", "fetched_at": "smoke"}
    json_path, md_path = store.write_result(data_dir, meta, sections)
    print("\n=== INDEX ===")
    print(json.dumps(store.build_index(meta, sections), indent=2, ensure_ascii=False))
    print(f"\nfile={json_path}\nmd={md_path}")

    print("\n=== trends_query(related_queries, top=5) ===")
    print(json.dumps(store.query(json_path, "related_queries", top=5),
                     indent=2, ensure_ascii=False)[:1500])


if __name__ == "__main__":
    kw = sys.argv[1] if len(sys.argv) > 1 else "bitcoin"
    asyncio.run(run(kw))
