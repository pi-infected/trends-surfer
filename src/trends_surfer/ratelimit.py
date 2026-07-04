"""Non-bypassable minimum delay between Google Trends requests.

Design goals (from the spec):

  - A *minimum* randomized delay is enforced between two network-touching
    requests. The value is drawn fresh per call from ``[min, max]`` so the
    spacing is never pixel-identical (a polling pattern is itself a tell).
  - Claude **cannot** bypass it: there is no tool parameter that skips the
    wait, the wait happens *inside* the server process while the tool call
    blocks, and the state survives restarts (a timestamp on disk). Even
    two concurrent tool calls are serialized.

The limiter is an async context manager. Hold it for the *whole* network
operation:

    async with limiter:
        ... do the fetch ...
    # on exit the "last request" timestamp is stamped to now

so the gap is measured from the completion of the previous request to the
start of the next — strictly safer than measuring start-to-start.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import time
from pathlib import Path


class RateLimiter:
    def __init__(
        self,
        state_path: str | os.PathLike[str],
        min_delay: float,
        max_delay: float,
    ) -> None:
        self._state_path = Path(state_path)
        self._min = max(0.0, float(min_delay))
        self._max = max(self._min, float(max_delay))
        # Serializes concurrent tool calls within this process. Combined with
        # the on-disk timestamp, no second request can race past the gap.
        self._lock = asyncio.Lock()
        self._last_waited = 0.0  # seconds slept on the most recent acquire

    # ── persistent timestamp ────────────────────────────────────────────
    def _read_last_ts(self) -> float:
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            return float(data.get("last_request_ts", 0.0))
        except Exception:
            return 0.0

    def _write_last_ts(self, ts: float) -> None:
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"last_request_ts": ts}), encoding="utf-8")
            tmp.replace(self._state_path)  # atomic on POSIX
        except Exception:
            # Failing to persist must not crash a fetch; worst case the next
            # process start under-counts elapsed time and waits a bit longer.
            pass

    # ── introspection for trends_health ─────────────────────────────────
    def status(self) -> dict:
        last = self._read_last_ts()
        now = time.time()
        elapsed = max(0.0, now - last) if last else None
        guaranteed = max(0.0, self._min - elapsed) if elapsed is not None else 0.0
        worst_case = max(0.0, self._max - elapsed) if elapsed is not None else 0.0
        return {
            "min_delay_s": self._min,
            "max_delay_s": self._max,
            "last_request_age_s": round(elapsed, 1) if elapsed is not None else None,
            "ready_after_at_least_s": round(guaranteed, 1),
            "ready_after_at_most_s": round(worst_case, 1),
            "last_waited_s": round(self._last_waited, 1),
        }

    # ── the gate ─────────────────────────────────────────────────────────
    async def __aenter__(self) -> "RateLimiter":
        # Acquire the in-process lock FIRST so a second concurrent call can't
        # read a stale timestamp before the first one finishes and stamps it.
        await self._lock.acquire()
        target = random.uniform(self._min, self._max)
        last = self._read_last_ts()
        elapsed = (time.time() - last) if last else float("inf")
        wait = target - elapsed
        self._last_waited = max(0.0, wait)
        if wait > 0:
            await asyncio.sleep(wait)
        return self

    async def __aexit__(self, *exc) -> None:
        try:
            # Stamp completion time — the next request's gap is measured from
            # here. Stamp even on failure: a failed request still hit Google.
            self._write_last_ts(time.time())
        finally:
            self._lock.release()
