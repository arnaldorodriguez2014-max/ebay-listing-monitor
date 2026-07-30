# eBay → Discord New Listing Monitor

Watches eBay for matching cards and posts a Discord notification when:
- a **new listing** appears (price, link, grade + grading company),
- a tracked listing's **price drops** (green "📉 price drop" alert showing old → new), and
- a **listing is below market** (amber "🔥 below market" alert). Market price is the
  median of **recent eBay sold prices for that card in the same grade** (real recent
  sales; TCGplayer is Cloudflare-blocked and can't be scraped) — a PSA 10 is compared
  to recent PSA 10 sales, a raw to recent raws. Alerts show the market price and the
  listing's % vs market.

**Auction (bid) listings are excluded** by default — only fixed-price / Buy-It-Now
listings are tracked (set `include_auctions: true`, or per-watch `allow_auctions`,
to include them).

**Only US + Canada sellers** are notified by default (from each listing's "Located
in" country). Change with the top-level `allowed_regions` (e.g. `["US"]` or add
more), or per-watch `allowed_regions`. Listings whose location can't be read are
skipped unless `allow_unknown_region: true`.

The monitor is TCG-agnostic (grade detection, currency, and matching all work for any
card game). Currently watching (English unless noted; grades: ungraded / PSA 10 / BGS 10 / BGS 9.5):

**One Piece:**
- **Luffy ST26-005 SP** — SP only (min_price filters out the cheap base card)
- **Sanji OP10-005 Flagship Promo** — any language (JP/Asia promo), Flagship-only
- **Luffy OP05-119 SEC (Alt / Manga Art)** — SEC only (min_price filters the base card)
- **Chopper ST01-006 1st Anniversary** — also catches the "#006" numbering
- **Luffy OP05-060 PSA Magazine Promo** — the PSA Magazine Exclusive promo only
- **Nami OP01-016 Gift Collection 2023** — the Gift Collection 2023 promo
- **Luffy P-099 (Event Pack Vol. 8)** — any language (JP promo)

**Pokémon** (`language: any` — see note):
- **Giratina V 186/196** — Lost Origin alternate full art (not the regular V or any VSTAR)
- **Mew ex 232/091** — Paldean Fates "Bubble Mew" Special Illustration Rare (not the 216/091 Shiny)
- **Mew ex 347/190** — the **Japanese** "Bubble Mew" SAR (Shiny Treasure ex / sv4a), counterpart of 232/091
- **Rayquaza V 194/203** — Evolving Skies alternate full art (not the VMAX alt art 218/203)
- **Rayquaza 3/17** — POP Series 1 (2004) Cosmos Holo Rare (holo only; non-holo excluded)
- **Rayquaza EX 123/124** — Dragons Exalted (2012) Full Art Ultra Rare (not the regular 85/124)

> Vintage grade note: for the older Rayquaza cards (3/17, 123/124), graded copies are
> commonly **PSA 8/9**, which the house grade buckets treat as "other" and don't alert
> on — these track raw + PSA 10 / BGS 10 / BGS 9.5 only.

> Language note: Pokémon watches use `language: any`, not `english`. Unlike One Piece (where
> a card shares one number across languages, so `english` usefully filters), a Pokémon card's
> English and Japanese prints have **different collector numbers** — so requiring the English
> number already excludes the Japanese card, and `english` would only do harm by dropping legit
> listings that say "English **NOT Japanese**".
>
> Grade note: Pokémon slabs are often graded by **CGC/SGC**, which the current grade buckets
> treat as "other" and don't alert on — these watches track raw + PSA 10 / BGS 10 / BGS 9.5 only.

## ☁️ Cloud deployment (primary — runs even when your PC is off)

This monitor runs in the cloud on **GitHub Actions**, so it works 24/7 regardless
of whether any local machine is on:

- **Repo:** https://github.com/cal-chan-cloud/ebay-listing-monitor (public)
- **Schedule / cadence:** `.github/workflows/monitor.yml` is triggered by cron, but
  GitHub throttles scheduled cron hard (measured ~80 min median between fires, not the
  5 min requested). So each triggered job **loops for ~50 minutes**, scanning every
  ~3 min (`poll_interval_seconds`, via `--loop-for-minutes 50`), then exits so the
  updated `seen.db` is committed once. Net effect: ~3-min notification granularity
  while a job is running, with ~30-min gaps between jobs. For true near-zero delay,
  run the loop on an always-on host instead (see "Local setup"). Scans fetch all
  watches concurrently (`scan_workers`, default 6), so a full pass takes ~15-20s.
- **Webhook:** stored as the encrypted GitHub Actions secret `DISCORD_WEBHOOK_URL`
  — it is **not** in the public code (`config.json`'s `discord_webhook_url` is left
  blank; the script reads the env var first).
- **State:** `seen.db` lives in the repo. When a run finds new listings it commits
  the updated `seen.db` back, so no listing is ever alerted twice.

Manage it:
```
gh workflow run monitor.yml -R cal-chan-cloud/ebay-listing-monitor     # run now
gh run list -R cal-chan-cloud/ebay-listing-monitor                     # recent runs
gh secret set DISCORD_WEBHOOK_URL -R cal-chan-cloud/ebay-listing-monitor --body "<url>"
```

**To add/change cards:** edit `config.json` and push (`git push`), or just ask.
The change takes effect on the next scheduled run.

> Notes: The local Windows Task Scheduler job has been **disabled** to avoid
> duplicate alerts (cloud is now the single source). GitHub disables scheduled
> workflows after 60 days of *zero* repo activity — the periodic `seen.db` commits
> on new listings keep it alive; if listings ever go quiet that long, click
> **Run workflow** once (or push any commit) to re-arm it.

## Local setup (optional / fallback)

## Setup

1. Install dependencies (already present on this machine):
   ```
   pip install -r requirements.txt
   ```

2. Create a Discord webhook:
   - In Discord: pick the channel → **Edit Channel** (gear) → **Integrations** →
     **Webhooks** → **New Webhook** → **Copy Webhook URL**.

3. Paste that URL into `config.json` → `discord_webhook_url`
   (replace `PASTE_YOUR_DISCORD_WEBHOOK_URL_HERE`).

## Run

```
python ebay_monitor.py            # run forever, checking every 5 min (config poll_interval_seconds)
python ebay_monitor.py --once     # one pass then exit  (use with Windows Task Scheduler)
python ebay_monitor.py --dry-run  # scan + print matches, send nothing, record nothing
```

**First run behavior:** the *first* time a watch runs it silently records all
current listings as "seen" so you don't get flooded — you'll only be alerted on
listings posted *after* that. To instead alert on everything already up, run once
with `--notify-existing`.

### Windows Task Scheduler (installed but DISABLED)

> ⚠️ This local task is currently **Disabled** because the cloud deployment above
> is now the primary runner. Running both would send duplicate Discord alerts.
> Re-enable with `Enable-ScheduledTask "eBay Luffy Monitor"` **only if** you also
> disable the GitHub Actions schedule. If you re-enable it, set the webhook via a
> Windows env var (`setx DISCORD_WEBHOOK_URL "<url>"`) since it's no longer in
> `config.json`.

A scheduled task named **"eBay Luffy Monitor"** is installed. It runs
`pythonw.exe ebay_monitor.py --once` **every 5 minutes** while you are logged in,
using the real Python install (`...\Programs\Python\Python311\pythonw.exe`) so no
console window pops up. It's configured to **catch up on missed runs** after the
PC wakes/turns on and to **wake the PC from sleep** to run.

> **About "even when the computer is off":** no local scheduled task can run while
> the PC is fully powered **off** — Windows isn't running to launch anything. This
> task covers the next best thing: it runs whenever the PC is on, wakes it from
> **sleep/hibernate**, and catches up after it powers back on. For true 24/7
> coverage (including while your PC is off) the monitor needs to live on an
> always-on host — a cheap cloud VM, a Raspberry Pi, or a service like Render.
> The script runs unchanged there; ask and I'll set that up.

Manage the task:

```powershell
Get-ScheduledTaskInfo "eBay Luffy Monitor"     # last run time + result (0x0 = OK) + next run
Start-ScheduledTask     "eBay Luffy Monitor"   # run right now
Disable-ScheduledTask   "eBay Luffy Monitor"   # pause
Enable-ScheduledTask    "eBay Luffy Monitor"   # resume
Unregister-ScheduledTask "eBay Luffy Monitor" -Confirm:$false   # remove
```

Activity is also logged to `monitor.log` in this folder.

To make it run **whether or not you're logged in**, re-register the task with a
stored password (`-LogonType Password`); that requires your Windows account
password, so it wasn't done automatically.

## Adding more items

Add entries to the `watches` array in `config.json`:

```json
{
  "name": "Zoro OP01-001",
  "query": "zoro op01-001 alt art",
  "require": ["op01-001"],
  "grades": ["ungraded", "psa10", "bgs10", "bgs9.5"],
  "language": "english",
  "min_price": null,
  "max_price": null
}
```

- `queries` — a **list** of search phrasings, all searched and merged/deduped.
  Broader/alternate wordings surface differently-titled listings of the same card;
  the require/grade filters keep them precise. (`query`, a single string, still works.)
- `match_any` — **name-fallback / multi-signature matching.** A list of signatures;
  a listing matches if it satisfies ANY one. Each signature is a require-list (same
  format as `require`). Use one signature keyed on the card number and another on
  character-name + descriptors, so you also catch listings that number the card
  differently (e.g. O-Nami as OP06-101 *or* OP07-101) or omit the number entirely:
  ```json
  "match_any": [
    [["op06-101", "op07-101"], ["500 years", "op07"]],
    [["nami", "o-nami"], ["500 years", "op07"], ["sp", "alt art"]]
  ]
  ```
  When `match_any` is set it replaces `require`. `exclude`, lot-detection, grade and
  language filters still apply.
- `query` — what gets typed into eBay search. Keep it fairly broad; eBay
  fuzzy-matches, so use `require` to pin the exact card.
- `require` — **list of terms that must ALL appear in the title** (case- and
  punctuation-insensitive, so `op05-119` = `OP05 119` = `op05119`). This is what
  stops eBay's fuzzy search from alerting you about the wrong card. Add the
  distinguishing words too, e.g. `["op10-005", "flagship"]` to get only the
  Flagship promo and not the same-numbered base card.
- `exclude` — optional extra terms to reject. Proxies/replicas
  (`proxy`, `orica`, `custom`, `handmade`, …) and **extended-art display cases**
  (merch, not the card) are already excluded globally. Sealed product and bulk/quantity
  lots (booster box, ETB, "N cards lot", "lot of N", jumbo, …) are also detected
  centrally (`is_bulk_or_sealed`, word-boundary matched on the raw title so it can't
  misfire on things like "Holo TCG"), so watches don't need to list those per-card.
- `grades` — any of: `ungraded`, `psa10`, `bgs10`, `bgs9.5`. (More can be added in
  `classify_grade()` — e.g. `psa9`, `cgc10`.)
- `language` — `english` (default), `japanese`, `chinese`, `korean`, or `any`.
- `min_price` / `max_price` — optional numeric filters (use `null` to disable).
- `allow_auctions` — set `true` to include auction listings for this watch
  (default: auctions excluded). Global default: `include_auctions` (top level).
- `allow_lots` — set `true` to include multi-card lots for this watch.
- `allowed_regions` — per-watch region allow-list (canonical `US` / `CA`);
  overrides the top-level default `["US", "CA"]`.
- `price_drop_pct` / `price_drop_min` — per-watch override of the drop thresholds.

## Reliability & maintenance

- **Health check** — if a whole scan scrapes 0 listings across every watch (eBay
  blocking, or an HTML change), you get a one-time Discord ⚠️ alert (and a ✅ when it
  recovers). This is what stops a broken scraper from failing silently.
- **Auto-pruning** — each listing's `last_seen` date is tracked; rows not seen in
  `prune_days` (default 30) are deleted, so `seen.db` and the git history don't grow
  forever and sold/ended listings clear out. (`last_seen` only rewrites once/day, so
  it doesn't spam commits.)
- **Config validation** — `config.json` is checked on startup; warnings print for
  empty `queries`, a match-everything watch (no `require`/`match_any`), unknown
  grades, or bad region codes.
- **Tests + CI** — `tests/test_monitor.py` runs offline (grade/lot/region/price-drop/
  validation/health); `.github/workflows/tests.yml` runs it on every push.
- **Scraper resilience** — bids, location, and price are read by text pattern with
  CSS-class fallbacks, so eBay's frequent layout renames are less likely to break it.
- **Transient-error retries** — the HTTP session auto-retries connection resets,
  read timeouts, and 5xx/429 responses with exponential backoff, so a brief network
  blip no longer drops a query for the whole pass. (eBay's 403 / "Pardon Our
  Interruption" soft-block is handled separately, with a cookie re-prime between tries.)
- **Currency-aware pricing** — Canadian sellers on `ebay.com` show `C $` (CAD) and
  other regions show `£`/`€`; the scraper detects the currency so a CAD/GBP/EUR
  listing is never compared against the USD sold-median (which would fake "below
  market" deals). The sold-median itself is computed from USD sales only.
- **Grade-spelling tolerance** — `PSA-10`, `PSA10`, `BGS-9.5` (not just `PSA 10`)
  all classify correctly instead of falling through to "graded (other)".
- **Health-check debounce** — a single quiet pass where nothing matches no longer
  trips a false ⚠️ alert; the "0 matched" alarm only fires after several consecutive
  zero-match scans (`zero_match_alert_scans`, default 3). A true "0 scraped"
  (scraper blocked / layout change) still alerts immediately.
- **Log rotation** — `monitor.log` is capped (~2 MB); once it exceeds that it's
  rotated to `monitor.log.1` on the next start, so it can't grow without bound.
- **Market-price cache** — a real recent-sold median is cached ~6h, but a failed or
  too-few-comps lookup (`None`) is *not* cached, so it's retried on the next scan
  instead of leaving the card without a market price for hours.

## Market price & below-market deals

> ⚠️ **Sold comps are unavailable; deal detection now falls back to asking prices.**
> eBay requires sign-in to view sold/completed listings — an unauthenticated request
> returns a "Pardon Our Interruption" challenge or a sign-in wall, so no sold data
> can be read (verified 2026-07-24; every cached market price in the live DB was
> `null`). The monitor detects this, posts a one-time Discord notice, and trips a
> circuit breaker that parks sold lookups for 24h — repeatedly retrying a blocked
> endpoint was getting the whole session challenged, which would break the
> active-listing scrape too.
>
> **Fallback: "typical asking (active)".** Deal detection now uses a low percentile
> (default 25th) of *current asking prices* for the same card and grade, computed
> from the listings each scan already fetches — **zero extra requests, no account
> credentials**. This is a weaker signal than real sales (sellers list optimistically),
> so it demands a wider gap (`below_ask_pct`, default 10% vs 5% for sold) and every
> alert is labelled **"below asking"** with a **Typical asking (active)** field — never
> presented as a real market price. If sold data ever becomes readable again, sold
> automatically takes precedence and the labels switch back to "market".

The monitor estimates a market price **per grade bucket** from **recent eBay
sold/completed listings** (real transactions) for that exact card: for each grade
a watch tracks it takes the most-recent sales *in that same grade*, trims outliers
(damaged/junk lows and mislabeled highs), and uses the median. A PSA 10 listing is
therefore compared only against recent PSA 10 sales, a raw against recent raws, and
so on. Each bucket is cached ~6h in the DB (`market:<watch>:<grade>`), and a watch's
sold listings are fetched at most once per refresh (shared across its buckets).

- Priced buckets: **ungraded, PSA 10, BGS 10, BGS 9.5**. `other_graded` (a mix of
  companies/grades) is never priced — a single median across it would be meaningless.
- Every alert with a market price shows **Market (recent sold)** and the listing's **% vs market**.
- A listing priced between `below_market_floor` (default **0.5×** market — anything
  cheaper is treated as damaged/mislabeled junk, not a deal) and
  `1 − below_market_pct` (default **5%** below) is flagged a **🔥 below-market deal**.
- New below-market listings are flagged inline; an already-seen listing that *crosses*
  below market fires a distinct 🔥 alert (tracked so it never repeats).
- A bucket with too few recent sold comps simply gets no market price (no false deals).

Tune in `config.json`: `below_market_pct`, `below_market_floor` (both per-watch overridable).

**Asking-price fallback settings** (used while sold data is gated):
- `ask_percentile` (default `25`) — which percentile of active asking prices is the
  reference. Lower = stricter (fewer, better deals).
- `ask_min_listings` (default `8`) — minimum comparable active listings in a grade
  bucket before a reference is computed at all, so a thin market can't fake a "deal".
- `below_ask_pct` (default `10`, per-watch overridable) — how far under the asking
  reference a listing must be. Wider than the sold threshold because asks are noisier.
- `reference_override` (per-watch) — pin the reference for a grade to a fixed value,
  e.g. `"reference_override": {"ungraded": 75}`, when the computed asking percentile
  runs high and pings too much. Takes precedence over sold/asking and shows as
  **Reference (set)** in the alert. Below-market then fires only for prices in
  `[value × below_market_floor, value × (1 − below_ask_pct))` (so at $75 with the
  defaults, ~$37.50–$67.50).

## Price-drop alerts

Every scan records each tracked listing's price. When a listing's price falls at
least **`price_drop_pct`** (top-level, default **5%**) **and** at least
**`price_drop_min`** (default **$1**) below its last-recorded price, you get a
green **📉 price drop** alert (old → new, % off). The reference then resets to the
new price, so small wiggles don't spam you and only further drops re-alert. Price
rises never alert (so excluded-by-default auctions wouldn't trigger it anyway).

### Language filtering

By default a watch is **English only**: listings whose titles are flagged
Japanese/Chinese/Korean (the words "Japanese", "Jp", "Chinese", CJK characters,
etc.) are dropped. To monitor a card in Japanese instead, set that watch's
`"language": "japanese"`.

> Note: listings with **no** language marker at all are kept (so genuine English
> listings that simply don't say "English" aren't missed). This can occasionally
> let through an unmarked import — tell me if you'd prefer strict "must say
> English" matching instead.

## How grading is detected

The listing title is scanned:
- `PSA 10` → PSA 10
- `BGS 9.5` / `Beckett 9.5` → BGS 9.5
- `BGS 10` / `Beckett 10` → BGS 10
- any other grading company/number (PSA 9, CGC, SGC, …) → *ignored* (not in your buckets)
- no grading company mentioned → Ungraded / Raw

Detection relies on sellers writing the grade in the title (standard practice for
slabs). `seen.db` (SQLite, auto-created) tracks which listings have already been
alerted so you never get a duplicate.

## Notes

- eBay bot-protection 403s a cold request, so the script first visits the eBay
  homepage to seed cookies, then re-primes automatically if a 403 appears later.
- If eBay ever hard-blocks scraping, the robust alternative is the official
  [eBay Browse API](https://developer.ebay.com/api-docs/buy/browse/overview.html)
  (free dev account + OAuth) — `fetch_listings()` is the only function that would
  need swapping.
