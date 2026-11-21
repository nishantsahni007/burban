"""News monitor: reads Google News RSS search feeds and turns launch headlines into evidence.

Each item: provider, city, area (or null), signal ("news_live" / "news_soon"), title, url, date.
Rules are keyword based (free, no API key). A headline must name the provider AND a city we track.
"""
import re, sys, time, urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import common

FEED = "https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
WINDOW_DAYS = 365

SOON = ["to launch", "will launch", "plans to", "planning to", "set to", "coming soon", "to expand", "to enter",
        "eyes ", "gearing up", "next month", "next quarter", "pilot", "waitlist", "to start operations", "soon in"]
LIVE = ["launches", "launched", "now live", "now available", "expands to", "expanded to", "expands into", "rolls out",
        "rolled out", "enters", "entered", "debuts", "goes live", "went live", "begins operations", "starts operations",
        "starts services", "now in ", "arrives in", "available in"]

fetch = common.http_get  # replaced in tests


def classify(text_norm):
    t = " " + text_norm + " "
    if any(" " + common.norm(w) + " " in t for w in SOON):
        return "news_soon"
    if any(" " + common.norm(w) + " " in t for w in LIVE):
        return "news_live"
    return None


def parse_feed(xml_bytes):
    root = ET.fromstring(xml_bytes)
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        desc = re.sub(r"<[^>]+>", " ", it.findtext("description") or "")
        link = (it.findtext("link") or "").strip()
        src = (it.findtext("source") or "").strip()
        try:
            date = parsedate_to_datetime(it.findtext("pubDate"))
        except (TypeError, ValueError):
            date = None
        yield title, desc, link, src, date


def run(cfg):
    ua = cfg["user_agent"]
    cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
    cities = [c for c in cfg["cities"]]
    areas = cfg["areas"]
    items, errors, seen = [], [], set()

    for p in cfg["providers"]:
        for name in p.get("news", []):
            city_terms = " OR ".join(f'"{c["name"]}"' for c in cities)
            q = f'"{name}" ({city_terms}) (launch OR launches OR launched OR expands OR expansion OR "now live" OR "coming soon")'
            url = FEED.format(q=urllib.parse.quote(q))
            try:
                xml_bytes = fetch(url, ua)
            except Exception as e:  # noqa: BLE001 - a dead feed must not stop the run
                errors.append(f"{p['id']}: {e}")
                continue
            try:
                entries = list(parse_feed(xml_bytes))
            except ET.ParseError as e:
                errors.append(f"{p['id']}: bad feed ({e})")
                continue
            for title, desc, link, src, date in entries:
                if date and date < cutoff:
                    continue
                title_n = common.norm(title)
                if not any(common.contains_phrase(title_n, n) for n in [p["name"]] + p.get("news", [])):
                    continue  # provider must be in the headline itself
                signal = classify(title_n)
                if not signal:
                    continue
                # "After Bengaluru, X expands to Hyderabad" is news about Hyderabad, not Bengaluru.
                full_n = re.sub(r"\b(after|beyond|besides|like) [a-z]+\b", " ", common.norm(title + " " + desc))
                for c in cities:
                    if not any(common.contains_phrase(full_n, a) for a in c["aliases"] + [c["name"]]):
                        continue
                    hit_areas = [a["id"] for a in areas if a["city"] == c["id"]
                                 and any(common.contains_phrase(full_n, al) for al in a["aliases"])]
                    # Live stories also count for the whole city; "coming to Whitefield" should not mark all of Bengaluru.
                    for area_id in hit_areas + ([None] if signal == "news_live" or not hit_areas else []):
                        key = (p["id"], c["id"], area_id, signal, link)
                        if key in seen:
                            continue
                        seen.add(key)
                        items.append({"provider": p["id"], "city": c["id"], "area": area_id, "signal": signal,
                                      "title": title, "source": src, "url": link,
                                      "date": date.strftime("%Y-%m-%d") if date else None})
            time.sleep(1.5)  # be gentle with the feed
    return items, errors


def main():
    cfg = common.load_config()
    items, errors = run(cfg)
    # Feeds only show recent stories, so keep earlier finds until they age out of the window.
    cutoff = (datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    keys = {(i["provider"], i["area"], i["url"]) for i in items}
    for old in common.read_evidence("news")["items"]:
        if (old["provider"], old["area"], old["url"]) not in keys and (old.get("date") or "9999") >= cutoff:
            items.append(old)
    report = common.write_evidence("news", items, errors)
    print(f"news: {report['items']} items, {len(errors)} errors, ok={report['ok']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
