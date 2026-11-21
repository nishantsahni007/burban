"""Turns all evidence into the app's data files, split per city so the app stays fast:

  data/index.json        services, last update, totals
  data/places.json       every city/town and neighbourhood (for search and "use my location")
  data/city/<id>.json    statuses: a default for the whole city + overrides for specific neighbourhoods

Status rules (the app shows live+likely as "Live" and soon+no as "Not available"):
  live    official page for this neighbourhood, or a launch story naming it
  likely  a store within range, several stores in the city, or the provider officially in the city
  soon    a "coming soon" story for this neighbourhood or city
  no      nothing found
"""
import json, os, shutil, sys
from datetime import datetime, timedelta, timezone

import common, geo as geomod

RANK = {"no": 0, "soon": 1, "likely": 2, "live": 3}
GROUP_LIVE = {"live", "likely"}
DATA_DIR = os.path.join(common.ROOT, "data")
SOON_MAX_DAYS = 240
CITY_STORE_KM = {"city": 15, "town": 6}


def month(d):
    try:
        return datetime.strptime(d, "%Y-%m-%d").strftime("%b %Y")
    except (TypeError, ValueError):
        return ""


def candidates(ev, place_name, city_name):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    soon_cut = (datetime.now(timezone.utc) - timedelta(days=SOON_MAX_DAYS)).strftime("%Y-%m-%d")
    out = []  # (status, strength, detail, link label, url)
    for e in ev:
        sig, local = e["signal"], e.get("area") is not None
        if sig == "official_page" and local:
            out.append(("live", 5, f"Has a page for {place_name}", "Official page", e["url"]))
        elif sig == "news_live" and local:
            out.append(("live", 4, f"Reported live here · {month(e.get('date'))}".rstrip(" ·"), e.get("source") or "News", e["url"]))
        elif sig == "store_near":
            out.append(("likely", 3, f"Store ~{e['km']} km away", "Map", e["url"]))
        elif sig == "stores_in_city":
            out.append(("likely", 2, f"{e['n']} stores in {city_name}", "Map", e["url"]))
        elif sig == "official_page":
            out.append(("likely", 2, f"Operates in {city_name}", "City page", e["url"]))
        elif sig == "news_live":
            out.append(("likely", 1, f"Live in {city_name} · {month(e.get('date'))}".rstrip(" ·"), e.get("source") or "News", e["url"]))
        elif sig == "news_soon" and (e.get("date") or today) >= soon_cut:
            out.append(("soon", 2 if local else 1, f"Reported coming to {place_name if local else city_name} · {month(e.get('date'))}".rstrip(" ·"),
                        e.get("source") or "News", e["url"]))
    return out


def pick(cands):
    if not cands:
        return None
    cands = sorted(cands, key=lambda c: (RANK[c[0]], c[1]), reverse=True)
    links, seen = [], set()
    for c in cands:
        if c[4] and c[4] not in seen and c[4].startswith("http"):
            seen.add(c[4])
            links.append([c[3], c[4]])
        if len(links) == 3:
            break
    return [cands[0][0], cands[0][2], links]


def osm_link(lat, lng):
    return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lng}#map=16/{lat}/{lng}"


