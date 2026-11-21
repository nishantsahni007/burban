"""Builds the list of every Indian city, town and neighbourhood from OpenStreetMap.

Output: pipeline/geo/cities.json and pipeline/geo/areas.json. Runs monthly (places rarely change).
OpenStreetMap data is (c) OpenStreetMap contributors, ODbL.
"""
import json, os, re, sys, time

import common

GEO_DIR = os.path.join(common.HERE, "geo")
INDIA = 'area["ISO3166-1"="IN"][admin_level=2]->.in;'
ASSIGN_KM = {"city": 30, "town": 12}  # how far a neighbourhood can be from the place it belongs to


def latin(s):
    return bool(s) and re.search(r"[A-Za-z]", s) is not None and not re.search(r"[^\x00-\x7F]", s)


def names(tags):
    """Display name plus every English spelling worth matching."""
    main = tags.get("name:en") if latin(tags.get("name:en")) else tags.get("name")
    if not latin(main):
        return None, []
    al = {main}
    for k in ("name", "name:en", "alt_name", "old_name", "official_name", "short_name", "alt_name:en", "old_name:en"):
        for v in (tags.get(k) or "").split(";"):
            v = v.strip()
            if latin(v):
                al.add(v)
    return main.strip(), sorted(al)


def pop(tags):
    try:
        return int(re.sub(r"[^\d]", "", tags.get("population", "")) or 0)
    except ValueError:
        return 0


fetch_overpass = common.overpass  # replaced in tests


def run(cfg):
    ua = cfg["user_agent"]
    errors = []
    extra = {common.norm(k): v for k, v in cfg.get("city_aliases", {}).items()}

    # One request per tile fetches towns and neighbourhoods together (a country-wide query is too slow).
    started = time.time()
    elements, seen = [], set()
    for la, lo in common.INDIA_TILES:
        if time.time() - started > 60 * 60:
            errors.append("stopped early to stay inside the time limit; the rest comes next month")
            break
        q = (f'[out:json][timeout:180];{INDIA}node["place"~"^(city|town|suburb|neighbourhood|quarter)$"]'
             f'(area.in)({la},{lo},{la + common.TILE},{lo + common.TILE});out body qt;')
        try:
            for el in fetch_overpass(q, ua, timeout=200, label=f"places {la},{lo}").get("elements", []):
                if el["id"] not in seen:
                    seen.add(el["id"]); elements.append(el)
        except Exception as e:  # noqa: BLE001
            errors.append(f"tile {la},{lo}: {e.__class__.__name__}")
        time.sleep(2)
    town_els = [el for el in elements if el.get("tags", {}).get("place") in ("city", "town")]
    hood_els = [el for el in elements if el.get("tags", {}).get("place") in ("suburb", "neighbourhood", "quarter")]
    cities, used = [], set()
    for el in town_els:
        t = el.get("tags", {})
        name, al = names(t)
        if not name:
            continue
        cid = common.slug(name)
        if cid in used:
            st = common.slug(t.get("is_in:state") or t.get("addr:state") or "")
            cid = f"{cid}-{st}" if st and f"{cid}-{st}" not in used else f"{cid}-{el['id']}"
        used.add(cid)
        al = sorted(set(al) | set(extra.get(common.norm(name), [])))
        cities.append({"id": cid, "name": name, "lat": round(el["lat"], 5), "lng": round(el["lon"], 5),
                       "place": t.get("place"), "pop": pop(t), "state": t.get("is_in:state") or t.get("addr:state") or "",
                       "aliases": al})
    print(f"  {len(cities)} cities and towns", flush=True)
    if len(cities) < 100:
        raise RuntimeError(f"only {len(cities)} cities returned; refusing to replace the list")

    grid = common.Grid(cell=0.1)
    for c in cities:
        grid.add(c["lat"], c["lng"], c)

    # Neighbourhoods: attach each to the nearest city or town.
    areas, area_ids = [], set()
    for el in hood_els:
        name, al = names(el.get("tags", {}))
        if not name:
            continue
        best = min(((d, c) for d, c in grid.near(el["lat"], el["lon"], ASSIGN_KM["city"])
                    if d <= ASSIGN_KM.get(c["place"], 12)), default=None, key=lambda x: x[0])
        if not best:
            continue
        city = best[1]
        if common.norm(name) == common.norm(city["name"]):
            continue
        aid = f"{city['id']}-{common.slug(name)}"
        if aid in area_ids:
            continue  # same name twice in one city: keep the first
        area_ids.add(aid)
        areas.append({"id": aid, "name": name, "city": city["id"], "lat": round(el["lat"], 5),
                      "lng": round(el["lon"], 5), "aliases": al})
    print(f"  {len(cities)} cities/towns, {len(areas)} neighbourhoods so far", flush=True)
    return cities, areas, errors


def main():
    cfg = common.load_config()
    os.makedirs(GEO_DIR, exist_ok=True)
    prev_areas = 0
    p = os.path.join(GEO_DIR, "areas.json")
    if os.path.exists(p):
        prev_areas = len(json.load(open(p, encoding="utf-8")))
    cities, areas, errors = run(cfg)
    if prev_areas and len(areas) < prev_areas * 0.7:
        errors.append(f"only {len(areas)} neighbourhoods (was {prev_areas}); kept the old list")
        ok = False
    else:
        for name, rows in (("cities", cities), ("areas", areas)):
            with open(os.path.join(GEO_DIR, f"{name}.json"), "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, separators=(",", ":"))
        ok = True
    os.makedirs(common.EVIDENCE_DIR, exist_ok=True)
    with open(os.path.join(common.EVIDENCE_DIR, "areas.report.json"), "w") as f:
        json.dump({"collector": "areas", "ran_at": common.now_iso(), "ok": ok, "cities": len(cities),
                   "items": len(areas), "errors": errors[:20]}, f, indent=1)
    print(f"areas: {len(cities)} cities/towns, {len(areas)} neighbourhoods, {len(errors)} errors")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
