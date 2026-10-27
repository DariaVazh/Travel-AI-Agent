"""Трансфер аэропорт/вокзал -> отель. Время и расстояние берём из 2GIS,
если не получилось (нет ключа, сеть) - грубая оценка, и это честно помечается."""
from app import twogis
from app.cities import haversine_km
_cache = {}


def get_transfer(start, end):
    """start/end: {'lat','lon'}. Возвращает dict или None, если координат нет."""
    if not start or not end:
        return None
    key = (round(start["lat"], 3), round(start["lon"], 3), round(end["lat"], 3), round(end["lon"], 3))
    if key in _cache:
        return _cache[key]

    r = twogis.route(start, end)
    if r and r.get("distance_m") and r.get("duration_s"):
        km, minutes, source = r["distance_m"] / 1000, round(r["duration_s"] / 60), "2GIS"
    else:
        km = haversine_km(start, end) * 1.3  # по прямой + поправка на дороги
        minutes, source = round(km / 40 * 60), "оценка"  # ~40 км/ч
    res = {
        "distance_km": round(km, 1),
        "duration_min": max(minutes, 1),
        "price_estimate": int((300 + 40 * km) / 10) * 10,  # ГРУБАЯ формула такси, не данные API
        "source": source,
    }
    if source == "2GIS":  # оценку не кэшируем: в следующий раз 2GIS может ответить
        _cache[key] = res
    return res