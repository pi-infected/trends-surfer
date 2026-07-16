"""Modern Google Trends endpoints, called via in-page ``fetch``.

Why in-page fetch instead of pytrends' ``requests`` calls: pytrends is
archived (April 2025) and its HTTP requests carry Python's TLS fingerprint,
which Google rate-limits/blocks. By running ``fetch()`` from a page already
on ``trends.google.com`` (same origin) inside the stealth Chrome, every
request inherits the real browser's JA3 fingerprint *and* the session
cookies (NID, consent) for free.

All ``/trends/api/*`` JSON responses are prefixed with ``)]}'`` to defeat
JSON hijacking; we strip that before parsing.

This module is deliberately isolated: Google's internal endpoints are
undocumented and change, so when something breaks, it breaks here.
"""
from __future__ import annotations

import asyncio
import json
import random
import re
from urllib.parse import quote, urlencode

EXPLORE_URL = "https://trends.google.com/trends/api/explore"
WIDGET_BASE = "https://trends.google.com/trends/api/widgetdata"
TRENDING_RSS_URL = "https://trends.google.com/trending/rss"

_WIDGET_ENDPOINT = {
    "TIMESERIES": "multiline",
    "GEO_MAP": "comparedgeo",
    "RELATED_QUERIES": "relatedsearches",
    "RELATED_TOPICS": "relatedsearches",
}


class TrendsError(RuntimeError):
    pass


def _parse_trends_json(text: str):
    """Strip the anti-hijack prefix line and parse the JSON body."""
    body = text.lstrip()
    if body[:4] == ")]}'":
        nl = body.find("\n")
        body = body[nl + 1:] if nl != -1 else body[4:]
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        snippet = body[:200].replace("\n", " ")
        raise TrendsError(
            f"could not parse Trends response (likely a block/redirect page): {snippet!r}"
        ) from e


def _suffix_index(widget_id: str) -> int:
    m = re.search(r"_(\d+)$", widget_id)
    return int(m.group(1)) if m else 0


# Number of attempts + backoff schedule for throttled widget calls. Google
# Trends 429s aggressively on bursts of /trends/api/* requests keyed on IP,
# and the throttle window is typically ~30-60s — far longer than a few
# seconds. We therefore back off on a long exponential schedule (honoring any
# Retry-After the server sends) instead of giving up after a handful of
# seconds, since a 429 here is almost always transient on a residential IP.
_FETCH_RETRIES = 5
_BACKOFF_BASE_S = 8.0      # first wait ~8-14s
_BACKOFF_FACTOR = 1.8      # then ~14-25s, ~26-45s, ~46-80s
_BACKOFF_MAX_S = 90.0

# In-page GET that also surfaces the Retry-After header so we can honor it.
_FETCH_JS = """async (u) => {
    const r = await fetch(u, {
        credentials: 'include',
        headers: { 'Accept': 'application/json, text/plain, */*' },
    });
    const t = await r.text();
    return { status: r.status, body: t, retryAfter: r.headers.get('retry-after') };
}"""


def _backoff_delay(attempt: int, retry_after: str | None) -> float:
    """Seconds to wait before the next attempt (1-indexed).

    Honors a numeric ``Retry-After`` header when present; otherwise falls back
    to a jittered exponential schedule capped at ``_BACKOFF_MAX_S``.
    """
    if retry_after:
        try:
            return min(float(retry_after) + random.uniform(0.5, 2.0), _BACKOFF_MAX_S)
        except (TypeError, ValueError):
            pass
    base = _BACKOFF_BASE_S * (_BACKOFF_FACTOR ** (attempt - 1))
    return min(base + random.uniform(0.0, base * 0.4), _BACKOFF_MAX_S)


async def _fetch(page, url: str, *, retries: int = _FETCH_RETRIES) -> dict:
    """Run a same-origin GET from inside the page and parse the JSON.

    Google Trends rate-limits hard with HTTP 429 (and occasionally 503),
    largely keyed on IP reputation. We retry with a long exponential backoff +
    jitter (honoring Retry-After) before giving up — on a residential IP a 429
    is usually transient but can take up to a minute to clear.
    """
    last_status = None
    last_snippet = ""
    for attempt in range(1, retries + 1):
        res = await page.evaluate(_FETCH_JS, url)
        status = res.get("status")
        if status == 200:
            return _parse_trends_json(res["body"])
        last_status = status
        last_snippet = (res.get("body") or "")[:160].replace("\n", " ")
        if status in (429, 503) and attempt < retries:
            await asyncio.sleep(_backoff_delay(attempt, res.get("retryAfter")))
            continue
        break
    raise TrendsError(f"HTTP {last_status} from {url.split('?')[0]} — {last_snippet!r}")


