"""The reusable opportunity-finding methodology, surfaced as an MCP prompt.

This distills the repeatable process for using Google Trends (via this plugin)
+ the open web to (a) discover trend-driven opportunities and (b) decide how to
turn each into a business. It is deliberately **domain-agnostic** (works for any
vertical), **channel-agnostic** (a website is only one way to capture demand —
short-form video, paid ads, a community, a tool, or a sales funnel are equally
valid), and **monetization-agnostic** (presents the full menu of models and how
to choose, not one prescribed model).
"""
from __future__ import annotations


def opportunity_playbook(domain: str = "") -> str:
    scope = (
        f"Your target domain for this run is: **{domain}**.\n"
        if domain.strip()
        else "Pick (or ask the user for) a target domain/vertical to investigate. "
        "It can be anything — a product category, an industry, a platform, a "
        "hobby, a fast-moving space.\n"
    )
    return f"""# Playbook — find trend opportunities and decide how to exploit them

You are using the **trends_surfer** tools (`trends_fetch`, `trends_query`,
`trends_list`, `trends_health`) plus your own web search/browsing to find
opportunities where you can capture rising demand against weak, beatable
competition — and to work out how that opportunity would make money and how its
content/pages could be built from data.

{scope}
This process is domain-agnostic, **channel-agnostic**, and
monetization-agnostic. A website is only ONE way to capture an opportunity —
short-form video, a YouTube channel, paid ads, a community/newsletter, a free
tool, or a direct sales funnel can each be the right vehicle. Do **not** assume a
niche, a channel, or a revenue model up front — derive them from evidence.

## 0. The opportunity equation

An opportunity is attractive when ALL of these hold:
1. **Demand** — rising or recurring interest (a trend, a repeated need, or an
   event that keeps happening).
2. **A beatable position** — in the channel you'd use, the incumbents are weak.
   In *search*, page 1 is held only by forums, thin aggregators, biased vendor
   blogs, or nobody. In *social/video*, no quality creator owns the topic yet.
   In *paid*, acquisition cost is low relative to payout. The point is the same:
   you can realistically out-rank / out-create / out-convert what's there.
3. **A moat you can hold** — usually **freshness** (facts that change, so static
   competitors rot), **neutrality/depth** (a trustworthy resource biased
   incumbents can't credibly publish), or **speed/distribution** (you reach the
   audience first when the spike hits).
4. **A way to monetize** — at least one viable model with real economics (§4).

The earliest, most beatable window is usually **upstream of a big spike** —
caught while the topic is still only on forums/Reddit/small creators, before an
authority or a crowded field locks it in.

## 1. Discover demand (breadth)

- Choose 4–8 high-volume **head terms** for the domain (the brands, platforms,
  categories everyone searches). Run `trends_fetch` on them with
  `timeframe="today 12-m"` (or `"today 3-m"`), `include_related=True`. Short
  windows like `now 7-d` return sparse related queries — avoid for discovery.
- The gold is in **rising related queries**. Pull them with `trends_query(file,
  "related_queries")`. Classify each rising query by **intent**, e.g.:
  error/troubleshooting · how-to · "X vs Y" · pricing/cost · "is X down" ·
  alternatives · "what is X" · cancel/refund · invest/stock · "is X safe" ·
  access/waitlist · shutdown · jobs/salary · deals. Each recurring intent is a
  candidate **opportunity** (a whole category of demand), not just one page.
- Trends is strong for **mapping intent** on high-volume terms but weak for tiny
  brand-new **names** (below its volume floor) — use web search (trending
  products/repos/news, communities, social) to catch names earliest, then use
  Trends to confirm the curve.
- Use `trends_list` to reuse prior fetches instead of re-fetching (every
  `trends_fetch` is rate-limited on purpose).

## 2. The event-driven pattern (your early-warning edge)

Most high-value opportunities are **events that trigger a demand spike**. When a
rising query breaks out, infer the event behind it and move first:

| Event behind the spike | Demand that spikes |
|------------------------|--------------------|
| Gated/invite-only launch | "X invite code / access" |
| A tool/option gets worse, banned, or restricted | "X alternatives" |
| Shutdown/deprecation rumor | "is X shutting down" |
| Price change | "X pricing / cost" |
| Outage | "is X down" |
| New release | new errors, "what's new in X" |
| New regulation/deadline | "X compliance / deadline" |

Your edge is **detection speed**: the weekly rising-query scan flags the event
the moment its query breaks out. Whoever reaches the audience first — with a
page, a video, or an offer — wins and holds it via the moat.

## 3. Validate beatability (in your chosen channel)

For each candidate, check whether the incumbents in the channel you'd use are
actually beatable:
- **Search**: read page 1 for the bare query. Official site/authority (hard),
  thin aggregator/forum thread (beatable), or nobody (open)? Name ambiguity is
  often an opening (a focused page can rank). Clone/aggregator domains already
  ranking for a big term *prove* the SERP is penetrable — green light.
- **Social/video**: are quality creators already covering it well, or is the
  topic under-served / served only by low-effort content?
- **Paid**: is the keyword/audience cheap to reach relative to the payout?

## 4. Choose how to capture + monetize it

Decide TWO things, from menus — pick by evidence, don't prescribe.

### (A) Acquisition channel (how people find you)
SEO/content site · short-form video (TikTok/Reels/Shorts) · YouTube ·
paid ads · community/forum/Discord · newsletter/email · marketplace listing ·
a free tool that spreads. The right channel depends on where the demand lives
and how fast it spikes (event spikes often favor video/social + a landing page
over slow-to-rank SEO).

### (B) Monetization / funnel (how it makes money)
Match the funnel to the searcher's intent and the **ticket size**:
- **Low-touch, high-volume** — *display ads* (volume/spiky traffic, no buyer
  intent), *affiliate* (commission for referring a purchase), *info-product*
  (templates/guides/courses), *e-commerce/dropshipping*, *paid tool* (free tier
  for reach, paid for power features). Verify affiliate **economics**: who pays,
  how much, one-time vs **recurring**, and the **payout form** (real money vs
  store credit/points — confirm it matches what the user wants).
- **Mid-touch** — *lead generation / lead resale*: capture qualified leads and
  sell them to vendors (esp. B2B/high-value verticals) at a price per lead.
- **High-touch, high-ticket funnels** — the asset is top-of-funnel and the money
  is closed downstream. Examples:
  - **Content → setting → call**: short-form video / YouTube builds attention →
    DM or an appointment-setter qualifies → a sales call closes a high-ticket
    offer (coaching, done-for-you service, agency retainer, B2B SaaS).
  - **VSL / webinar funnel**: ad or organic → landing page/webinar → checkout
    or booked call.
  - **Productized / "drop" service**: a done-for-you service brokered through the
    page or video (you arrange fulfillment).
  - **Community / cohort / membership**: recurring access revenue.

A single opportunity usually **stacks** a channel + a funnel (e.g. trend video →
landing page → booked call; or free tool for traffic → affiliate/leads).
Crucially: **if the core entity in the niche pays nothing** (some platforms have
no affiliate at all), monetize via ads, lead-gen, a high-ticket service funnel,
or by promoting *adjacent* things that do pay — never assume the obvious brand is
the payer.

## 5. Source the data / raw material (so the asset can be built and kept fresh)

For each opportunity, identify where structured data or raw material lives,
preferring machine-readable feeds. This feeds whatever asset you build — pages,
a tool, video scripts, or an offer. Generic places to look, by leverage:
1. **Official structured feeds/APIs** — status JSON, public APIs, RSS,
   changelogs, release feeds, sitemaps.
2. **Pricing / terms / spec pages** — scrape and **diff over time**; the diff is
   itself the freshness moat for pricing/limits/policy/deadline content.
3. **Public registries / filings / official texts** — regulators, government
   datasets, financial filings, standards bodies.
4. **Marketplaces / catalogs / directories** — structured listings to seed and
   enrich your own database (mind their ToS for commercial use).
5. **Communities** — forums, Reddit, Discord, Q&A, social — for real queries,
   error strings, pain points, hooks, and freshly-spiking demand.
6. **Your own measurement** — run a benchmark/harness and publish results nobody
   else has.
Note for each source whether it's free or paid and how to pull it (API endpoint,
RSS, scrape target). Assets should be **auto-generatable** from these on a cron.

## 6. Rank and decide

Score every candidate on three criteria and sort:
- **Difficulty to set up** (1 easy → 5 hard): content/templating is easy;
  interactive tools, live infra, a sales funnel, or fulfillment are harder.
- **Competition** (1 open → 5 saturated): from the beatability read in §3.
- **Financial potential** (1 low → 5 high): from the channel + funnel economics
  in §4 (ticket size × volume × conversion).
A useful composite: **Financial×2 − Difficulty − Competition** (higher = better
risk-adjusted bet). Group into tiers (build-first / out-execute / volume-filler /
needs-an-edge).

## 7. Deliver

Write findings to a `research/` folder. Deliverables depend on the play: a ranked
opportunity map, a per-opportunity sheet (channel + funnel + data sources +
beatability), and the final 3-criteria ranking. Be honest about uncertainty and
verify any monetization or factual claim before repeating it — credibility is
what earns trust, links, and conversions.

Then, if asked, deepen one opportunity (traffic/revenue sizing, exact data
wiring, funnel design) or widen the scan (more head terms, more verticals).
Re-run the rising-query scan periodically — it's the trigger detector for the
next event-driven opening.
"""
