"""Sitemap watcher: reads the public sitemaps providers publish for search engines and looks for
city and neighbourhood pages, e.g. urbancompany.com/bangalore-professional-home-cleaning-hsr-layout.

Follows robots.txt (only fetches what search engines are allowed to fetch). No provider-specific code:
any provider whose sitemap has locality pages is picked up automatically.
"""
import re, sys, time, urllib.parse, urllib.robotparser
import xml.etree.ElementTree as ET

import common

MAX_FILES_PER_SITE = 25
SKIP = re.compile(r"product|blog|recipe|brand|article|image|video|news|press|career|job|faq|offer|coupon|dish|menu|cuisine", re.I)
PREFER = re.compile(r"city|cities|local|locality|area|location|near|categor|store|centre|center|restaurant|service", re.I)
NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
# Pages that merely mention a city (blog posts, articles) are not evidence of service.
SKIP_PAGE = re.compile(r"/(blog|blogs|article|articles|news|press|careers?|jobs?|stories)/", re.I)

fetch = common.http_get  # replaced in tests


def robots_for(base, ua):
    rp = urllib.robotparser.RobotFileParser()
    try:
        rp.parse(fetch(base + "/robots.txt", ua).decode("utf-8", "replace").splitlines())
    except Exception:  # noqa: BLE001 - no robots.txt means everything is allowed
        rp.parse([])
    return rp


def site_urls(domain, ua, errors):
    """Yield every page URL listed in the site's sitemaps (bounded)."""
    base = "https://" + domain
    rp = robots_for(base, ua)
    queue = list(rp.site_maps() or []) or [base + "/sitemap.xml"]
    seen, files = set(), 0
    while queue and files < MAX_FILES_PER_SITE:
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        if not rp.can_fetch(ua, sm):
            continue
        try:
            root = ET.fromstring(fetch(sm, ua))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{domain}: {sm} ({e.__class__.__name__})")
            continue
        files += 1
        tag = root.tag.replace(NS, "")
        locs = [(el.text or "").strip() for el in root.iter(NS + "loc")] or [(el.text or "").strip() for el in root.iter("loc")]
        if tag == "sitemapindex":
            children = [u for u in locs if u and not SKIP.search(u.rsplit("/", 1)[-1])]
            children.sort(key=lambda u: 0 if PREFER.search(u) else 1)
            queue.extend(children)
        else:
            for u in locs:
                if u:
                    yield u
        time.sleep(1.0)


def run(cfg, geo=None):
    import geo as geomod
    g = geo or geomod.Geo(cfg)
    ua = cfg["user_agent"]
    items, errors = [], []
    cache = {}
    for p in cfg["providers"]:
        domain = p.get("sitemap")
        if not domain:
            continue
        if domain not in cache:
            cache[domain] = list(site_urls(domain, ua, errors))
        token = p.get("sitemap_token")
        by_area, by_city = {}, {}
        for u in cache[domain]:
            path = urllib.parse.urlparse(u).path
            if SKIP_PAGE.search(path + "/"):
                continue
            path_n = common.norm(path)
            if token and token not in path_n:
                continue
            for city_id in g.url_cities.find(path_n):
                by_city.setdefault(city_id, []).append(u)
                for area_id in g.area_index(city_id).find(path_n):
                    by_area.setdefault(area_id, []).append(u)
        for city_id, us in by_city.items():
            items.append({"provider": p["id"], "city": city_id, "area": None, "signal": "official_page",
                          "url": sorted(us, key=len)[0], "pages": len(us)})
        for area_id, us in by_area.items():
            items.append({"provider": p["id"], "city": g.area[area_id]["city"], "area": area_id, "signal": "official_page",
                          "url": sorted(us, key=len)[0], "pages": len(us)})
    return items, errors


def main():
    cfg = common.load_config()
    items, errors = run(cfg)
    report = common.write_evidence("sitemaps", items, errors)
    print(f"sitemaps: {report['items']} items, {len(errors)} errors, ok={report['ok']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
