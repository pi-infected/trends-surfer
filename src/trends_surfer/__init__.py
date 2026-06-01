"""trends_surfer — natural-language Google Trends via a stealth browser session.

The package is split so the volatile, Google-facing parts stay isolated:

  - ``ratelimit``  persistent, non-bypassable minimum delay between requests
  - ``browser``    stealth Chrome (Patchright + 20-point init script), ported
                   from the Lea/auto-ninja-linking project
  - ``consent``    Google consent dialog + Cloudflare Turnstile click-through
  - ``trends``     the modern Trends API endpoints, called via in-page fetch
  - ``store``      writes the full result to a temp file + builds a compact index
  - ``server``     the FastMCP server wiring the four tools together
"""

__version__ = "0.1.0"
