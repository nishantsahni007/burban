"""Runs the whole pipeline. One broken source never stops the others.

  python pipeline/run_all.py            # everything
  python pipeline/run_all.py --skip places
"""
import json, os, sys, traceback
from datetime import datetime, timezone

import build, collect_news, collect_places, collect_sitemaps, common, notify

WEEKLY = {"places"}  # store locations change slowly; be kind to the free OpenStreetMap servers
STEPS = [("news", collect_news.main), ("sitemaps", collect_sitemaps.main), ("places", collect_places.main)]


def main(argv):
    skip = set(argv[argv.index("--skip") + 1].split(",")) if "--skip" in argv else set()
    for name, fn in STEPS:
        if name in skip:
            print(f"{name}: skipped")
            continue
        if name in WEEKLY and datetime.now(timezone.utc).weekday() != 0 and common.read_evidence(name)["items"] and "--all" not in argv:
            print(f"{name}: weekly source, runs on Mondays")
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
    build.main()
    notify.main()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