async def _fetch_text(page, url: str, *, retries: int = _FETCH_RETRIES) -> str:
    """Same as :func:`_fetch` but returns the raw body (for non-JSON, e.g. RSS)."""
    last_status = None
    last_snippet = ""
    for attempt in range(1, retries + 1):
        res = await page.evaluate(
            """async (u) => {
                const r = await fetch(u, { credentials: 'include' });
                const t = await r.text();
                return { status: r.status, body: t, retryAfter: r.headers.get('retry-after') };
            }""",
            url,
        )
        status = res.get("status")
        if status == 200:
            return res["body"]
        last_status = status
        last_snippet = (res.get("body") or "")[:160].replace("\n", " ")
        if status in (429, 503) and attempt < retries:
            await asyncio.sleep(_backoff_delay(attempt, res.get("retryAfter")))
            continue
        break
    raise TrendsError(f"HTTP {last_status} from {url.split('?')[0]} — {last_snippet!r}")


def _unescape(s: str) -> str:
    import html
    s = s.strip()
    if s.startswith("<![CDATA[") and s.endswith("]]>"):
        s = s[9:-3]
    return html.unescape(s.strip())


def _explore_url(keywords, timeframe, geo, category, gprop, hl, tz) -> str:
    req = {
        "comparisonItem": [
            {"keyword": kw, "geo": geo, "time": timeframe} for kw in keywords
        ],
        "category": int(category),
        "property": gprop,
    }
    qs = urlencode({
        "hl": hl,
        "tz": str(tz),
        "req": json.dumps(req, separators=(",", ":")),
    })
    return f"{EXPLORE_URL}?{qs}"


def _widget_url(endpoint, request_obj, token, hl, tz) -> str:
    qs = urlencode({
        "hl": hl,
        "tz": str(tz),
        "req": json.dumps(request_obj, separators=(",", ":")),
        "token": token,
    })
    return f"{WIDGET_BASE}/{endpoint}?{qs}"


# ── parsers ──────────────────────────────────────────────────────────────────

def _parse_multiline(data, keywords) -> dict:
    timeline = data.get("default", {}).get("timelineData", []) or []
    points = []
    for entry in timeline:
        vals = entry.get("value", []) or []
        row = {
            "time": entry.get("time"),
            "date": entry.get("formattedTime") or entry.get("formattedAxisTime"),
            "is_partial": bool(entry.get("isPartial", False)),
        }
        for i, kw in enumerate(keywords):
            row[kw] = vals[i] if i < len(vals) else None
        points.append(row)
    return {"keywords": keywords, "points": points}


def _parse_geo(data, keywords) -> dict:
    rows = []
    for g in data.get("default", {}).get("geoMapData", []) or []:
        vals = g.get("value", []) or []
        row = {"geoName": g.get("geoName"), "geoCode": g.get("geoCode"),
               "hasData": g.get("hasData")}
        for i, kw in enumerate(keywords):
            row[kw] = vals[i] if i < len(vals) else None
        rows.append(row)
    return {"keywords": keywords, "regions": rows}


def _parse_related(data) -> dict:
    out = {"top": [], "rising": []}
    ranked = data.get("default", {}).get("rankedList", []) or []
    for idx, lst in enumerate(ranked):
        bucket = "top" if idx == 0 else "rising"
        for item in lst.get("rankedKeyword", []) or []:
            entry = {
                "value": item.get("value"),
                "formattedValue": item.get("formattedValue"),
                "link": item.get("link"),
            }
            if "query" in item:
                entry["query"] = item.get("query")
            topic = item.get("topic")
            if isinstance(topic, dict):
                entry["topic"] = topic.get("title")
                entry["topic_type"] = topic.get("type")
            out[bucket].append(entry)
    return out


# ── orchestration ────────────────────────────────────────────────────────────

async def prepare_session(page, keywords, geo) -> dict:
    """Warm cookies + same-origin context on a NEUTRAL Trends page.

    Do NOT land on ``/trends/explore?q=<keywords>``: that page's own JS fires
    the very widget XHRs we are about to request (multiline, comparedgeo,
    relatedsearches). Google's budget for ``/trends/api/widgetdata/*`` is only
    a handful of calls per session-window — measured 2026-07-16, the page's own
    4th widget call already came back 429. So the UI burned the budget and our
    identical calls were then refused: the plugin was rate-limiting itself, and
    it looked exactly like an IP-level block.

    The widget endpoints only need same-origin cookies, not an explore referer,
    so the bare ``/trends/`` home is enough — and it fires no api calls at all.

    ``keywords``/``geo`` are kept in the signature: they no longer shape the
    landing URL, but callers pass them and a future consent/geo cookie step may
    want them again.

    Returns the protection status from :mod:`consent`.
    """
    from .consent import pass_protections

    await page.goto(
        "https://trends.google.com/trends/",
        wait_until="domcontentloaded",
        timeout=45000,
    )
    status = await pass_protections(page)
    # Let any deferred XHRs / cookie set complete.
    try:
        await page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    return status


