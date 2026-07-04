"""Stealth Chrome session.

Strategy (most-furtive first), trimmed to what Trends needs:

  1. **Patchright** — patches at the launch-args + CDP-handshake level. The
     real Google Chrome binary (``channel="chrome"``) is preferred over
     Chromium because Chromium's TLS/JA3 fingerprint is detectable
     independently of any JS patch.
  2. **playwright-stealth** on stock Playwright — fallback.
  3. A 20-point manual init script injected on top of either, via a direct
     CDP command (Patchright's ``add_init_script`` wrapper has a DNS-poison
     regression; the underlying CDP call is unaffected).

We run **headful under Xvfb** because headless Chrome reliably fails
Cloudflare Turnstile. On Linux that means faking a display with Xvfb; on
Windows/macOS a real desktop session already provides one, so headful Chrome
runs natively there with no virtual-display step at all. A **persistent
user-data-dir** keeps cookies (NID, consent) warm across calls so we rarely
re-hit consent/Turnstile.

The session is exposed as ``open_session(profile_dir)`` — an async context
manager yielding a ready Playwright ``Page``.
"""
from __future__ import annotations

import asyncio
import os
import random
import shutil
import subprocess
import sys
import time
from contextlib import asynccontextmanager

_IS_WINDOWS = sys.platform.startswith("win")
_XVFB_DISPLAY = ":99"
_xvfb_ready: bool | None = None

_DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

_VIEWPORT_POOL = (
    (1280, 800), (1366, 768), (1440, 900),
    (1536, 864), (1600, 900), (1920, 1080),
)

# 20-point belt-and-braces stealth, injected before any page script runs.
_STEALTH_INIT_SCRIPT = r"""
(() => {
  try { Object.defineProperty(navigator, 'webdriver', { get: () => undefined }); } catch (e) {}
  try {
    const fakePlugins = [
      { name: 'PDF Viewer', filename: 'internal-pdf-viewer' },
      { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer' },
      { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer' },
    ];
    Object.defineProperty(navigator, 'plugins', { get: () => fakePlugins });
    Object.defineProperty(navigator, 'mimeTypes', { get: () => [{ type: 'application/pdf' }] });
  } catch (e) {}
  try {
    if (!window.chrome) { window.chrome = {}; }
    if (!window.chrome.runtime) { window.chrome.runtime = {}; }
  } catch (e) {}
  try {
    const origQuery = navigator.permissions && navigator.permissions.query;
    if (origQuery) {
      navigator.permissions.query = (param) => {
        if (param && (param.name === 'notifications' || param.name === 'clipboard-read' || param.name === 'clipboard-write')) {
          return Promise.resolve({ state: 'prompt' });
        }
        return origQuery.call(navigator.permissions, param);
      };
    }
  } catch (e) {}
  try { Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] }); } catch (e) {}
  try {
    const getParam = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function (param) {
      if (param === 37445) return 'Intel Inc.';
      if (param === 37446) return 'Intel Iris OpenGL Engine';
      return getParam.call(this, param);
    };
    if (window.WebGL2RenderingContext) {
      const getParam2 = WebGL2RenderingContext.prototype.getParameter;
      WebGL2RenderingContext.prototype.getParameter = function (param) {
        if (param === 37445) return 'Intel Inc.';
        if (param === 37446) return 'Intel Iris OpenGL Engine';
        return getParam2.call(this, param);
      };
    }
  } catch (e) {}
  try { Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 }); } catch (e) {}
  try { Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 }); } catch (e) {}
  try {
    document.addEventListener('DOMContentLoaded', () => {
      document.querySelectorAll('iframe').forEach((f) => {
        try { if (f.contentWindow && !f.contentWindow.chrome) { f.contentWindow.chrome = window.chrome; } } catch (_) {}
      });
    });
  } catch (e) {}
  try {
    if (navigator.userAgentData === undefined) {
      const brands = [
        { brand: 'Chromium', version: '148' },
        { brand: 'Google Chrome', version: '148' },
        { brand: 'Not_A Brand', version: '99' },
      ];
      const uaData = {
        brands, mobile: false, platform: 'Linux',
        getHighEntropyValues: (hints) => Promise.resolve({
          brands, mobile: false, platform: 'Linux', platformVersion: '6.0.0',
          architecture: 'x86', bitness: '64', model: '', uaFullVersion: '148.0.7778.167',
          fullVersionList: [
            { brand: 'Chromium', version: '148.0.7778.167' },
            { brand: 'Google Chrome', version: '148.0.7778.167' },
            { brand: 'Not_A Brand', version: '99.0.0.0' },
          ], wow64: false,
        }),
        toJSON: () => ({ brands, mobile: false, platform: 'Linux' }),
      };
      Object.defineProperty(navigator, 'userAgentData', { get: () => uaData });
    }
  } catch (e) {}
  try {
    if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
      const orig = navigator.mediaDevices.enumerateDevices.bind(navigator.mediaDevices);
      navigator.mediaDevices.enumerateDevices = async () => {
        try { const real = await orig(); if (real && real.length > 0) return real; } catch (_) {}
        return [
          { deviceId: 'default', kind: 'audioinput', label: '', groupId: 'g1' },
          { deviceId: 'default', kind: 'audiooutput', label: '', groupId: 'g1' },
        ];
      };
    }
  } catch (e) {}
  try {
    if (navigator.getBattery === undefined) {
      navigator.getBattery = async () => ({
        charging: true, chargingTime: 0, dischargingTime: Infinity, level: 0.87,
        addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
        onchargingchange: null, onchargingtimechange: null, ondischargingtimechange: null, onlevelchange: null,
      });
    }
  } catch (e) {}
  try {
    if (typeof Notification !== 'undefined' && Notification.permission === 'denied') {
      Object.defineProperty(Notification, 'permission', { get: () => 'default' });
    }
  } catch (e) {}
  try {
    Object.defineProperty(screen, 'availTop', { get: () => 27 });
    Object.defineProperty(screen, 'availLeft', { get: () => 0 });
  } catch (e) {}
  try {
    if (navigator.connection === undefined) {
      Object.defineProperty(navigator, 'connection', {
        get: () => ({ effectiveType: '4g', rtt: 100, downlink: 10, saveData: false, type: 'wifi',
          onchange: null, addEventListener: () => {}, removeEventListener: () => {} }),
      });
    }
  } catch (e) {}
  try {
    Object.defineProperty(document, 'hidden', { get: () => false });
    Object.defineProperty(document, 'visibilityState', { get: () => 'visible' });
    document.hasFocus = () => true;
  } catch (e) {}
  try {
    if (window.chrome) {
      if (typeof window.chrome.csi !== 'function') {
        window.chrome.csi = () => ({ onloadT: Date.now(), pageT: Math.random() * 1000, startE: Date.now() - 5000, tran: 15 });
      }
      if (typeof window.chrome.loadTimes !== 'function') {
        window.chrome.loadTimes = () => ({
          commitLoadTime: Date.now() / 1000 - 2, connectionInfo: 'h2',
          finishDocumentLoadTime: Date.now() / 1000 - 1, finishLoadTime: Date.now() / 1000 - 0.5,
          firstPaintAfterLoadTime: 0, firstPaintTime: Date.now() / 1000 - 1.8, navigationType: 'Other',
          npnNegotiatedProtocol: 'h2', requestTime: Date.now() / 1000 - 3, startLoadTime: Date.now() / 1000 - 3,
          wasAlternateProtocolAvailable: false, wasFetchedViaSpdy: true, wasNpnNegotiated: true,
        });
      }
    }
  } catch (e) {}
  try {
    if (performance && performance.memory === undefined) {
      Object.defineProperty(performance, 'memory', {
        get: () => ({ jsHeapSizeLimit: 4294705152, totalJSHeapSize: 35000000, usedJSHeapSize: 25000000 }),
      });
    }
  } catch (e) {}
  try {
    const realOuterH = window.outerHeight, realInnerH = window.innerHeight;
    if (realOuterH === realInnerH || Math.abs(realOuterH - realInnerH) < 20) {
      Object.defineProperty(window, 'outerHeight', { get: () => realInnerH + 87 });
    }
    const realOuterW = window.outerWidth, realInnerW = window.innerWidth;
    if (realOuterW === realInnerW) { Object.defineProperty(window, 'outerWidth', { get: () => realInnerW }); }
  } catch (e) {}
})();
"""


