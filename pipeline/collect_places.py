"""Store finder: every Blinkit/Zepto/Instamart store, gym and pharmacy in India that OpenStreetMap
knows about. build.py turns "a store within N km" into a Live signal for nearby neighbourhoods.

Runs weekly. OpenStreetMap data is (c) OpenStreetMap contributors, ODbL.
"""
import sys, time

import common

LAT, LNG, TILE = (6, 38), (68, 98), 4

fetch_overpass = common.overpass  # replaced in tests


def build_query(patterns, la, lo):
    rx = "|".join(p.replace(".", "[.]").replace('"', "") for p in patterns)
    bb = f"({la},{lo},{la + TILE},{lo + TILE})"
    return ('[out:json][timeout:180];area["ISO3166-1"="IN"][admin_level=2]->.in;('
            f'nwr["brand"~"{rx}",i](area.in){bb};nwr["name"~"{rx}",i](area.in){bb};'
            ');out center tags qt;')


def run(cfg):
    providers = [p for p in cfg["providers"] if p.get("osm")]
    patterns = sorted({x for p in providers for x in p["osm"]})
    elements, errors = [], []
    for la in range(LAT[0], LAT[1], TILE):
        for lo in range(LNG[0], LNG[1], TILE):
            try:
                elements += fetch_overpass(build_query(patterns, la, lo), cfg["user_agent"], timeout=200,
                                           label=f"stores {la},{lo}").get("elements", [])
            except Exception as e:  # noqa: BLE001
                errors.append(f"tile {la},{lo}: {e.__class__.__name__}")
            time.sleep(3)
    items, seen = [], set()
    for el in elements:
        tags = el.get("tags", {})
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lng = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lng is None:
            continue
        label = common.norm(" ".join([tags.get("brand", ""), tags.get("name", "")]))
        for p in providers:
            if any(common.contains_phrase(label, x) for x in p["osm"]) and (p["id"], el["id"]) not in seen:
                seen.add((p["id"], el["id"]))
                items.append({"provider": p["id"], "signal": "store", "lat": round(lat, 5), "lng": round(lng, 5),
                              "store": tags.get("name") or tags.get("brand")})
    return items, errors


def main():
    cfg = common.load_config()
    items, errors = run(cfg)
    report = common.write_evidence("places", items, errors)
    print(f"places: {report['items']} stores, {len(errors)} errors, ok={report['ok']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
