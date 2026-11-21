"""Emails you (the owner) only when something needs attention or something new launched.
Uses Resend's free tier if RESEND_API_KEY and OWNER_EMAIL are set; otherwise prints to the log.
Quiet days send nothing.
"""
import json, os, sys, urllib.request

import common


def load(name):
    p = os.path.join(common.EVIDENCE_DIR, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def main():
    cfg = common.load_config()
    names = {p["id"]: p["name"] for p in cfg["providers"]}
    areas = {a["id"]: a["name"] for a in cfg["areas"]}
    changes = load("changes.json").get("changes", [])
    health = load("health.json")
    ups = [c for c in changes if c["up"]]
    problems = health.get("problems", [])
    if not ups and not problems:
        print("notify: nothing to report")
        return 0

    lines = []
    if problems:
        lines.append("NEEDS A LOOK")
        lines += [f"- {p}" for p in problems]
        lines.append("")
    if ups:
        lines.append(f"NEW OR UPGRADED ({len(ups)})")
        lines += [f"- {names.get(c['provider'], c['provider'])} in {areas.get(c['area'], c['area'])}: {c['from']} -> {c['to']} ({c['detail']})" for c in ups[:60]]
    downs = len(changes) - len(ups)
    if downs:
        lines.append(f"\n{downs} statuses went down (see pipeline/evidence/changes.json).")
    body = "\n".join(lines)
    subject = ("[Burban] Problem: " if problems else "[Burban] ") + f"{len(ups)} new, {len(problems)} issues"

    key, to = os.environ.get("RESEND_API_KEY"), os.environ.get("OWNER_EMAIL")
    if not key or not to:
        print(f"notify (no email configured):\n{subject}\n{body}")
        return 0
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps({"from": os.environ.get("FROM_EMAIL", "Burban <onboarding@resend.dev>"),
                         "to": [to], "subject": subject, "text": body}).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        print("notify: email sent", r.status)
    return 0


if __name__ == "__main__":
    sys.exit(main())