def _probe_display(display: str) -> bool:
    if not shutil.which("xdpyinfo"):
        return True  # can't probe; assume a set DISPLAY works
    return subprocess.run(
        ["xdpyinfo", "-display", display],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0


def ensure_xvfb() -> bool:
    """Make a usable X display exist so Chrome can run headful.

    Returns True when headful is safe, False when the caller must fall back to
    headless (which Cloudflare Turnstile reliably fails). Idempotent + cached.

    On Windows/macOS a real desktop session already provides a display, so
    there's nothing to fake here — always headful, no Xvfb involved.
    """
    if _IS_WINDOWS:
        return True

    global _xvfb_ready
    if _xvfb_ready is not None:
        return _xvfb_ready

    # By default we FORCE a dedicated virtual display so the browser never
    # pops a visible window on the user's real desktop (DISPLAY=:0). Set
    # TTT_FORCE_XVFB=0 to allow reusing an existing display instead.
    force = (os.environ.get("TTT_FORCE_XVFB", "1") or "").strip().lower() in (
        "1", "true", "yes",
    )
    existing = (os.environ.get("DISPLAY") or "").strip()
    if existing and not force and _probe_display(existing):
        _xvfb_ready = True
        return True
    # Already running on our forced virtual display from a previous call.
    if force and existing == _XVFB_DISPLAY and _probe_display(_XVFB_DISPLAY):
        _xvfb_ready = True
        return True

    if not shutil.which("Xvfb"):
        _xvfb_ready = False
        return False
    try:
        subprocess.Popen(
            ["Xvfb", _XVFB_DISPLAY, "-screen", "0", "1920x1080x24",
             "-ac", "-nolisten", "tcp"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(20):
            time.sleep(0.25)
            if _probe_display(_XVFB_DISPLAY):
                os.environ["DISPLAY"] = _XVFB_DISPLAY
                _xvfb_ready = True
                return True
    except Exception:
        pass
    _xvfb_ready = False
    return False


def chrome_available() -> bool:
    """True when the real Google Chrome binary is reachable.

    Checks the system install paths AND whether ``patchright install chrome``
    has placed a chrome build in the Playwright browsers cache.
    """
    if _IS_WINDOWS:
        win_paths = (
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        )
        if any(os.path.exists(p) for p in win_paths):
            return True
        cache = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or os.path.expandvars(
            r"%LOCALAPPDATA%\ms-playwright"
        )
        try:
            return any(name.startswith("chrome") for name in os.listdir(cache))
        except Exception:
            return False

    sys_paths = (
        "/opt/google/chrome/chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/google-chrome-beta",
    )
    if any(os.path.exists(p) for p in sys_paths):
        return True
    # Patchright/Playwright cache (e.g. ~/.cache/ms-playwright/chrome-*/...).
    cache = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or os.path.expanduser(
        "~/.cache/ms-playwright"
    )
    try:
        return any(name.startswith("chrome") for name in os.listdir(cache))
    except Exception:
        return False


def _common_args(headful: bool) -> list[str]:
    args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--no-default-browser-check",
        "--no-first-run",
        "--disable-features=IsolateOrigins,site-per-process,Translate,"
        "DnsOverHttps,SecureDnsTransactions,EncryptedClientHello",
        "--dns-over-https-mode=off",
        "--disable-extensions",
        "--disable-component-update",
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
    ]
    if headful:
        args.append("--start-maximized")
    return args


@asynccontextmanager
async def open_session(profile_dir: str):
    """Yield a stealthy Playwright ``Page`` backed by a persistent profile.

    The page has the manual stealth init script installed (so it applies to
    every navigation), runs headful under Xvfb when possible, and reuses the
    cookies stored in ``profile_dir`` across calls.
    """
    headful = await asyncio.to_thread(ensure_xvfb)

    # --- pick the stealth lib (Patchright > playwright-stealth > manual) ---
    pw_module = None
    stealth_kind = "manual"
    try:
        from patchright.async_api import async_playwright as _patchright_pw
        pw_module = _patchright_pw
        stealth_kind = "patchright"
    except Exception:
        pass

    stealth_ctx_manager = None
    if pw_module is None:
        from playwright.async_api import async_playwright as _stock_pw
        try:
            from playwright_stealth import Stealth
            stealth_ctx_manager = Stealth().use_async(_stock_pw())
            stealth_kind = "playwright-stealth"
        except Exception:
            stealth_ctx_manager = _stock_pw()
            stealth_kind = "manual"

    ctx_manager = pw_module() if pw_module is not None else stealth_ctx_manager
    pw = await ctx_manager.__aenter__()

    use_chrome = chrome_available() and stealth_kind == "patchright"
    headless = not headful

    os.makedirs(profile_dir, exist_ok=True)
    vw, vh = random.choice(_VIEWPORT_POOL)

    launch_kwargs: dict = {
        "user_data_dir": profile_dir,
        "headless": headless,
        "args": _common_args(headful),
        "locale": "en-US",
        "timezone_id": "Europe/Paris",
        "ignore_https_errors": True,
    }
    if headful:
        # Real OS window — explicit viewport re-enables emulation, which makes
        # outerW/H == innerW/H again (the headless tell Turnstile rejects).
        launch_kwargs["viewport"] = None
    else:
        launch_kwargs["viewport"] = {"width": vw, "height": vh}
        launch_kwargs["user_agent"] = _DEFAULT_UA.replace("HeadlessChrome", "Chrome")
        launch_kwargs["extra_http_headers"] = {"Accept-Language": "en-US,en;q=0.9"}

    context = None
    try:
        if use_chrome:
            try:
                context = await pw.chromium.launch_persistent_context(
                    channel="chrome", **launch_kwargs
                )
            except Exception:
                context = None
        if context is None:
            context = await pw.chromium.launch_persistent_context(**launch_kwargs)

        # Non-patchright: the standard init-script API is safe.
        if stealth_kind != "patchright":
            try:
                await context.add_init_script(_STEALTH_INIT_SCRIPT)
            except Exception:
                pass

        page = context.pages[0] if context.pages else await context.new_page()

        # Patchright: inject via the raw CDP command (its add_init_script
        # wrapper poisons DNS on 1.59.x; the CDP call underneath is fine).
        if stealth_kind == "patchright":
            try:
                cdp = await context.new_cdp_session(page)
                await cdp.send(
                    "Page.addScriptToEvaluateOnNewDocument",
                    {"source": _STEALTH_INIT_SCRIPT},
                )
            except Exception:
                pass

        page._ttt_stealth_kind = stealth_kind  # type: ignore[attr-defined]
        page._ttt_headful = headful  # type: ignore[attr-defined]
        try:
            yield page
        finally:
            try:
                await context.close()
            except Exception:
                pass
    finally:
        try:
            await ctx_manager.__aexit__(None, None, None)
        except Exception:
            pass
