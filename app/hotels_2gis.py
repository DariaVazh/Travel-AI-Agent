"""РЕАЛЬНЫЕ отели из 2GIS: название, адрес, координаты, рейтинг и число отзывов, звёзды,
«цена от», признаки «Можно с животными» и «Завтрак», удобства (из attribute_groups).
ОЦЕНОЧНЫЕ остаются: итоговая цена за ваши даты (строится от «цены от» 2GIS) и условия отмены.
Список отелей города кэшируется на диск на 7 дней."""
import json
import re
import time
from pathlib import Path

from app import twogis
from app.cities import get_city, haversine_km

CACHE_FILE = Path(__file__).with_name(".hotels_cache_v2.json")
CACHE_TTL = 7 * 24 * 3600
QUERIES = ("отель", "гостиница")          # два запроса, чтобы набрать побольше вариантов
FIELDS = "items.reviews,items.rubrics,items.attribute_groups"
RADIUS_M = 6000
MAX_HOTELS = 15
LODGING_RE = re.compile(r"гостиниц|отел|хостел|апартамент|гостев|санатор|пансионат|база отдыха|кемпинг",
                        re.I)
NOT_AMENITY_RE = re.compile(r"^(цена от|номинант|лучш|\d\s*(звезд|звёзд))", re.I)


def _adjusted_rating(rating, reviews, prior=8.8, weight=30):
    """Рейтинг для сортировки: тянем к среднему тем сильнее, чем меньше отзывов.
    Нет реального рейтинга: нейтральные 8.0 (он не должен выигрывать за счёт случайного числа)."""
    if not rating:
        return 8.0
    n = float(reviews or 0)
    return round((n * rating + weight * prior) / (n + weight), 2)


def _load():
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data):
    try:
        CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _attr_names(it):
    out = []
    for g in it.get("attribute_groups") or []:
        for a in (g.get("attributes") or []) if isinstance(g, dict) else []:
            n = (a or {}).get("name")
            if n:
                out.append(str(n).replace("\xa0", " ").strip())
    return out


def _parse(it):
    """Из ответа 2GIS -> компактный dict. None, если это не жильё."""
    pt = it.get("point") or {}
    if not it.get("id") or "lat" not in pt or "lon" not in pt:
        return None
    rubrics = [r.get("name") for r in it.get("rubrics") or [] if isinstance(r, dict) and r.get("name")]
    if not LODGING_RE.search(" ".join(rubrics + [it.get("name") or ""])):
        return None
    attrs = _attr_names(it)
    low = [a.lower() for a in attrs]
    stars = next((int(m.group(1)) for a in attrs if (m := re.match(r"^(\d)\s*(?:звезд|звёзд)", a, re.I))), 0)
    price_from = next((int(re.sub(r"\D", "", m.group(1))) for a in attrs
                       if (m := re.match(r"^цена от\s*([\d\s]+)", a, re.I)) and re.sub(r"\D", "", m.group(1))), None)
    if any("всё включено" in a or "все включено" in a for a in low):
        meal = "AI"
    elif any(a.startswith("завтрак") for a in low):
        meal = "BB"
    else:
        meal = "RO"
    rv = it.get("reviews") or {}
    try:
        rating = round(float(rv["general_rating"]) * 2, 1)          # у 2GIS шкала 5, у нас 10
    except (KeyError, TypeError, ValueError):
        rating = None
    return {"id": str(it["id"]), "name": it.get("name") or "Без названия",
            "address": it.get("address_name") or "", "lat": pt["lat"], "lon": pt["lon"],
            "stars": stars, "price_from": price_from, "meal": meal,
            "pets": any("животн" in a for a in low), "rating": rating,
            "reviews": rv.get("general_review_count"), "rubrics": rubrics[:3],
            "amenities": [a for a in attrs if not NOT_AMENITY_RE.match(a)][:8]}


class Hotels2GIS:
    name = "2gis"
    is_mock = False
    modes = set()
    authoritative = False

    def _places(self, city):
        cache = _load()
        hit = cache.get(city["name"])
        if hit and time.time() - hit["t"] < CACHE_TTL and hit["items"]:
            return hit["items"]
        c, items, seen = city["center"], [], set()
        for q in QUERIES:
            for it in twogis.search_nearby(q, c["lat"], c["lon"], radius=RADIUS_M, limit=10,
                                           extra_fields=FIELDS):
                p = _parse(it)
                if p and p["id"] not in seen:
                    seen.add(p["id"])
                    items.append(p)
        if items:
            cache[city["name"]] = {"t": time.time(), "items": items}
            _save(cache)
        return items

    def search(self, city_name, check_in, nights, pets):
        city = get_city(city_name)
        if not city or not twogis.KEY:
            return []
        out = []
        for p in self._places(city)[:MAX_HOTELS]:
            if not p["price_from"]:
                continue
            ppn, source = p["price_from"], "2gis_from"
            coords = {"lat": p["lat"], "lon": p["lon"]}
            out.append({
                "id": f"2g-{p['id']}",
                "name": p["name"], "address": p["address"], "city": city["name"],
                "stars": p["stars"], "stars_known": bool(p["stars"]),
                "rating": p["rating"],
                "rating_real": bool(p["rating"]), "reviews": p["reviews"],
                "rating_adj": _adjusted_rating(p["rating"], p["reviews"]),
                "price_per_night": ppn, "price_from": p["price_from"], "price_source": source,
                "price_estimated": False, "nights": nights, "currency": "RUB",
                "meal": p["meal"], "pets_allowed": p["pets"],
                "free_cancellation": None,
                "distance_center_km": max(round(haversine_km(coords, city["center"]), 1), 0.1),
                "checkin_from": "14:00", "checkout_until": "12:00",
                "coords": coords, "rubrics": p["rubrics"], "amenities": p["amenities"],
                "source": self.name, "is_mock": False,
            })
        return out