def main():
    cfg = common.load_config()
    g = geomod.Geo(cfg)
    providers = cfg["providers"]
    pcat = {p["id"]: p["cat"] for p in providers}
    radius = {k: v["store_radius_km"] for k, v in cfg["categories"].items()}
    sources = {n: common.read_evidence(n) for n in ("news", "sitemaps", "places")}

    # Evidence by (provider, city) and (provider, area); "area" may be a town's own id (its centre).
    by_city, by_area = {}, {}
    for n in ("news", "sitemaps"):
        for e in sources[n]["items"]:
            if e.get("city") not in g.city:
                continue
            if e.get("area"):
                by_area.setdefault((e["provider"], e["area"]), []).append(e)
            else:
                by_city.setdefault((e["provider"], e["city"]), []).append(e)

    # Stores -> nearest store per neighbourhood (and per town centre), plus store counts per city.
    pts = common.Grid(cell=0.05)
    for a in g.areas:
        pts.add(a["lat"], a["lng"], a["id"])
    for c in g.cities:
        pts.add(c["lat"], c["lng"], c["id"])
    city_pts = common.Grid(cell=0.1)
    for c in g.cities:
        city_pts.add(c["lat"], c["lng"], c["id"])
    nearest, city_stores = {}, {}
    for s in sources["places"]["items"]:
        r = radius.get(pcat.get(s["provider"]), 0)
        if not r:
            continue
        for d, pid in pts.near(s["lat"], s["lng"], r):
            k = (s["provider"], pid)
            if k not in nearest or d < nearest[k][0]:
                nearest[k] = (d, s)
        for d, cid in city_pts.near(s["lat"], s["lng"], 15):
            if d <= CITY_STORE_KM.get(g.city[cid]["place"], 6):
                city_stores.setdefault((s["provider"], cid), []).append(s)
    for (prov, pid), (d, s) in nearest.items():
        by_area.setdefault((prov, pid), []).append({"signal": "store_near", "area": pid, "km": round(d, 1),
                                                    "url": osm_link(s["lat"], s["lng"])})
    for (prov, cid), ss in city_stores.items():
        if len(ss) >= 2:
            by_city.setdefault((prov, cid), []).append({"signal": "stores_in_city", "n": len(ss),
                                                        "url": osm_link(ss[0]["lat"], ss[0]["lng"])})

    # Write per-city files: default for the city + neighbourhood overrides that say something more.
    if os.path.isdir(DATA_DIR):
        old_index = json.load(open(os.path.join(DATA_DIR, "index.json"))) if os.path.exists(os.path.join(DATA_DIR, "index.json")) else {}
        shutil.rmtree(os.path.join(DATA_DIR, "city"), ignore_errors=True)
    else:
        old_index = {}
    os.makedirs(os.path.join(DATA_DIR, "city"), exist_ok=True)
    has_data, live_pairs = set(), 0
    status_of = {}  # (provider, place id) -> status, for canaries
    for c in g.cities:
        default, overrides = {}, {}
        for p in providers:
            v = pick(candidates(by_city.get((p["id"], c["id"]), []), c["name"], c["name"]))
            if v:
                default[p["id"]] = v
        places = [(c["id"], c["name"])] + [(a["id"], a["name"]) for a in g.areas_in.get(c["id"], [])]
        for pid, pname in places:
            row = {}
            for p in providers:
                local = candidates(by_area.get((p["id"], pid), []), pname, c["name"])
                if not local:
                    continue
                v = pick(local + candidates(by_city.get((p["id"], c["id"]), []), pname, c["name"]))
                if v != default.get(p["id"]):
                    row[p["id"]] = v
            if row:
                overrides[pid] = row
            for p in providers:
                st = (row.get(p["id"]) or default.get(p["id"]) or ["no"])[0]
                status_of[(p["id"], pid)] = st
                live_pairs += st in GROUP_LIVE
        if default or overrides:
            has_data.add(c["id"])
            with open(os.path.join(DATA_DIR, "city", f"{c['id']}.json"), "w", encoding="utf-8") as f:
                json.dump({"d": default, "a": overrides}, f, ensure_ascii=False, separators=(",", ":"))

    # Places list for search and "use my location". Big cities first so search shows them first.
    order = sorted(g.cities, key=lambda c: (c["place"] != "city", -c["pop"], c["name"]))
    cidx = {c["id"]: i for i, c in enumerate(order)}
    places = {"c": [[c["id"], c["name"], c["state"], round(c["lat"], 3), round(c["lng"], 3), int(c["id"] in has_data),
                     1 if c["place"] == "city" else 0] for c in order],
              "a": [[a["id"], a["name"], cidx[a["city"]], round(a["lat"], 3), round(a["lng"], 3)] for a in g.areas]}
    with open(os.path.join(DATA_DIR, "places.json"), "w", encoding="utf-8") as f:
        json.dump(places, f, ensure_ascii=False, separators=(",", ":"))

    index = {"updated": common.now_iso(),
             "services": [{k: p[k] for k in ("id", "name", "cat", "tag", "bg", "fg", "android", "ios", "store_q") if p.get(k)} for p in providers],
             "stats": {"cities": len(g.cities), "areas": len(g.areas), "cities_with_data": len(has_data), "live_pairs": live_pairs}}
    with open(os.path.join(DATA_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))

    # Health: broken collectors, canaries, big drops.
    problems = []
    for n in ("news", "sitemaps", "places", "areas"):
        rp = os.path.join(common.EVIDENCE_DIR, f"{n}.report.json")
        if os.path.exists(rp):
            r = json.load(open(rp))
            if not r["ok"]:
                problems.append(f"{n} collector failed: {'; '.join(r['errors'][:3])}")
            elif r.get("prev_items") and r["items"] < r["prev_items"] * 0.5:
                problems.append(f"{n} found {r['items']} items, down from {r['prev_items']}: {'; '.join(r['errors'][:2]) or 'no errors reported'}")
    for cn in cfg.get("canaries", []):
        city = next((c for c in g.cities if common.norm(cn["city"]) in {common.norm(x) for x in c["aliases"]}), None)
        area = next((a for a in g.areas_in.get(city["id"], []) if common.norm(cn["area"]) in {common.norm(x) for x in a["aliases"]}), None) if city else None
        place = area or city
        if not place or status_of.get((cn["provider"], place["id"])) not in GROUP_LIVE:
            problems.append(f"Canary failed: {cn['provider']} should be Live in {cn['area']}, {cn['city']}. Its source may have changed.")
    prev_live = (old_index.get("stats") or {}).get("live_pairs")
    if prev_live and live_pairs < prev_live * 0.7:
        problems.append(f"Live results fell from {prev_live} to {live_pairs} in one run; a source probably broke.")
    os.makedirs(common.EVIDENCE_DIR, exist_ok=True)
    with open(os.path.join(common.EVIDENCE_DIR, "health.json"), "w") as f:
        json.dump({"at": index["updated"], "ok": not problems, "problems": problems, "stats": index["stats"]}, f, indent=1)
    print(f"build: {index['stats']}, {len(problems)} problems")
    for pr in problems:
        print("  !", pr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
