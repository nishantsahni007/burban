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


# ---------- pan-India helpers ----------

# Single words too common in English or in place names to count as a match on their own.
STOPWORDS = set("""new old city town nagar colony road market station park garden layout sector block phase
stage extension main central north south east west village temple church airport junction cross circle
bazaar bazar camp cantonment industrial area estate enclave vihar puram pura palli halli hills hill lake
fort port beach river valley central india indian national state district world group service services
home delivery store stores now live launch launches people""".split())
# 4-degree map tiles (south-west corner) that cover part of India; the rest are sea or other countries.
INDIA_TILES = [(6, 76), (6, 92), (10, 72), (10, 76), (10, 92), (14, 72), (14, 76), (14, 80),
               (18, 72), (18, 76), (18, 80), (18, 84), (22, 68), (22, 72), (22, 76), (22, 80), (22, 84),
               (22, 88), (22, 92), (26, 68), (26, 72), (26, 76), (26, 80), (26, 84), (26, 88), (26, 92),
               (26, 96), (30, 72), (30, 76), (30, 80), (34, 72), (34, 76)]
TILE = 4
OVERPASS_URLS = ["https://overpass-api.de/api/interpreter",
                 "https://overpass.private.coffee/api/interpreter",
                 "https://overpass.kumi.systems/api/interpreter"]


def overpass(query, ua, timeout=200, label=""):
    """Run an Overpass query, moving to the next public server if one is slow or refuses.
    Prints one progress line per attempt so the GitHub log shows what is happening."""
    import urllib.parse
    last = None
    for url in OVERPASS_URLS:
        t0 = time.time()
        try:
            raw = http_get(url, ua, timeout=timeout, retries=0, data=urllib.parse.urlencode({"data": query}).encode(),
                           headers={"Accept": "application/json, */*"})
            res = json.loads(raw)
            print(f"  overpass {label} ok via {url.split('/')[2]} in {time.time() - t0:.0f}s, {len(res.get('elements', []))} items", flush=True)
            return res
        except Exception as e:  # noqa: BLE001
            print(f"  overpass {label} failed via {url.split('/')[2]} after {time.time() - t0:.0f}s: {e.__class__.__name__} {str(e)[:80]}", flush=True)
            last = e
    raise last


class PhraseIndex:
    """Find known place names inside a normalised text quickly, by looking up word n-grams."""

    def __init__(self, max_words=4, min_single=5):
        self.map, self.max_words, self.min_single = {}, max_words, min_single

    def add(self, phrase, value):
        p = norm(phrase)
        if not p:
            return
        words = p.split(" ")
        if len(words) > self.max_words:
            return
        if len(words) == 1 and (len(p) < self.min_single or p in STOPWORDS or p.isdigit()):
            return
        self.map.setdefault(p, set()).add(value)

    def find(self, text_norm):
        words = text_norm.split(" ")
        hits = set()
        for i in range(len(words)):
            for n in range(1, self.max_words + 1):
                if i + n > len(words):
                    break
                hit = self.map.get(" ".join(words[i:i + n]))
                if hit:
                    hits |= hit
        return hits


class Grid:
    """Points bucketed in ~5 km cells for fast "what is near here" lookups."""

    def __init__(self, cell=0.05):
        self.cell, self.cells = cell, {}

    def add(self, lat, lng, value):
        self.cells.setdefault((int(lat // self.cell), int(lng // self.cell)), []).append((lat, lng, value))

    def near(self, lat, lng, km):
        r = int(km / (111 * self.cell)) + 1
        ci, cj = int(lat // self.cell), int(lng // self.cell)
        for di in range(-r, r + 1):
            for dj in range(-r, r + 1):
                for la, lo, v in self.cells.get((ci + di, cj + dj), ()):
                    d = km_between(lat, lng, la, lo)
                    if d <= km:
                        yield d, v
