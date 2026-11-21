"""Loads the pan-India place list made by collect_areas.py and builds fast name lookups."""
import json, os

import common

GEO_DIR = os.path.join(common.HERE, "geo")


class Geo:
    def __init__(self, cfg=None):
        cfg = cfg or common.load_config()
        with open(os.path.join(GEO_DIR, "cities.json"), encoding="utf-8") as f:
            self.cities = json.load(f)
        with open(os.path.join(GEO_DIR, "areas.json"), encoding="utf-8") as f:
            self.areas = json.load(f)
        self.city = {c["id"]: c for c in self.cities}
        self.area = {a["id"]: a for a in self.areas}
        self.areas_in = {}
        for a in self.areas:
            self.areas_in.setdefault(a["city"], []).append(a)
        big = cfg.get("news_min_population", 100000)
        # News text is noisy: only match cities (and large towns). URLs are precise: match every town.
        self.news_cities, self.url_cities = common.PhraseIndex(), common.PhraseIndex()
        for c in self.cities:
            for al in c["aliases"]:
                self.url_cities.add(al, c["id"])
                if c["place"] == "city" or c["pop"] >= big:
                    self.news_cities.add(al, c["id"])
        self._area_idx = {}

    def area_index(self, city_id):
        if city_id not in self._area_idx:
            idx = common.PhraseIndex(min_single=5)
            for a in self.areas_in.get(city_id, []):
                for al in a["aliases"]:
                    idx.add(al, a["id"])
            self._area_idx[city_id] = idx
        return self._area_idx[city_id]
