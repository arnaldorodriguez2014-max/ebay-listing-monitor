#!/usr/bin/env python3
"""Offline regression tests for ebay_monitor (no network). Run: python tests/test_monitor.py

Covers grade classification, language, card/lot/auction/region filters, price
parsing, config validation, and the end-to-end new-listing + price-drop logic in
scan_once (with fetch/Discord mocked and a temp DB).
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ebay_monitor as m

# Emojis appear in some log lines. Production wraps stdout in _Tee (which swallows
# console-encoding errors) and CI is UTF-8; a bare Windows console (cp1252) is not,
# so make this harness tolerate un-encodable chars the same way.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors="replace")
    except Exception:
        pass

fails = []


def check(name, got, want):
    if got != want:
        fails.append(name)
        print(f"  [FAIL] {name}: got={got!r} want={want!r}")
    else:
        print(f"  [pass] {name}")


def ok(name, cond):
    check(name, bool(cond), True)


# --------------------------------------------------------------------------
print("== classify_grade ==")
check("PSA 10", m.classify_grade("PSA 10 Luffy ST26-005"), "psa10")
check("PSA 100 not PSA10", m.classify_grade("Lot of PSA 100 Luffy"), "other_graded")
check("BGS 9.5", m.classify_grade("Luffy BGS 9.5"), "bgs9.5")
check("BGS 10 not 9.5", m.classify_grade("Luffy BGS 10 Pristine"), "bgs10")
check("Beckett 9.5", m.classify_grade("Luffy Beckett 9.5"), "bgs9.5")
check("PSA 9 -> other", m.classify_grade("Luffy PSA 9"), "other_graded")
check("CGC 10 -> other", m.classify_grade("Luffy CGC 10"), "other_graded")
check("raw", m.classify_grade("Luffy ST26-005 SP Foil English"), "ungraded")
check("ACE 10 slab -> other", m.classify_grade("O-Nami ACE 10 OP06-101"), "other_graded")
check("TAG 10 slab -> other", m.classify_grade("Chopper TAG 10 ST01-006"), "other_graded")
check("ARS 10 slab -> other", m.classify_grade("Luffy ARS 10 ST26-005"), "other_graded")
check("Ace character raw", m.classify_grade("Portgas D. Ace OP01-002 NM"), "ungraded")
check("with tag raw", m.classify_grade("Nami OP06-101 mint with tag"), "ungraded")
check("PSA-10 hyphen", m.classify_grade("Luffy ST26-005 PSA-10 Gem"), "psa10")
check("PSA10 no space", m.classify_grade("Luffy ST26-005 PSA10"), "psa10")
check("BGS-9.5 hyphen", m.classify_grade("Luffy BGS-9.5"), "bgs9.5")
check("BGS10 no space", m.classify_grade("Luffy BGS10 Pristine"), "bgs10")
# grade words between "PSA" and "10" must still bucket as psa10 (common on slabs)
check("PSA GEM MT 10", m.classify_grade("Charizard PSA GEM MT 10 020/073"), "psa10")
check("PSA Grade 10", m.classify_grade("Celebi V 245/264 PSA Grade 10"), "psa10")
check("PSA GEM MINT 10", m.classify_grade("Mew ex 232/091 PSA GEM MINT 10"), "psa10")
check("PSA Graded 10 lot stays other", m.classify_grade("PSA Graded 10 Cards Lot"), "other_graded")

print("== language ==")
check("japanese word", m.title_language("Luffy ST26-005 Japanese"), "japanese")
check("cjk", m.title_language("ルフィ ST26-005"), "cjk")
check("unknown", m.title_language("Luffy ST26-005 Foil"), "unknown")
ok("en keeps unknown", m.passes_language("Luffy ST26-005 Foil", "english"))
ok("en drops japanese", not m.passes_language("Luffy Japanese", "english"))
ok("any keeps japanese", m.passes_language("Luffy Japanese", "any"))
# negated foreign mentions ("English NOT Japanese") must not flip an English card
check("English NOT Japanese", m.title_language("Luffy OP05-119 English NOT Japanese"), "english")
check("not a Japan import", m.title_language("Luffy OP05-119 not a Japan import English"), "english")
ok("en keeps 'not japanese'", m.passes_language("Luffy OP05-119 English NOT Japanese", "english"))
ok("bare japanese still dropped", not m.passes_language("Luffy OP05-119 Japanese", "english"))

print("== matches_filters / require / aliases / match_any ==")
ok("require hit (punct-insensitive)", m.matches_filters("Luffy OP05 119 Manga", ["op05-119"], []))
ok("require miss", not m.matches_filters("Luffy OP05-060", ["op05-119"], []))
ok("AND both", m.matches_filters("Sanji OP10-005 Flagship", ["op10-005", "flagship"], []))
ok("AND one missing", not m.matches_filters("Sanji OP10-005 Royal Blood", ["op10-005", "flagship"], []))
ok("alias OR hit", m.matches_filters("O-Nami OP06-101 OP07 Alt", ["op06-101", ["500 years", "op07"]], []))
ok("alias OR miss", not m.matches_filters("O-Nami OP06-101 Wings", ["op06-101", ["500 years", "op07"]], []))
ok("default excludes proxy", not m.matches_filters("Luffy OP05-119 Proxy", ["op05-119"], []))
ok("per-watch exclude", not m.matches_filters("Luffy OP05-119 bundle", ["op05-119"], ["bundle"]))
MA = [["op15-086", ["alt art"]], [["nami"], ["alt art"], ["kami island"], ["sr"]]]
ok("match_any via number", m.matches_filters("Nami OP15-086 Alt Art SR", None, [], MA))
ok("match_any via name fallback", m.matches_filters("Nami Alt Art SR Kami Island", None, [], MA))
ok("match_any base excluded", not m.matches_filters("Nami OP15-086 Foil Kami Island", None, [], MA))

print("== is_lot ==")
ok("multi-number lot", m.is_lot("Luffy OP12-015 + ST26-005 + OP02-062 Set"))
ok("single card not lot", not m.is_lot("Bandai OP15 Luffy ST26-005 SP 2026"))
# Pokemon same-set multi-number lot (two numbers sharing a set total)
ok("pokemon two-number lot", m.is_lot("Mew ex 232/091 + 216/091 two-card lot"))
ok("pokemon single not lot", not m.is_lot("Mew ex 232/091 Paldean Fates SIR"))
ok("pop-report ratio not lot", not m.is_lot("Mew ex 232/091 PSA 10 POP 12/500"))

print("== is_bulk_or_sealed (word-boundary; no substring misfire) ==")
ok("booster box", m.is_bulk_or_sealed("Celebi V 245/264 Fusion Strike Booster Box Sealed"))
ok("ETB", m.is_bulk_or_sealed("Giratina V 186/196 Lost Origin Elite Trainer Box ETB"))
ok("bulk lot", m.is_bulk_or_sealed("Mew ex 232/091 Bulk Lot 50 Cards"))
ok("cards collection", m.is_bulk_or_sealed("Fusion Strike 245 Cards Collection Celebi V"))
ok("bare word lot", m.is_bulk_or_sealed("Giratina V 186/196 + Palkia lot"))
ok("Holo TCG single (not sealed)", not m.is_bulk_or_sealed("Giratina V 186/196 Lost Origin Holo TCG"))
ok("Holo Trading Card single", not m.is_bulk_or_sealed("Celebi V 245/264 Fusion Strike Holo Trading Card"))
ok("etb substring not misfire", not m.is_bulk_or_sealed("Pokemon trumpetbandit Celebi V 245/264"))
ok("plain single not sealed", not m.is_bulk_or_sealed("Mew ex 232/091 Paldean Fates SIR NM"))

print("== extended-art-case merch exclude ==")
ok("extended artwork case excluded",
   not m.matches_filters("Pokemon Mew EX SIR Paldean Fates 232/091 Extended Artwork Case", ["mew ex"], []))
ok("extended art case excluded",
   not m.matches_filters("Celebi V 245/264 Fusion Strike Extended Art Case Display", ["celebi v"], []))
ok("real card not excluded by art-case term",
   m.matches_filters("Mew ex 232/091 Paldean Fates SIR NM", ["mew ex"], []))

print("== is_auction ==")
ok("auction with bids", m.is_auction({"bids": "5 bids", "format": None}))
ok("zero bids still auction", m.is_auction({"bids": "0 bids", "format": None}))
ok("BIN not auction", not m.is_auction({"bids": None, "format": "Buy It Now"}))

print("== region ==")
check("US", m.canon_region("United States"), "US")
check("CA", m.canon_region("Canada"), "CA")
check("other", m.canon_region("Japan"), "OTHER")
check("none", m.canon_region(None), None)
ok("US passes", m.passes_region("United States", {"US", "CA"}, False))
ok("Japan fails", not m.passes_region("Japan", {"US", "CA"}, False))
ok("unknown strict fails", not m.passes_region(None, {"US", "CA"}, False))
ok("unknown lenient passes", m.passes_region(None, {"US", "CA"}, True))

print("== parse_price / currency / price_ok / clean_title ==")
check("price simple", m.parse_price("$949.99")[1], 949.99)
check("price thousands", m.parse_price("$2,600.00")[1], 2600.0)
check("price range low", m.parse_price("$10.00 to $20.00")[1], 10.0)
check("currency plain USD", m.parse_price("$949.99")[2], "USD")
check("currency US $", m.parse_price("US $949.99")[2], "USD")
check("currency CAD C $", m.parse_price("C $80.00")[2], "CAD")
check("currency GBP", m.parse_price("£75.00")[2], "GBP")
check("currency EUR", m.parse_price("€90.00")[2], "EUR")
check("currency AUD", m.parse_price("AU $120.00")[2], "AUD")
check("currency none", m.parse_price("90.00")[2], None)
check("CAD number still parsed", m.parse_price("C $80.00")[1], 80.0)
ok("min floor", not m.price_ok(50.0, {"min_price": 100}))
ok("none passes", m.price_ok(None, {"min_price": 100}))
check("clean title", m.clean_title("Luffy ST26-005 Opens in a new window or tab"), "Luffy ST26-005")

print("== validate_config ==")
warns = m.validate_config({"watches": [
    {"name": "ok", "queries": ["x"], "require": ["op01-001"], "grades": ["psa10"]},
    {"name": "bad", "grades": ["psa11"], "allowed_regions": ["Mars"]},
]})
ok("flags missing queries", any("no 'queries'" in w for w in warns))
ok("flags match-all", any("match EVERY" in w for w in warns))
ok("flags bad grade", any("unknown grade" in w for w in warns))
ok("flags bad region", any("unrecognized region" in w for w in warns))

# --------------------------------------------------------------------------
print("== scan_once: new-listing + dedup + price-drop (mocked) ==")

def L(item_id, price_str, price_low, title="Luffy OP05-119 Manga English", currency="USD"):
    return {"item_id": item_id, "title": title, "price_str": price_str, "price_low": price_low,
            "currency": currency,
            "url": f"https://www.ebay.com/itm/{item_id}", "image": None, "condition": None,
            "shipping": None, "bids": None, "format": None, "location": "United States"}

WATCH = {"name": "W", "require": ["op05-119"], "grades": ["ungraded"], "language": "english"}
CFG = {"discord_webhook_url": "https://discord.test/wh", "ebay_domain": "www.ebay.com",
       "price_drop_pct": 5, "price_drop_min": 1, "watches": [WATCH]}

tmp = os.path.join(tempfile.gettempdir(), "ebay_test_monitor.db")
if os.path.exists(tmp):
    os.remove(tmp)
m.DB_PATH = tmp
conn = m.db_connect()
sends = []
m.send_discord = lambda url, name, lst, grade, event="new", old_price_str=None, drop_pct=None, \
    market_price=None, **kw: \
    sends.append((event, lst["item_id"], old_price_str, lst["price_str"], drop_pct))
health = []
m.send_simple_discord = lambda url, title, text, color: health.append((title, text))

def run(fixtures, **kw):
    m.fetch_listings = lambda d, q, **k: list(fixtures)
    m.fetch_all = lambda d, w, **k: list(fixtures)
    sends.clear()
    m.scan_once(CFG, conn, **kw)
    return list(sends)

ok("seed silent", run([L("1", "$100.00", 100.0)]) == [])
ok("new listing alerts", run([L("1", "$100.00", 100.0), L("2", "$50.00", 50.0)]) == [("new", "2", None, "$50.00", None)])
ok("no duplicate", run([L("1", "$100.00", 100.0), L("2", "$50.00", 50.0)]) == [])
s = run([L("1", "$90.00", 90.0), L("2", "$50.00", 50.0)])
ok("price drop alert 10%", s == [("drop", "1", "$100.00", "$90.00", 10)])
ok("no re-drop when stable", run([L("1", "$90.00", 90.0), L("2", "$50.00", 50.0)]) == [])
ok("increase no alert", run([L("1", "$200.00", 200.0), L("2", "$50.00", 50.0)]) == [])
jp = L("7", "$10.00", 10.0); jp["location"] = "Japan"
res = run([jp, L("1", "$200.00", 200.0)])   # jp excluded (region); item 1 seen -> no alert
ok("japan listing excluded in scan", not any(r[1] == "7" for r in res))

print("== health check + prune ==")
m.meta_set(conn, "health", "ok"); health.clear()
run([])                                   # 0 scraped across all watches -> down (scrape broken)
ok("health down on 0 scraped", any("scraped across" in txt for _, txt in health))
health.clear()
run([L("1", "$200.00", 200.0)])           # scraping + matching back -> recovered
ok("health recovered alerted", any("recover" in t.lower() for t, _ in health))
health.clear()
# 0 matched is debounced: a single quiet pass must NOT alert; only a sustained
# streak (default 3 scans) does — that's a real filter/layout break, not quiet inventory.
run([L("z", "$10.00", 10.0, "Unrelated Card XYZ")])
ok("single 0-matched pass does not alert", not any("0 matched" in txt for _, txt in health))
run([L("z", "$10.00", 10.0, "Unrelated Card XYZ")])
ok("second 0-matched pass still quiet", not any("0 matched" in txt for _, txt in health))
run([L("z", "$10.00", 10.0, "Unrelated Card XYZ")])   # 3rd consecutive -> down
ok("health down after sustained 0 matched", any("0 matched" in txt for _, txt in health))
health.clear()
run([L("1", "$200.00", 200.0)])                       # match returns -> streak resets, recovered
ok("recovered after match returns", any("recover" in t.lower() for t, _ in health))

stale = (m.datetime.now(m.timezone.utc) - m.timedelta(days=40)).date().isoformat()
conn.execute("INSERT OR REPLACE INTO seen(watch,item_id,grade,first_seen,price,price_str,last_seen) "
             "VALUES(?,?,?,?,?,?,?)", ("W", "999", "ungraded", "t", 10.0, "$10", stale))
conn.commit()
before = conn.execute("SELECT COUNT(*) FROM seen WHERE item_id='999'").fetchone()[0]
m.prune_seen(conn, 30)
after = conn.execute("SELECT COUNT(*) FROM seen WHERE item_id='999'").fetchone()[0]
ok("prune removes stale row", before == 1 and after == 0)
fresh = conn.execute("SELECT COUNT(*) FROM seen WHERE item_id='1'").fetchone()[0]
ok("prune keeps fresh row", fresh == 1)

print("== market price + below-market ==")
check("median", m._median([3, 1, 2]), 2)
check("median even", m._median([1, 2, 3, 4]), 2.5)
check("sold date parse", m._parse_sold_date("Sold Jul 19, 2026"), "2026-07-19")
# Year rollover: a yearless "Sold <far-future-month> <day>" must roll back a year
# rather than land in the future. Pick the month 6 months ahead of 'today'.
_future_mo = (m.datetime.now(m.timezone.utc).month % 12) + 6
_future_mo = _future_mo if _future_mo <= 12 else _future_mo - 12
_mon = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"][_future_mo - 1]
_parsed_year = int(m._parse_sold_date(f"Sold {_mon.capitalize()} 15")[:4])
ok("yearless future month rolls back a year", _parsed_year <= m.datetime.now(m.timezone.utc).year)
check("median recent price (trimmed)",
      m.median_recent_price([("2026-07-01", 100.0, "ungraded"),
                             ("2026-07-02", 110.0, "ungraded"),
                             ("2026-07-03", 5.0, "ungraded"),   # junk low, trimmed
                             ("2026-07-04", 90.0, "ungraded")], "ungraded"), 100.0)
check("median recent price ignores other buckets",
      m.median_recent_price([("2026-07-01", 500.0, "psa10")], "ungraded"), None)

MKT = {"v": 100.0}
m.get_market_prices = lambda conn_, domain, watch, grades, **k: {"ungraded": MKT["v"]}
run([L("b2", "$98.00", 98.0)])            # market 100 -> 98 not below (needs <95); seeds below_alerted=0
MKT["v"] = 120.0                          # market rises -> 98 now below 120*0.95=114
s = run([L("b2", "$98.00", 98.0)])
ok("below-market crossing pings", any(r[0] == "below_market" and r[1] == "b2" for r in s))
ok("below-market not repeated", not any(r[0] == "below_market" for r in run([L("b2", "$98.00", 98.0)])))
below_flag = conn.execute("SELECT below_alerted FROM seen WHERE item_id='b2'").fetchone()[0]
ok("below_alerted persisted", below_flag == 1)

# A CAD-priced listing must NOT be compared against the USD market median (that
# manufactured fake deals). It still alerts as new, but never below-market.
MKT["v"] = 100.0
cad = L("cad1", "C $60.00", 60.0, currency="CAD")   # 60 < 95 in raw number, but CAD
scad = run([cad])                                    # first pass: watch W already seeded -> new alert
ok("CAD listing alerts as new", any(r[1] == "cad1" for r in scad))
cad_below = conn.execute("SELECT below_alerted FROM seen WHERE item_id='cad1'").fetchone()[0]
ok("CAD not flagged below USD market", cad_below == 0)

print("== per-grade market (graded slab priced against its own bucket) ==")
# A PSA 10 listing is flagged below-market only against the PSA 10 sold median,
# and is unaffected by the ungraded median.
GWATCH = {"name": "G", "require": ["op05-119"], "grades": ["ungraded", "psa10"], "language": "english"}
GCFG = {"discord_webhook_url": "https://discord.test/wh", "ebay_domain": "www.ebay.com",
        "price_drop_pct": 5, "price_drop_min": 1, "watches": [GWATCH]}
m.get_market_prices = lambda conn_, domain, watch, grades, **k: {"ungraded": 100.0, "psa10": 1000.0}
# Pre-seed watch G so it isn't in silent first-run mode -> new listings alert.
conn.execute("INSERT OR IGNORE INTO seen(watch,item_id,grade,first_seen,price,price_str,last_seen) "
             "VALUES('G','seed0','psa10','t',999,'$999','2026-07-01')")
conn.commit()
def grun(fixtures):
    m.fetch_all = lambda d, w, **k: list(fixtures)
    sends.clear(); m.scan_once(GCFG, conn, **{}); return list(sends)
psa = L("g1", "$800.00", 800.0, "PSA 10 Luffy OP05-119 Manga English")     # 800 < 1000*0.95 -> below
raw = L("g2", "$800.00", 800.0, "Luffy OP05-119 Manga English")           # 800 > 100 ungraded -> not below
s = grun([psa, raw])
ok("psa10 slab alerts as new", any(r[0] == "new" and r[1] == "g1" for r in s))
ok("raw alerts as new", any(r[0] == "new" and r[1] == "g2" for r in s))
g1_below = conn.execute("SELECT below_alerted FROM seen WHERE item_id='g1'").fetchone()[0]
g2_below = conn.execute("SELECT below_alerted FROM seen WHERE item_id='g2'").fetchone()[0]
ok("psa10 slab below its own bucket", g1_below == 1)      # priced vs psa10 median (1000)
ok("raw not below (own bucket 100)", g2_below == 0)       # NOT dragged below by psa10 median

print("== market-prices cache (None not cached, real cached, shared fetch) ==")
import importlib
importlib.reload(m)          # restore real market functions (monkeypatched above)
fetch_calls = {"n": 0}
def _fake_sold(domain, watch):
    fetch_calls["n"] += 1
    if fetch_calls["n"] == 1:
        return []                                    # too few comps -> None everywhere
    return [(f"2026-07-{i:02d}", 42.0, "ungraded") for i in range(1, 6)]
m.fetch_sold_sales = _fake_sold
m.meta_set(conn, "market_circuit", '{"fails": 0, "until": null}')
mw = {"name": "MKTcache", "require": ["op05-119"], "grades": ["ungraded"]}
r1 = m.get_market_prices(conn, "www.ebay.com", mw, ["ungraded"])   # no comps -> None
ok("unpriceable bucket returns None", r1["ungraded"] is None)
_cached = m.meta_get(conn, "market:MKTcache:ungraded")
ok("None is negative-cached", _cached is not None and json.loads(_cached)["price"] is None)
r2 = m.get_market_prices(conn, "www.ebay.com", mw, ["ungraded"])   # inside negative TTL
ok("negative cache avoids refetch every scan", fetch_calls["n"] == 1 and r2["ungraded"] is None)
# Expire the negative entry -> it retries and now finds real comps.
_old = (m.datetime.now(m.timezone.utc) - m.timedelta(hours=m.MARKET_NONE_CACHE_HOURS + 1)).isoformat()
m.meta_set(conn, "market:MKTcache:ungraded", json.dumps({"price": None, "ts": _old}))
r3 = m.get_market_prices(conn, "www.ebay.com", mw, ["ungraded"])
ok("negative cache expires and recomputes", r3["ungraded"] == 42.0 and fetch_calls["n"] == 2)
r4 = m.get_market_prices(conn, "www.ebay.com", mw, ["ungraded"])   # served from cache
ok("real market served from cache", r4["ungraded"] == 42.0 and fetch_calls["n"] == 2)
ok("other_graded never priced",
   m.get_market_prices(conn, "www.ebay.com", mw, ["other_graded"]) == {})

print("== one-time below-flag baseline (no alert storm on first reference) ==")
# Simulate the real deploy: existing rows stored with below_alerted=0 while no
# reference existed. The first scan that HAS a reference must baseline silently.
_real_gmp, _real_send = m.get_market_prices, m.send_discord   # restored after this block
m.send_discord = lambda url, name, lst, grade, event="new", old_price_str=None, \
    drop_pct=None, market_price=None, **kw: \
    sends.append((event, lst["item_id"], old_price_str, lst["price_str"], drop_pct))
m.meta_set(conn, "ask_baseline_done", "")
conn.execute("DELETE FROM seen WHERE watch='BL'")
for i, p in enumerate([50.0, 55.0, 60.0]):
    conn.execute("INSERT INTO seen(watch,item_id,grade,first_seen,price,price_str,last_seen,below_alerted) "
                 "VALUES('BL',?,'ungraded','t',?,?, '2026-07-01',0)", (f"bl{i}", p, f"${p}"))
conn.commit()
BLW = {"name": "BL", "require": ["op05-119"], "grades": ["ungraded"], "language": "english"}
BLCFG = {"discord_webhook_url": "https://discord.test/wh", "ebay_domain": "www.ebay.com",
         "watches": [BLW]}
m.get_market_prices = lambda conn_, domain, watch, grades, **k: {"ungraded": 100.0}
blf = [L(f"bl{i}", f"${p}", p) for i, p in enumerate([50.0, 55.0, 60.0])]
m.fetch_all = lambda d, w, **k: list(blf)
sends.clear(); m.scan_once(BLCFG, conn)
ok("no below-market storm on first reference",
   not any(r[0] == "below_market" for r in sends))
flags = [r[0] for r in conn.execute("SELECT below_alerted FROM seen WHERE watch='BL'")]
ok("below flags baselined instead", all(f == 1 for f in flags))
ok("baseline marked done", m.meta_get(conn, "ask_baseline_done") == "1")
# A genuine later crossing still alerts. Clear the flag only (changing the stored
# price would register as a price DROP and short-circuit the below check).
conn.execute("UPDATE seen SET below_alerted=0 WHERE watch='BL' AND item_id='bl0'")
conn.commit()
sends.clear(); m.scan_once(BLCFG, conn)
ok("real crossing still alerts after baseline",
   any(r[0] == "below_market" and r[1] == "bl0" for r in sends))
m.get_market_prices, m.send_discord = _real_gmp, _real_send   # don't leak into later tests

print("== active-asking reference (fallback when sold data is gated) ==")
check("percentile p25", m._percentile([10, 20, 30, 40, 50], 25), 20.0)
check("percentile p50", m._percentile([10, 20, 30, 40, 50], 50), 30.0)
check("percentile single", m._percentile([7], 25), 7)
check("percentile empty", m._percentile([], 25), None)

AW = {"name": "AR", "require": ["op05-119"], "grades": ["ungraded"], "language": "english"}
def AL(i, price, title="Luffy OP05-119 Manga English", **kw):
    d = L(str(i), f"${price}", float(price), title)
    d.update(kw)
    return d
# 8 raw asks: 100..170 -> p25 = 117.5 (interpolated)
asks = [AL(i, p) for i, p in enumerate([100, 110, 120, 130, 140, 150, 160, 170])]
ref = m.active_asking_reference(asks, AW, {"ungraded"})
check("asking p25 reference", ref.get("ungraded"), 117.5)
ok("too few asks -> no reference",
   m.active_asking_reference(asks[:4], AW, {"ungraded"}) == {})
# auctions must not drag the reference down
withauc = asks + [AL(99, 5, bids="3 bids")]
check("auctions excluded from reference",
      m.active_asking_reference(withauc, AW, {"ungraded"}).get("ungraded"), 117.5)
# non-USD must not pollute a USD reference
withcad = asks + [AL(98, 5, currency="CAD")]
check("non-USD excluded from reference",
      m.active_asking_reference(withcad, AW, {"ungraded"}).get("ungraded"), 117.5)
# graded listings land in their own bucket, not the raw one
mixed = asks + [AL(200 + i, p, "PSA 10 Luffy OP05-119 Manga English")
                for i, p in enumerate([500, 520, 540, 560, 580, 600, 620, 640])]
mref = m.active_asking_reference(mixed, AW, {"ungraded", "psa10"})
ok("per-grade asking buckets stay separate",
   mref.get("ungraded") == 117.5 and mref.get("psa10") == 535.0)
# A card number covering both a cheap base printing and an expensive SP: without a
# price window the p25 lands in the junk cluster; min_price isolates the real card.
bimodal = [AL(300 + i, p) for i, p in enumerate([3, 4, 5, 6, 7, 8, 9, 10])] + \
          [AL(400 + i, p) for i, p in enumerate([300, 320, 340, 360, 380, 400, 420, 440])]
check("bimodal without window picks junk cluster",
      m.active_asking_reference(bimodal, AW, {"ungraded"}).get("ungraded"), 6.75)
AW_MIN = dict(AW, min_price=100)
check("min_price isolates the real comparables",
      m.active_asking_reference(bimodal, AW_MIN, {"ungraded"}).get("ungraded"), 335.0)

print("== market circuit breaker (sold data blocked) ==")
# eBay requires sign-in for sold listings, so the fetch returns []. Retrying that
# every scan risks getting the whole session challenged, which would break the
# active-listing scrape. After N failed rounds the breaker parks sold lookups.
m.meta_set(conn, "market_circuit", '{"fails": 0, "until": null}')
blocked = {"n": 0}
def _blocked_sold(domain, watch):
    blocked["n"] += 1
    return []                                   # challenge/sign-in page -> no sales
m.fetch_sold_sales = _blocked_sold
cw = {"name": "CB", "require": ["x"], "grades": ["ungraded"]}
for i in range(m.MARKET_FAIL_THRESHOLD):
    m.meta_set(conn, f"market:CB:ungraded", "")   # force a cache miss each round
    m.get_market_prices(conn, "www.ebay.com", cw, ["ungraded"])
ok("breaker attempted up to threshold", blocked["n"] == m.MARKET_FAIL_THRESHOLD)
is_open, _st = m._market_circuit_open(conn, m.datetime.now(m.timezone.utc))
ok("breaker opens after threshold", is_open)
before_n = blocked["n"]
m.meta_set(conn, f"market:CB:ungraded", "")       # cache miss, but breaker is open
res = m.get_market_prices(conn, "www.ebay.com", cw, ["ungraded"])
ok("open breaker skips the network entirely", blocked["n"] == before_n)
ok("open breaker reports no market price", res["ungraded"] is None)

# A successful round resets the breaker.
m.meta_set(conn, "market_circuit", '{"fails": 0, "until": null}')
m.fetch_sold_sales = lambda d, w: [(f"2026-07-{i:02d}", 42.0, "ungraded") for i in range(1, 6)]
m.meta_set(conn, f"market:CB:ungraded", "")
m.get_market_prices(conn, "www.ebay.com", cw, ["ungraded"])
still_open, st2 = m._market_circuit_open(conn, m.datetime.now(m.timezone.utc))
ok("success resets breaker", (not still_open) and int(st2.get("fails", 0)) == 0)

# Negative results are cached briefly (not refetched every scan).
m.fetch_sold_sales = _blocked_sold
m.meta_set(conn, "market_circuit", '{"fails": 0, "until": null}')
m.meta_set(conn, f"market:CB:ungraded", "")
m.get_market_prices(conn, "www.ebay.com", cw, ["ungraded"])
n_after_first = blocked["n"]
m.get_market_prices(conn, "www.ebay.com", cw, ["ungraded"])   # within negative TTL
ok("None result negative-cached (no immediate refetch)", blocked["n"] == n_after_first)

print("== log rotation ==")
import tempfile as _tf
_logdir = _tf.mkdtemp()
m.LOG_PATH = os.path.join(_logdir, "monitor.log")
m.LOG_MAX_BYTES = 100
with open(m.LOG_PATH, "w", encoding="utf-8") as _f:
    _f.write("x" * 250)                                    # over the cap
m._rotate_log_if_large()
ok("large log rotated to .1", os.path.exists(m.LOG_PATH + ".1")
   and not os.path.exists(m.LOG_PATH))
with open(m.LOG_PATH, "w", encoding="utf-8") as _f:
    _f.write("small")                                      # under the cap
m._rotate_log_if_large()
ok("small log not rotated", os.path.exists(m.LOG_PATH))

print("\n==== RESULT ====")
if fails:
    print("FAILURES:", fails)
    sys.exit(1)
print("ALL PASSED")
