"""Get past Google's consent wall + a Cloudflare Turnstile, if present.

The Turnstile click-through is ported from Lea/auto-ninja-linking captcha.py
(``try_click_turnstile`` and its humanisation helpers), trimmed to the
click-only path — no paid solver. ``pass_protections`` is the single entry
point the session calls after each navigation.
"""
from __future__ import annotations

import asyncio
import random
import re
import time

_IFRAME_SEL = (
    'iframe[src*="challenges.cloudflare.com/turnstile"], '
    'iframe[src*="challenges.cloudflare.com/cdn-cgi/challenge-platform"]'
)
_CONTAINER_SEL = '.cf-turnstile, div[data-sitekey][class*="turnstile"]'

_CONSENT_LABELS = re.compile(
    r"(accept all|tout accepter|i agree|j.accepte|accept the use|"
    r"alle akzeptieren|aceptar todo|accetta tutto)",
    re.I,
)


async def handle_consent(page) -> bool:
    """Click through Google's consent dialog if one is showing.

    Handles both the dedicated ``consent.google.com`` interstitial and the
    in-page cookie banner. Best-effort; returns True if it clicked something.
    """
    try:
        clicked = False
        for _ in range(2):
            btn = page.get_by_role("button", name=_CONSENT_LABELS)
            try:
                if await btn.count() > 0:
                    await btn.first.click(timeout=4000)
                    clicked = True
                    await asyncio.sleep(random.uniform(0.8, 1.6))
                    try:
                        await page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception:
                        pass
                    break
            except Exception:
                pass
            # Some consent forms use a plain <form> submit button without a role.
            try:
                form_btn = page.locator(
                    'form[action*="consent"] button, button[aria-label*="Accept"]'
                ).first
                if await form_btn.count() > 0:
                    await form_btn.click(timeout=4000)
                    clicked = True
                    await asyncio.sleep(random.uniform(0.8, 1.6))
                    break
            except Exception:
                pass
            break
        return clicked
    except Exception:
        return False


# ── Turnstile click-through (ported, click-only) ────────────────────────────

async def _humanise_pre_click(page) -> None:
    """Small delay + one natural scroll + curved mouse drift before clicking.

    Cloudflare scores page-level signals accumulated *before* the click; a
    sub-second goto→click is a guaranteed bot tell no fingerprint can mask.
    """
    try:
        await asyncio.sleep(random.uniform(1.2, 2.4))
        await page.evaluate(
            "window.scrollBy({ top: arguments[0], behavior: 'smooth' })",
            random.randint(160, 380),
        )
        await asyncio.sleep(random.uniform(0.4, 1.0))
        try:
            vp = page.viewport_size or {"width": 1280, "height": 720}
            vw, vh = vp["width"], vp["height"]
        except Exception:
            vw, vh = 1280, 720
        x0, y0 = random.uniform(60, vw * 0.4), random.uniform(80, vh * 0.4)
        await page.mouse.move(x0, y0)
        for _ in range(3):
            xt = random.uniform(40, vw * 0.85)
            yt = random.uniform(60, vh * 0.75)
            await page.mouse.move(xt, yt, steps=random.randint(8, 18))
            await asyncio.sleep(random.uniform(0.05, 0.20))
    except Exception:
        pass


async def _humanise_click_at(page, x: float, y: float) -> None:
    """Move to (x, y) along a curved path + click — CF counts pre-click moves."""
    cx, cy = x + 200, y + 100
    waypoints = []
    for i in range(random.randint(2, 3)):
        t = (i + 1) / 4
        wx = cx + (x - cx) * t + random.uniform(-30, 30)
        wy = cy + (y - cy) * t + random.uniform(-30, 30)
        waypoints.append((wx, wy))
    waypoints.append((x + random.uniform(-3, 3), y + random.uniform(-3, 3)))
    for wx, wy in waypoints:
        await page.mouse.move(wx, wy, steps=random.randint(6, 14))
        await asyncio.sleep(random.uniform(0.04, 0.12))
    await asyncio.sleep(random.uniform(0.15, 0.45))
    await page.mouse.click(x, y, delay=random.uniform(35, 95))


async def _pick_turnstile_iframe(page):
    """Return (locator, box) of the largest clickable Turnstile iframe, or (None, None)."""
    try:
        n = await page.locator(_IFRAME_SEL).count()
    except Exception:
        return None, None
    best, best_box, best_area = None, None, 0.0
    for i in range(n):
        loc = page.locator(_IFRAME_SEL).nth(i)
        try:
            box = await loc.bounding_box()
        except Exception:
            box = None
        if not box or box["width"] < 50 or box["height"] < 20:
            continue
        area = box["width"] * box["height"]
        if area > best_area:
            best, best_box, best_area = loc, box, area
    return best, best_box


async def detect_turnstile(page) -> bool:
    try:
        return await page.evaluate(
            """() => !!(document.querySelector('.cf-turnstile[data-sitekey], div[data-sitekey][class*="turnstile"]')
                || document.querySelector('iframe[src*="challenges.cloudflare.com/turnstile"]'))"""
        )
    except Exception:
        return False


async def try_click_turnstile(page, timeout_seconds: float = 20.0) -> str | None:
    """Click the Turnstile widget like a human; return the token or None."""
    started = time.monotonic()
    await _humanise_pre_click(page)
    try:
        cont = page.locator(_CONTAINER_SEL).first
        if await cont.count() > 0:
            await cont.scroll_into_view_if_needed(timeout=3000)
    except Exception:
        pass

    iframe_el = box = None
    deadline = time.monotonic() + timeout_seconds * 0.5
    while time.monotonic() < deadline:
        iframe_el, box = await _pick_turnstile_iframe(page)
        if iframe_el is not None:
            break
        await asyncio.sleep(0.3)
    if iframe_el is None or not box:
        return None

    try:
        await iframe_el.scroll_into_view_if_needed(timeout=3000)
        await asyncio.sleep(0.3)
        box = await iframe_el.bounding_box() or box
    except Exception:
        pass

    cx = box["x"] + 24 + random.uniform(-4, 6)
    cy = box["y"] + box["height"] / 2 + random.uniform(-4, 4)
    try:
        await _humanise_click_at(page, cx, cy)
    except Exception:
        return None

    poll_deadline = time.monotonic() + max(timeout_seconds - 4, 6)
    fail_frame = page.frame_locator(_IFRAME_SEL).first
    while time.monotonic() < poll_deadline:
        try:
            token = await page.evaluate("""() => {
                const el = document.querySelector('input[name="cf-turnstile-response"]');
                if (el && el.value) return el.value;
                try {
                  if (window.turnstile && typeof window.turnstile.getResponse === 'function') {
                    const t = window.turnstile.getResponse();
                    if (t) return t;
                  }
                } catch (e) {}
                return null;
            }""")
            if token:
                return token
        except Exception:
            pass
        try:
            if await fail_frame.get_by_text("Verification failed", exact=False).count():
                return None
        except Exception:
            pass
        await asyncio.sleep(0.4)
    return None


async def pass_protections(page) -> dict:
    """Run consent + Turnstile handling after a navigation. Returns a status dict."""
    status = {"consent_clicked": False, "turnstile": "none"}
    status["consent_clicked"] = await handle_consent(page)
    if await detect_turnstile(page):
        token = await try_click_turnstile(page)
        status["turnstile"] = "solved" if token else "failed"
        # Give the page a beat to settle after the challenge resolves.
        await asyncio.sleep(random.uniform(0.6, 1.4))
    return status
