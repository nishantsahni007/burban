"""Runs the whole pipeline. One broken source never stops the others.

  python pipeline/run_all.py          # normal daily run
  python pipeline/run_all.py --all    # also refresh the monthly/weekly sources now
"""
import json, os, sys, traceback
from datetime import datetime, timezone

import build, collect_areas, collect_news, collect_places, collect_sitemaps, common

GEO = os.path.join(common.HERE, "geo", "areas.json")


def due(name, argv):
    today = datetime.now(timezone.utc)
    if "--all" in argv:
        return True
    if name == "areas":   # monthly, or whenever the place list is missing
        return not os.path.exists(GEO) or today.day == 1
    if name == "places":  # weekly
        return today.weekday() == 0 or not common.read_evidence("places")["items"]
    return True


def main(argv):
    for name, fn in [("areas", collect_areas.main), ("news", collect_news.main),
                     ("sitemaps", collect_sitemaps.main), ("places", collect_places.main)]:
        if not due(name, argv):
            print(f"{name}: not due today")
            continue
        try:
            fn()
        except Exception:  # noqa: BLE001
            err = traceback.format_exc()
            print(f"{name}: crashed, keeping last good data\n{err}")
            os.makedirs(common.EVIDENCE_DIR, exist_ok=True)
            with open(os.path.join(common.EVIDENCE_DIR, f"{name}.report.json"), "w") as f:
                json.dump({"collector": name, "ran_at": common.now_iso(), "ok": False, "items": 0,
                           "errors": [err.strip().splitlines()[-1]]}, f, indent=1)
        if name == "areas" and not os.path.exists(GEO):
            print("No place list yet; cannot continue.")
            return 1
    build.main()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