async def fetch_all(
    page,
    keywords: list[str],
    timeframe: str = "today 12-m",
    geo: str = "",
    category: int = 0,
    gprop: str = "",
    *,
    include_region: bool = True,
    include_related: bool = True,
    include_trending: bool = False,
    region_resolution: str = "COUNTRY",
    hl: str = "en-US",
    tz: int = -120,
) -> dict:
    """Run the full explore→widgets flow and return organized sections."""
    sections: dict = {}

    explore = await _fetch(page, _explore_url(keywords, timeframe, geo, category, gprop, hl, tz))
    widgets = explore.get("widgets", []) or []
    if not widgets:
        raise TrendsError("explore returned no widgets (keywords may have no data)")

    async def _jitter():
        # Space the per-widget requests out: Google 429s bursts of
        # /trends/api/* calls, and the related-searches widgets (which come
        # last) were the first to get throttled when fired ~1s apart.
        await asyncio.sleep(random.uniform(2.5, 5.0))

    # 1) Interest over time (always).
    ts_widget = next((w for w in widgets if w.get("id", "").startswith("TIMESERIES")), None)
    if ts_widget:
        await _jitter()
        d = await _fetch(page, _widget_url("multiline", ts_widget["request"],
                                           ts_widget["token"], hl, tz))
        sections["interest_over_time"] = _parse_multiline(d, keywords)

    # 2) Interest by region.
    if include_region:
        geo_widget = next((w for w in widgets if w.get("id", "").startswith("GEO_MAP")), None)
        if geo_widget:
            req = dict(geo_widget["request"])
            if region_resolution:
                req["resolution"] = region_resolution.upper()
            req.setdefault("requestOptions", {})
            await _jitter()
            try:
                d = await _fetch(page, _widget_url("comparedgeo", req,
                                                   geo_widget["token"], hl, tz))
                sections["interest_by_region"] = _parse_geo(d, keywords)
            except TrendsError as e:
                sections["interest_by_region"] = {"error": str(e)}

    # 3) Related queries + topics (one widget per keyword).
    if include_related:
        rq = {}
        rt = {}
        for w in widgets:
            wid = w.get("id", "")
            if wid.startswith("RELATED_QUERIES"):
                kw = keywords[min(_suffix_index(wid), len(keywords) - 1)]
                await _jitter()
                try:
                    d = await _fetch(page, _widget_url("relatedsearches", w["request"],
                                                       w["token"], hl, tz))
                    rq[kw] = _parse_related(d)
                except TrendsError as e:
                    rq[kw] = {"error": str(e)}
            elif wid.startswith("RELATED_TOPICS"):
                kw = keywords[min(_suffix_index(wid), len(keywords) - 1)]
                await _jitter()
                try:
                    d = await _fetch(page, _widget_url("relatedsearches", w["request"],
                                                       w["token"], hl, tz))
                    rt[kw] = _parse_related(d)
                except TrendsError as e:
                    rt[kw] = {"error": str(e)}
        if rq:
            sections["related_queries"] = rq
        if rt:
            sections["related_topics"] = rt

    # 4) Trending now (geo-based, keyword-independent).
    #    The old /api/dailytrends JSON endpoint now 404s; the current public
    #    feed is the Trending RSS at /trending/rss?geo=XX.
    if include_trending:
        tgeo = (geo or "US").split("-")[0]  # RSS wants a country, not a sub-region
        try:
            await _jitter()
            xml = await _fetch_text(page, f"{TRENDING_RSS_URL}?geo={quote(tgeo)}")
            sections["trending_now"] = {"geo": tgeo, "items": _parse_trending_rss(xml)}
        except TrendsError as e:
            sections["trending_now"] = {"geo": tgeo, "error": str(e)}

    return sections


def _parse_trending_rss(xml: str) -> list[dict]:
    items = []
    for m in re.finditer(r"<item>(.*?)</item>", xml, re.S):
        block = m.group(1)
        title = re.search(r"<title>(.*?)</title>", block, re.S)
        traffic = re.search(r"<ht:approx_traffic>(.*?)</ht:approx_traffic>", block, re.S)
        news = re.findall(r"<ht:news_item_title>(.*?)</ht:news_item_title>", block, re.S)
        items.append({
            "title": _unescape(title.group(1)) if title else None,
            "traffic": _unescape(traffic.group(1)) if traffic else None,
            "articles": [_unescape(n) for n in news[:2]],
        })
    return items
