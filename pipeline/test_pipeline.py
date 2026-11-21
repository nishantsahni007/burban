"""Offline test: runs the whole pipeline on made-up OpenStreetMap, news and sitemap data in a
temporary copy of the project, and checks the results. No internet needed.

  python pipeline/test_pipeline.py
"""
import json, os, shutil, sys, tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CITIES = {"elements": [
    {"type": "node", "id": 1, "lat": 12.9767, "lon": 77.5901, "tags": {"place": "city", "name": "Bengaluru", "population": "8443675", "alt_name": "Bangalore"}},
    {"type": "node", "id": 2, "lat": 19.0760, "lon": 72.8777, "tags": {"place": "city", "name": "Mumbai", "population": "12442373"}},
    {"type": "node", "id": 3, "lat": 13.0707, "lon": 77.7982, "tags": {"place": "town", "name": "Hoskote"}},
    {"type": "node", "id": 4, "lat": 26.9, "lon": 80.9, "tags": {"place": "town", "name": "लखनऊ"}},  # non-Latin, skipped
] + [{"type": "node", "id": 100 + i, "lat": 20 + i * 0.01, "lon": 78, "tags": {"place": "town", "name": f"Testtown{i}"}} for i in range(120)]}
AREAS = {"elements": [
    {"type": "node", "id": 11, "lat": 12.9116, "lon": 77.6474, "tags": {"place": "suburb", "name": "HSR Layout"}},
    {"type": "node", "id": 12, "lat": 12.9352, "lon": 77.6245, "tags": {"place": "suburb", "name": "Koramangala"}},
    {"type": "node", "id": 13, "lat": 12.9698, "lon": 77.7500, "tags": {"place": "suburb", "name": "Whitefield"}},
    {"type": "node", "id": 14, "lat": 12.9784, "lon": 77.6408, "tags": {"place": "suburb", "name": "Indiranagar"}},
    {"type": "node", "id": 15, "lat": 12.9177, "lon": 77.4838, "tags": {"place": "suburb", "name": "Kengeri"}},
    {"type": "node", "id": 21, "lat": 19.1136, "lon": 72.8697, "tags": {"place": "suburb", "name": "Andheri"}},
    {"type": "node", "id": 99, "lat": 30.0, "lon": 90.0, "tags": {"place": "suburb", "name": "Nowhere"}},
]}
STORES = {"elements": [
    {"type": "node", "id": 501, "lat": 12.9140, "lon": 77.6450, "tags": {"name": "Blinkit Dark Store HSR"}},
    {"type": "node", "id": 502, "lat": 12.9700, "lon": 77.6000, "tags": {"name": "Blinkit"}},
    {"type": "way", "id": 503, "center": {"lat": 12.9360, "lon": 77.6260}, "tags": {"brand": "cult.fit", "name": "cult Koramangala"}},
    {"type": "node", "id": 504, "lat": 19.11, "lon": 72.87, "tags": {"name": "Zepto"}},
]}
RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>Snabbit launches in HSR Layout and Koramangala, Bengaluru - Inc42</title>
<link>https://news.example/snabbit-hsr</link><pubDate>Mon, 02 Nov 2026 10:00:00 GMT</pubDate>
<description>Snabbit is now live in HSR Layout</description><source>Inc42</source></item>
<item><title>Pronto set to launch in Whitefield, Bengaluru next month - YourStory</title>
<link>https://news.example/pronto-whitefield</link><pubDate>Tue, 10 Nov 2026 10:00:00 GMT</pubDate><description></description><source>YourStory</source></item>
<item><title>After Bengaluru, Rapido expands to Mumbai</title><link>https://news.example/rapido</link>
<pubDate>Tue, 10 Nov 2026 10:00:00 GMT</pubDate><description></description><source>X</source></item>
</channel></rss>"""
ROBOTS = b"User-agent: *\nDisallow: /api/*\nSitemap: https://www.urbancompany.com/sitemap/sitemap.xml\n"
INDEX = b"""<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://www.urbancompany.com/sitemap/category-sitemap-1.xml</loc></sitemap></sitemapindex>"""
URLSET = b"""<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://www.urbancompany.com/bangalore-professional-home-cleaning-koramangala</loc></url>
<url><loc>https://www.urbancompany.com/bangalore-salon-at-home-hsr-layout</loc></url>
<url><loc>https://www.urbancompany.com/blog/weekend-trips-from-mumbai</loc></url>
<url><loc>https://www.urbancompany.com/bangalore-ac-repair-indiranagar</loc></url></urlset>"""


