"""Shared helpers for the Burban data pipeline. Standard library only."""
import gzip, json, math, os, re, time, urllib.request, urllib.error
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
EVIDENCE_DIR = os.path.join(HERE, "evidence")
ROOT = os.path.dirname(HERE)


def load_config():
    with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def http_get(url, ua, timeout=30, retries=2, data=None, headers=None):
    """GET (or POST when data is given) with a polite pause and retries. Returns bytes."""
    last = None
    for attempt in range(retries + 1):
        try:
            h = {"User-Agent": ua, "Accept-Encoding": "gzip"}
            h.update(headers or {})
            req = urllib.request.Request(url, data=data, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
                if r.headers.get("Content-Encoding") == "gzip" or url.endswith(".gz") or body[:2] == b"\x1f\x8b":
                    try:
                        body = gzip.decompress(body)
                    except OSError:
                        pass
                return body
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise last


def norm(text):
    """Lowercase, turn punctuation into spaces, collapse spaces."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (text or "").lower())).strip()


def slug(text):
    return norm(text).replace(" ", "-")


def contains_phrase(haystack_norm, phrase):
    """True when the normalised phrase appears as whole words."""
    p = norm(phrase)
    return bool(p) and re.search(r"(^| )" + re.escape(p) + r"( |$)", haystack_norm) is not None


def km_between(lat1, lng1, lat2, lng2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def write_evidence(name, items, errors, extra=None):
    """Save a collector's output. A run with zero items and errors does NOT overwrite the
    last good file, so a broken source never wipes out what we knew."""
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    path = os.path.join(EVIDENCE_DIR, f"{name}.json")
    ok = bool(items) or not errors
    prev = 0
    rp = os.path.join(EVIDENCE_DIR, f"{name}.report.json")
    if os.path.exists(rp):
        with open(rp, encoding="utf-8") as f:
            prev = json.load(f).get("items", 0) or 0
    report = {"collector": name, "ran_at": now_iso(), "ok": ok, "items": len(items), "prev_items": prev,
              "errors": errors[:20]}
    if ok:
        payload = {"collected_at": now_iso(), "items": items}
        payload.update(extra or {})
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
    with open(os.path.join(EVIDENCE_DIR, f"{name}.report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    return report


def read_evidence(name):
    path = os.path.join(EVIDENCE_DIR, f"{name}.json")
    if not os.path.exists(path):
        return {"collected_at": None, "items": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)
