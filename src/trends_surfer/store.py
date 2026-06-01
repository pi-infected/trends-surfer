"""Persist a full Trends result to a temp file + expose compact slices.

The whole point of this layer (per the spec): ``trends_fetch`` pulls *all*
the data, writes it here, and returns to Claude only a tiny index. Claude
then reads exactly the slice it needs via ``trends_query`` instead of loading
megabytes of time series into its context.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

_VALID_SECTIONS = (
    "interest_over_time",
    "interest_by_region",
    "related_queries",
    "related_topics",
    "trending_now",
)


def _results_dir(data_dir: str) -> Path:
    d = Path(data_dir) / "results"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slug(keywords) -> str:
    raw = "-".join(keywords) if keywords else "trends"
    s = re.sub(r"[^a-zA-Z0-9]+", "-", raw).strip("-").lower()
    return (s or "trends")[:48]


# ── write ─────────────────────────────────────────────────────────────────────

def write_result(data_dir: str, meta: dict, sections: dict) -> tuple[str, str]:
    """Write ``<slug>-<ts>.json`` + a readable ``.md`` summary. Returns paths."""
    rdir = _results_dir(data_dir)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = f"{_slug(meta.get('keywords'))}-{stamp}"
    json_path = rdir / f"{base}.json"
    md_path = rdir / f"{base}.md"

    payload = {"meta": meta, "sections": sections}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    md_path.write_text(_render_markdown(meta, sections))
    return str(json_path), str(md_path)


# ── index (what gets returned to Claude) ───────────────────────────────────────

def build_index(meta: dict, sections: dict) -> dict:
    keywords = meta.get("keywords", [])
    idx: dict = {
        "keywords": keywords,
        "timeframe": meta.get("timeframe"),
        "geo": meta.get("geo") or "worldwide",
        "sections_present": sorted(sections.keys()),
    }

    iot = sections.get("interest_over_time")
    if iot and iot.get("points"):
        pts = iot["points"]
        summary = {}
        for kw in keywords:
            vals = [p[kw] for p in pts if isinstance(p.get(kw), (int, float))]
            if not vals:
                continue
            peak_pt = max(pts, key=lambda p: p.get(kw) if isinstance(p.get(kw), (int, float)) else -1)
            summary[kw] = {
                "avg": round(sum(vals) / len(vals), 1),
                "peak": peak_pt.get(kw),
                "peak_date": peak_pt.get("date"),
                "latest": pts[-1].get(kw),
            }
        idx["interest_over_time"] = {
            "n_points": len(pts),
            "from": pts[0].get("date"),
            "to": pts[-1].get("date"),
            "per_keyword": summary,
        }

    rq = sections.get("related_queries")
    if isinstance(rq, dict):
        idx["related_queries_top5"] = {
            kw: [e.get("query") for e in (v.get("top") or [])[:5]]
            for kw, v in rq.items() if isinstance(v, dict) and "top" in v
        }

    rt = sections.get("related_topics")
    if isinstance(rt, dict):
        idx["related_topics_top5"] = {
            kw: [e.get("topic") for e in (v.get("top") or [])[:5]]
            for kw, v in rt.items() if isinstance(v, dict) and "top" in v
        }

    reg = sections.get("interest_by_region")
    if isinstance(reg, dict) and reg.get("regions"):
        first_kw = keywords[0] if keywords else None
        ranked = sorted(
            reg["regions"],
            key=lambda r: r.get(first_kw) if isinstance(r.get(first_kw), (int, float)) else -1,
            reverse=True,
        )
        idx["interest_by_region_top5"] = [
            {"geo": r.get("geoName"), "value": r.get(first_kw)} for r in ranked[:5]
        ]

    tn = sections.get("trending_now")
    if isinstance(tn, dict) and tn.get("items"):
        idx["trending_now_top10"] = [i.get("title") for i in tn["items"][:10]]

    return idx


def _render_markdown(meta: dict, sections: dict) -> str:
    lines = [f"# Google Trends — {', '.join(meta.get('keywords', []))}", ""]
    lines.append(f"- timeframe: `{meta.get('timeframe')}`")
    lines.append(f"- geo: `{meta.get('geo') or 'worldwide'}`")
    lines.append(f"- fetched_at: {meta.get('fetched_at')}")
    lines.append(f"- sections: {', '.join(sorted(sections.keys()))}")
    lines.append("")
    idx = build_index(meta, sections)
    if "interest_over_time" in idx:
        lines.append("## Interest over time (summary)")
        for kw, s in idx["interest_over_time"].get("per_keyword", {}).items():
            lines.append(f"- **{kw}**: avg {s['avg']}, peak {s['peak']} ({s['peak_date']}), latest {s['latest']}")
        lines.append("")
    if "related_queries_top5" in idx:
        lines.append("## Top related queries")
        for kw, qs in idx["related_queries_top5"].items():
            lines.append(f"- **{kw}**: {', '.join(q for q in qs if q)}")
        lines.append("")
    if "trending_now_top10" in idx:
        lines.append("## Trending now")
        lines.append(", ".join(t for t in idx["trending_now_top10"] if t))
        lines.append("")
    lines.append("_Full data in the sibling .json — query slices via `trends_query`._")
    return "\n".join(lines)


# ── query (read a slice without dumping everything) ────────────────────────────

def query(file: str, section: str, keyword: str | None = None, top: int | None = None,
          fields: list[str] | None = None) -> dict:
    if section not in _VALID_SECTIONS:
        return {"error": f"unknown section {section!r}; valid: {', '.join(_VALID_SECTIONS)}"}
    p = Path(file)
    if not p.exists():
        return {"error": f"file not found: {file}"}
    payload = json.loads(p.read_text())
    sections = payload.get("sections", {})
    data = sections.get(section)
    if data is None:
        return {"error": f"section {section!r} not present in this result",
                "available": sorted(sections.keys())}

    # interest_over_time → optionally trim points + project keyword columns
    if section == "interest_over_time":
        pts = data.get("points", [])
        if top:
            pts = pts[-int(top):]
        if keyword:
            pts = [{"date": p.get("date"), "time": p.get("time"), keyword: p.get(keyword)} for p in pts]
        return {"keywords": data.get("keywords"), "points": pts, "n": len(pts)}

    if section == "interest_by_region":
        regions = data.get("regions", [])
        kw = keyword or (data.get("keywords") or [None])[0]
        regions = sorted(
            regions,
            key=lambda r: r.get(kw) if isinstance(r.get(kw), (int, float)) else -1,
            reverse=True,
        )
        if top:
            regions = regions[:int(top)]
        return {"keywords": data.get("keywords"), "regions": regions, "n": len(regions)}

    if section in ("related_queries", "related_topics"):
        if keyword:
            sub = data.get(keyword)
            if sub is None:
                return {"error": f"keyword {keyword!r} not in {section}", "available": list(data.keys())}
            return _trim_related(sub, top)
        return {kw: _trim_related(v, top) for kw, v in data.items()}

    if section == "trending_now":
        items = data.get("items", [])
        if top:
            items = items[:int(top)]
        return {"geo": data.get("geo"), "items": items, "n": len(items)}

    return data


def _trim_related(sub: dict, top: int | None) -> dict:
    if "error" in sub:
        return sub
    out = {}
    for bucket in ("top", "rising"):
        lst = sub.get(bucket, [])
        out[bucket] = lst[:int(top)] if top else lst
    return out


def list_results(data_dir: str, limit: int = 20) -> list[dict]:
    rdir = _results_dir(data_dir)
    files = sorted(rdir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for p in files[:limit]:
        try:
            payload = json.loads(p.read_text())
            meta = payload.get("meta", {})
            out.append({
                "file": str(p),
                "keywords": meta.get("keywords"),
                "timeframe": meta.get("timeframe"),
                "geo": meta.get("geo") or "worldwide",
                "fetched_at": meta.get("fetched_at"),
                "sections": sorted(payload.get("sections", {}).keys()),
            })
        except Exception:
            continue
    return out
