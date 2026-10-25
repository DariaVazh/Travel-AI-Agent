"""Погода через Open-Meteo (клиент openmeteo_requests). Ключ не нужен."""
import atexit
import sys
from datetime import date, timedelta

import requests

import cities


def _warn(where, err):
    """Печатаем причину, почему погоды нет."""
    print(f"[weather] {where}: {type(err).__name__}: {err}", file=sys.stderr)


try:
    import openmeteo_requests
    _client = openmeteo_requests.Client()
except Exception as e:     # библиотека не установлена -> работаем без погоды
    _warn("импорт/создание клиента openmeteo_requests", e)
    _client = None


def _close_client():
    """Удаляем клиент ДО остановки Python, иначе при выходе печатается безобидное
    'Exception ignored in Client.__del__ ... Python is likely shutting down'."""
    global _client
    _client = None


atexit.register(_close_client)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_HORIZON_DAYS = 15     # дальше прогноз не строится

_geo_cache = {}
_weather_cache = {}


def geocode(city):
    """Название города -> (широта, долгота) или None. Сначала наш справочник,
    потом геокодер Open-Meteo (русские названия он находит плохо)."""
    info = cities.get_city(city)
    if info:
        return info["center"]["lat"], info["center"]["lon"]
    if city in _geo_cache:
        return _geo_cache[city]
    coords = None
    for lang in ("ru", "en"):
        try:
            r = requests.get(GEOCODE_URL, params={"name": city, "count": 1, "language": lang}, timeout=10)
            res = r.json().get("results")
            if res:
                coords = (res[0]["latitude"], res[0]["longitude"])
                break
        except Exception as e:
            _warn("геокодер", e)
    _geo_cache[city] = coords
    return coords


def _same_dates_last_year(d):
    try:
        return d.replace(year=d.year - 1)
    except ValueError:                      # 29 февраля
        return d.replace(year=d.year - 1, day=28)


def get_weather(city, date_from, date_to=None):
    """Сводка погоды (dict) или None. Даты в пределах 15 дней -> прогноз,
    иначе берём те же даты прошлого года. Результат кэшируется."""
    ck = (city, date_from, date_to, date.today())
    if ck in _weather_cache:
        return _weather_cache[ck]
    w = _fetch_weather(city, date_from, date_to)
    _weather_cache[ck] = w
    return w


def _fetch_weather(city, date_from, date_to):
    if _client is None:
        return None
    coords = geocode(city)
    if not coords:
        return None
    d1 = date.fromisoformat(date_from)
    d2 = date.fromisoformat(date_to) if date_to else d1

    if d2 <= date.today() + timedelta(days=FORECAST_HORIZON_DAYS):
        url, kind, s, e = FORECAST_URL, "forecast", d1, d2
    else:
        url, kind = ARCHIVE_URL, "last_year"
        s, e = _same_dates_last_year(d1), _same_dates_last_year(d2)

    params = {
        "latitude": coords[0], "longitude": coords[1],
        "start_date": s.isoformat(), "end_date": e.isoformat(),
        "daily": ["temperature_2m_max", "temperature_2m_min", "precipitation_sum"],
        "timezone": "auto",
    }
    try:
        daily = _client.weather_api(url, params=params)[0].Daily()
        tmax = [float(v) for v in daily.Variables(0).ValuesAsNumpy() if v == v]
        tmin = [float(v) for v in daily.Variables(1).ValuesAsNumpy() if v == v]
        rain = [float(v) for v in daily.Variables(2).ValuesAsNumpy() if v == v]
    except Exception as e:
        _warn(f"запрос погоды ({kind})", e)
        return None
    if not tmax:
        _warn(f"запрос погоды ({kind})", "пустой ответ (нет данных за эти даты)")
        return None
    return {
        "kind": kind,                                   # forecast | last_year
        "temp_max_avg": round(sum(tmax) / len(tmax)),
        "temp_min_avg": round(sum(tmin) / len(tmin)) if tmin else None,
        "precip_total_mm": round(sum(rain)),
        "rainy_days": sum(1 for v in rain if v >= 1),
        "days": len(tmax),
        "source": "Open-Meteo",
    }


def weather_text(city, w):
    if not w:
        return ""
    src = "прогноз" if w["kind"] == "forecast" else "по данным прошлого года за те же даты"
    return (f"🌤 Погода в {city} ({src}): днём ~{w['temp_max_avg']}°C, ночью ~{w['temp_min_avg']}°C, "
            f"осадки {w['precip_total_mm']} мм, дождливых дней {w['rainy_days']} из {w['days']}. "
            f"Источник: Open-Meteo.")