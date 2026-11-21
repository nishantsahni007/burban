"""Store finder: gets dark stores, gyms and pharmacies from OpenStreetMap (free, open data) and
records the nearest one to each area. "Store within N km" becomes a "likely available" signal.

Runs weekly is plenty; daily is harmless (one query per city).
OpenStreetMap data is (c) OpenStreetMap contributors, ODbL. Credit it in the app.
"""
import json, re, sys, time, urllib.parse

import common

OVERPASS = "https://overpass-api.de/api/interpreter"
fetch = common.http_get  # replaced in tests


def build_query(bbox, patterns):
    s, w, n, e = bbox
    rx = "|".join(p.replace(".", "[.]").replace("\"", "") for p in patterns)
    return (f'[out:json][timeout:90];('
            f'nwr["brand"~"{rx}",i]({s},{w},{n},{e});'
            f'nwr["name"~"{rx}",i]({s},{w},{n},{e});'
            f');out center tags;')


def run(cfg):
    ua = cfg["user_agent"]
    items, errors = [], []
    providers = [p for p in cfg["providers"] if p.get("osm")]
    patterns = sorted({x for p in providers for x in p["osm"]})
    for c in cfg["cities"]:
        if not c.get("live") or not c.get("bbox"):
            continue
        q = build_query(c["bbox"], patterns)
        try:
            raw = fetch(OVERPASS, ua, timeout=120, data=urllib.parse.urlencode({"data": q}).encode())
            elements = json.loads(raw).get("elements", [])
        except Exception as e:  # noqa: BLE001
            errors.append(f"{c['id']}: {e}")
            continue
        stores = []
        for el in elements:
            tags = el.get("tags", {})
            label = " ".join([tags.get("brand", ""), tags.get("name", "")])
            lat = el.get("lat") or (el.get("center") or {}).get("lat")
            lng = el.get("lon") or (el.get("center") or {}).get("lon")
            if lat is None or lng is None:
                continue
            ln = common.norm(label)
            for p in providers:
                if any(common.contains_phrase(ln, x) for x in p["osm"]):
                    stores.append((p["id"], lat, lng, tags.get("name") or tags.get("brand")))
        for a in cfg["areas"]:
            if a["city"] != c["id"]:
                continue
            for p in providers:
                radius = cfg["categories"][p["cat"]]["store_radius_km"]
                if not radius:
                    continue
                best = min(((common.km_between(a["lat"], a["lng"], la, lo), nm, la, lo)
                            for pid, la, lo, nm in stores if pid == p["id"]), default=None)
                if best and best[0] <= radius:
                    items.append({"provider": p["id"], "city": c["id"], "area": a["id"], "signal": "store_nearby",
                                  "km": round(best[0], 1), "store": best[1],
                                  "url": f"https://www.openstreetmap.org/?mlat={best[2]}&mlon={best[3]}#map=17/{best[2]}/{best[3]}"})
        time.sleep(5)
    return items, errors


def main():
    cfg = common.load_config()
    items, errors = run(cfg)
    report = common.write_evidence("places", items, errors)
    print(f"places: {report['items']} items, {len(errors)} errors, ok={report['ok']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
