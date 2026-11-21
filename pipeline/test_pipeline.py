"""Offline test: runs the whole pipeline against made-up feeds, sitemaps and map data, in a
temporary copy of the project, and checks the results. No internet needed.

  python pipeline/test_pipeline.py
"""
import json, os, shutil, sys, tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>Snabbit launches in HSR Layout and Koramangala, Bengaluru - Inc42</title>
<link>https://news.example/snabbit-hsr</link><pubDate>Mon, 02 Nov 2026 10:00:00 GMT</pubDate>
<description>Snabbit is now live in HSR Layout</description><source>Inc42</source></item>
<item><title>Pronto set to launch in Whitefield, Bengaluru next month - YourStory</title>
<link>https://news.example/pronto-whitefield</link><pubDate>Tue, 10 Nov 2026 10:00:00 GMT</pubDate>
<description></description><source>YourStory</source></item>
<item><title>Rapido raises funding</title><link>https://news.example/rapido</link>
<pubDate>Tue, 10 Nov 2026 10:00:00 GMT</pubDate><description>Bengaluru</description><source>X</source></item>
</channel></rss>"""

ROBOTS = b"User-agent: *\nDisallow: /api/*\nSitemap: https://www.urbancompany.com/sitemap/sitemap.xml\n"
INDEX = b"""<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://www.urbancompany.com/sitemap/category-sitemap-1.xml</loc></sitemap>
<sitemap><loc>https://www.urbancompany.com/sitemap/blog-sitemap.xml</loc></sitemap></sitemapindex>"""
URLSET = b"""<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://www.urbancompany.com/bangalore-professional-home-cleaning-koramangala</loc></url>
<url><loc>https://www.urbancompany.com/bangalore-professional-home-cleaning-hsr-layout</loc></url>
<url><loc>https://www.urbancompany.com/bangalore-salon-at-home-whitefield</loc></url>
<url><loc>https://www.urbancompany.com/mumbai-salon-at-home-andheri</loc></url></urlset>"""
OVERPASS = json.dumps({"elements": [
    {"type": "node", "lat": 12.9140, "lon": 77.6450, "tags": {"name": "Blinkit Dark Store HSR"}},
    {"type": "way", "center": {"lat": 12.9360, "lon": 77.6260}, "tags": {"brand": "cult.fit", "name": "cult Koramangala"}},
    {"type": "node", "lat": 13.30, "lon": 77.80, "tags": {"name": "Zepto"}},
]}).encode()


def fake_fetch(url, ua, **kw):
    if "news.google.com" in url:
        return RSS if "Snabbit" in url or "Pronto" in url or "Rapido" in url else b"<rss><channel></channel></rss>"
    if url.endswith("robots.txt"):
        return ROBOTS if "urbancompany" in url else b""
    if url.endswith("/sitemap/sitemap.xml"):
        return INDEX
    if "category-sitemap-1" in url:
        return URLSET
    if "overpass" in url:
        return OVERPASS
    raise ConnectionError("offline test: " + url)


def main():
    tmp = tempfile.mkdtemp()
    dst = os.path.join(tmp, "app")
    shutil.copytree(SRC, dst, ignore=shutil.ignore_patterns("evidence", "__pycache__"))
    if os.path.exists(os.path.join(dst, "data.json")):
        os.remove(os.path.join(dst, "data.json"))
    sys.path.insert(0, os.path.join(dst, "pipeline"))
    import common, collect_news, collect_sitemaps, collect_places, build  # noqa: E402
    for m in (collect_news, collect_sitemaps, collect_places):
        m.fetch = fake_fetch
    collect_news.time.sleep = collect_sitemaps.time.sleep = collect_places.time.sleep = lambda s: None
    collect_news.main(); collect_sitemaps.main(); collect_places.main(); build.main()

    data = json.load(open(os.path.join(dst, "data.json")))
    st = data["status"]
    checks = [
        ("Snabbit live in HSR (news names the area)", st["hsr"]["snabbit"]["s"] == "live"),
        ("Snabbit likely in Jayanagar (city-level news only)", st["jayanagar"]["snabbit"]["s"] == "likely"),
        ("Pronto coming soon to Whitefield", st["whitefield"]["pronto"]["s"] == "soon"),
        ("Rapido funding story ignored", st["hsr"]["rapido"]["s"] == "no"),
        ("Urban Company live in Koramangala (official page)", st["koramangala"]["uc"]["s"] == "live"),
        ("Urban Company likely in Yelahanka (city page only)", st["yelahanka"]["uc"]["s"] == "likely"),
        ("Blinkit likely in HSR (store 0.4 km)", st["hsr"]["blinkit"]["s"] == "likely" and "km" in st["hsr"]["blinkit"]["d"]),
        ("Blinkit not in Kengeri (store too far)", st["kengeri"]["blinkit"]["s"] == "no"),
        ("cult.fit likely in Koramangala", st["koramangala"]["cult"]["s"] == "likely"),
        ("Zepto store outside radius ignored", st["devanahalli"]["zepto"]["s"] == "no"),
        ("Evidence links attached", st["hsr"]["snabbit"]["e"][0]["u"].startswith("https://")),
        ("Canary passes", json.load(open(os.path.join(dst, "pipeline/evidence/health.json")))["ok"]),
    ]
    # A broken source must not wipe what we knew: rerun sitemaps with everything failing.
    collect_sitemaps.fetch = lambda *a, **k: (_ for _ in ()).throw(ConnectionError("down"))
    collect_sitemaps.main(); build.main()
    st2 = json.load(open(os.path.join(dst, "data.json")))["status"]
    health = json.load(open(os.path.join(dst, "pipeline/evidence/health.json")))
    checks += [
        ("Broken sitemap keeps last good data", st2["koramangala"]["uc"]["s"] == "live"),
        ("Broken sitemap is reported", not health["ok"]),
    ]
    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(("PASS " if ok else "FAIL ") + n)
    shutil.rmtree(tmp)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