def fake_overpass(q, ua, timeout=0, label=""):
    if '"place"~' in q:  # every tile returns the same nodes; duplicates must be ignored
        return {"elements": CITIES["elements"] + AREAS["elements"]}
    return STORES


def fake_fetch(url, ua, **kw):
    if "news.google.com" in url:
        return RSS
    if url.endswith("robots.txt"):
        return ROBOTS if "urbancompany" in url else b""
    if url.endswith("/sitemap/sitemap.xml"):
        return INDEX
    if "category-sitemap-1" in url:
        return URLSET
    raise ConnectionError("offline test: " + url)


def main():
    tmp = tempfile.mkdtemp()
    dst = os.path.join(tmp, "app")
    shutil.copytree(SRC, dst, ignore=shutil.ignore_patterns("evidence", "geo", "data", "__pycache__", ".git"))
    cfgp = os.path.join(dst, "pipeline", "config.json")
    cfg = json.load(open(cfgp))
    cfg["canaries"] = [c for c in cfg["canaries"] if c["provider"] == "uc"]  # only UC has fake sitemap data
    json.dump(cfg, open(cfgp, "w"))
    sys.path.insert(0, os.path.join(dst, "pipeline"))
    import common, collect_areas, collect_news, collect_sitemaps, collect_places, build  # noqa: E402
    collect_areas.fetch_overpass = collect_places.fetch_overpass = fake_overpass
    collect_news.fetch = collect_sitemaps.fetch = fake_fetch
    for m in (collect_areas, collect_news, collect_sitemaps, collect_places, common):
        m.time.sleep = lambda s: None
    collect_areas.main(); collect_news.main(); collect_sitemaps.main(); collect_places.main(); build.main()

    D = os.path.join(dst, "data")
    places = json.load(open(os.path.join(D, "places.json")))
    blr = json.load(open(os.path.join(D, "city", "bengaluru.json")))
    health = json.load(open(os.path.join(dst, "pipeline/evidence/health.json")))

    def st(area, prov, city=blr):
        return (city["a"].get(area, {}).get(prov) or city["d"].get(prov) or ["no"])[0]
    area_ids = [a[0] for a in places["a"]]
    checks = [
        ("Cities loaded, non-Latin name skipped", len(places["c"]) == 123),
        ("Big cities listed first", places["c"][0][1] == "Mumbai" and places["c"][1][1] == "Bengaluru"),
        ("Neighbourhoods assigned to their city", "bengaluru-hsr-layout" in area_ids and "mumbai-andheri" in area_ids),
        ("Far-away place dropped", not any("nowhere" in a for a in area_ids)),
        ("Snabbit live in HSR (news names it)", st("bengaluru-hsr-layout", "snabbit") == "live"),
        ("Snabbit likely across Bengaluru (city news)", st("bengaluru-kengeri", "snabbit") == "likely"),
        ("Pronto coming to Whitefield only", st("bengaluru-whitefield", "pronto") == "soon" and st("bengaluru-kengeri", "pronto") == "no"),
        ("'After Bengaluru' not credited to Bengaluru", st("bengaluru-kengeri", "rapido") == "no"),
        ("Urban Company live in Koramangala (official page)", st("bengaluru-koramangala", "uc") == "live"),
        ("Blog page ignored", not any("blog" in str(v) for v in blr["d"].get("uc", []))),
        ("Blinkit likely in HSR (store 0.4 km)", st("bengaluru-hsr-layout", "blinkit") == "likely"),
        ("Blinkit likely city-wide (2 stores in Bengaluru)", st("bengaluru-kengeri", "blinkit") == "likely"),
        ("Zepto live in Andheri via store", st("mumbai-andheri", "zepto", json.load(open(os.path.join(D, "city", "mumbai.json")))) == "likely"),
        ("Town without data has no file", not os.path.exists(os.path.join(D, "city", "hoskote.json"))),
        ("Canaries pass", health["ok"]),
    ]
    # A broken source must not wipe what we knew.
    collect_sitemaps.fetch = lambda *a, **k: (_ for _ in ()).throw(ConnectionError("down"))
    collect_sitemaps.main(); build.main()
    blr2 = json.load(open(os.path.join(D, "city", "bengaluru.json")))
    h2 = json.load(open(os.path.join(dst, "pipeline/evidence/health.json")))
    checks += [("Broken sitemap keeps last good data", st("bengaluru-koramangala", "uc", blr2) == "live"),
               ("Broken sitemap is reported", not h2["ok"])]
    for n, ok in checks:
        print(("PASS " if ok else "FAIL ") + n)
    shutil.rmtree(tmp)
    return 1 if not all(ok for _, ok in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
