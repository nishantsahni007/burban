"""Merge all evidence into the app's data.json, work out what changed since last time,
and write a health report. Never needs editing: rules live here, inputs live in config.json.

Status per area x provider, strongest wins:
  live    - an official page for this area, or a launch story naming this area
  likely  - a store/centre within range, or the provider is officially in this city
  soon    - a "coming soon / set to launch" story for this area or city
  no      - no sign yet
"""
import json, os, sys
from datetime import datetime, timedelta, timezone

import common

RANK = {"no": 0, "soon": 1, "likely": 2, "live": 3}
DATA_PATH = os.path.join(common.ROOT, "data.json")
CHANGES_PATH = os.path.join(common.EVIDENCE_DIR, "changes.json")
HEALTH_PATH = os.path.join(common.EVIDENCE_DIR, "health.json")
SOON_MAX_DAYS = 240


def month(d):
    try:
        return datetime.strptime(d, "%Y-%m-%d").strftime("%b %Y")
    except (TypeError, ValueError):
        return ""


def judge(ev, area_name, city_name):
    """Pick a status, a one-line reason, and up to 3 evidence links."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    soon_cut = (datetime.now(timezone.utc) - timedelta(days=SOON_MAX_DAYS)).strftime("%Y-%m-%d")
    cands = []  # (status, strength, detail, link-label, url)
    for e in ev:
        sig, local = e["signal"], e["area"] is not None
        if sig == "official_page" and local:
            cands.append(("live", 5, f"Has a page for {area_name}", "Official page", e["url"]))
        elif sig == "news_live" and local:
            cands.append(("live", 4, f"Reported live here · {month(e.get('date'))}".rstrip(" ·"), e.get("source") or "News", e["url"]))
        elif sig == "store_nearby":
            cands.append(("likely", 3, f"Store ~{e['km']} km away", "Map", e["url"]))
        elif sig == "official_page":
            cands.append(("likely", 2, f"Operates in {city_name}; your area not confirmed", "City page", e["url"]))
        elif sig == "news_live":
            cands.append(("likely", 1, f"Live in {city_name} · {month(e.get('date'))}; area not confirmed".replace(" · ;", ";"), e.get("source") or "News", e["url"]))
        elif sig == "news_soon" and (e.get("date") or today) >= soon_cut:
            where = area_name if local else city_name
            cands.append(("soon", 2 if local else 1, f"Reported coming to {where} · {month(e.get('date'))}".rstrip(" ·"), e.get("source") or "News", e["url"]))
    if not cands:
        return {"s": "no"}
    cands.sort(key=lambda c: (RANK[c[0]], c[1]), reverse=True)
    best = cands[0]
    links, seen = [], set()
    for c in cands:
        if c[4] not in seen:
            seen.add(c[4])
            links.append({"t": c[3], "u": c[4]})
        if len(links) == 3:
            break
    return {"s": best[0], "d": best[2], "e": links}


def main():
    cfg = common.load_config()
    sources = {n: common.read_evidence(n) for n in ("news", "sitemaps", "places")}
    evidence = [i for s in sources.values() for i in s["items"]]
    cities = {c["id"]: c for c in cfg["cities"]}
    providers = cfg["providers"]

    status = {}
    for a in cfg["areas"]:
        status[a["id"]] = {}
        for p in providers:
            ev = [e for e in evidence if e["provider"] == p["id"]
                  and (e["area"] == a["id"] or (e["area"] is None and e.get("city") == a["city"]))]
            status[a["id"]][p["id"]] = judge(ev, a["name"], cities[a["city"]]["name"])

    old = {}
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, encoding="utf-8") as f:
            old = json.load(f).get("status", {})

    changes = []
    for aid, row in status.items():
        for pid, cur in row.items():
            prev = (old.get(aid) or {}).get(pid, {}).get("s", "no")
            if prev != cur["s"]:
                changes.append({"area": aid, "provider": pid, "from": prev, "to": cur["s"],
                                "up": RANK[cur["s"]] > RANK[prev], "detail": cur.get("d", "")})

    # Health: broken collectors, and canaries (a provider that must be live in a known area).
    problems = []
    for n in sources:
        rp = os.path.join(common.EVIDENCE_DIR, f"{n}.report.json")
        if os.path.exists(rp):
            with open(rp) as f:
                r = json.load(f)
            if not r["ok"]:
                problems.append(f"{n} collector failed: {'; '.join(r['errors'][:3])}")
            elif r.get("prev_items") and r["items"] < r["prev_items"] * 0.5:
                problems.append(f"{n} found {r['items']} items, down from {r['prev_items']}. A source may have changed: {'; '.join(r['errors'][:2]) or 'no errors reported'}")
    for p in providers:
        canary = p.get("canary")
        if canary and RANK[status.get(canary, {}).get(p["id"], {}).get("s", "no")] < RANK["live"]:
            problems.append(f"Canary failed: {p['name']} should be live in {canary} but isn't. Its source may have changed.")
    big_drop = sum(1 for c in changes if not c["up"])
    if big_drop > 25:
        problems.append(f"{big_drop} statuses went down in one run. That usually means a source broke, not that services left.")

    data = {
        "_generated": "By pipeline/build.py. Don't edit by hand; edit pipeline/config.json instead.",
        "updated": common.now_iso(),
        "sample": False,
        "cities": [{"name": c["name"], "live": c.get("live", False)} for c in cfg["cities"]],
        "services": [{k: p[k] for k in ("id", "name", "cat", "tag", "bg", "fg")} for p in providers],
        "areas": [{k: a[k] for k in ("id", "name", "pin", "city")} | {"city": cities[a["city"]]["name"]} for a in cfg["areas"]],
        "status": status,
    }
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.makedirs(common.EVIDENCE_DIR, exist_ok=True)
    with open(CHANGES_PATH, "w", encoding="utf-8") as f:
        json.dump({"at": data["updated"], "changes": changes}, f, ensure_ascii=False, indent=1)
    with open(HEALTH_PATH, "w", encoding="utf-8") as f:
        json.dump({"at": data["updated"], "ok": not problems, "problems": problems}, f, indent=1)

    counts = {k: sum(1 for r in status.values() for v in r.values() if v["s"] == k) for k in RANK}
    print(f"build: {counts}, {len(changes)} changes, {len(problems)} problems")
    for pr in problems:
        print("  !", pr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
