"""2GIS API: геокодинг, поиск мест рядом, маршруты.

Устойчивость к сбоям сети: одна сессия (keep-alive), повторы с паузой, небольшой интервал
между запросами и 'предохранитель': после нескольких подряд сбоев на минуту перестаём
обращаться к 2GIS (вызывающий код тогда использует оценку вместо данных API).
"""
import os
import sys
import time
from pathlib import Path

import requests
from app.config import get_secret
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEBUG = True
MIN_INTERVAL = 0.25
MAX_FAILS = 3
BLOCK_SECONDS = 60


def _log(msg):
    if DEBUG:
        print(f"[2gis] {msg}", file=sys.stderr)


KEY = get_secret("TWOGIS_API_KEY")
CATALOG = "https://catalog.api.2gis.com"
ROUTING = "https://routing.api.2gis.com"


def _make_retry():
    kw = dict(total=2, connect=2, read=2, backoff_factor=0.7,
              status_forcelist=(429, 500, 502, 503, 504))
    try:
        return Retry(allowed_methods=None, **kw)
    except TypeError:
        return Retry(method_whitelist=False, **kw)


_session = requests.Session()
_session.mount("https://", HTTPAdapter(max_retries=_make_retry()))
_state = {"fails": 0, "blocked_until": 0.0, "last": 0.0}


def _request(method, url, timeout=10, **kw):
    """Один запрос с защитой от сбоев. Возвращает Response или None."""
    now = time.time()
    if now < _state["blocked_until"]:
        return None
    wait = MIN_INTERVAL - (now - _state["last"])
    if wait > 0:
        time.sleep(wait)
    _state["last"] = time.time()
    try:
        r = _session.request(method, url, timeout=timeout, **kw)
    except Exception as e:
        _state["fails"] += 1
        _log(f"{type(e).__name__}: {str(e)[:150]}")
        if _state["fails"] >= MAX_FAILS:
            _state["blocked_until"] = time.time() + BLOCK_SECONDS
            _state["fails"] = 0
            _log(f"2GIS не отвечает: {BLOCK_SECONDS} с работаем без него "
                 f"(трансфер считается по оценке)")
        return None
    _state["fails"] = 0
    return r


def _get(url, params):
    if not KEY:
        _log("ключ не найден: задайте TWOGIS_API_KEY (переменная окружения или файл .env)")
        return None
    r = _request("GET", url, params={**params, "key": KEY})
    if r is None:
        return None
    try:
        if r.status_code != 200:
            _log(f"HTTP {r.status_code}: {r.text[:300]}")
            return None
        data = r.json()
        code = data.get("meta", {}).get("code")
        if code == 404:
            return None
        if code != 200:
            _log(f"meta.code={code}: {data.get('meta')}")
            return None
        return data
    except Exception as e:
        _log(f"{type(e).__name__}: {e}")
        return None


def geocode(address):
    """Адрес -> {'lat': float, 'lon': float} или None."""
    data = _get(f"{CATALOG}/3.0/items/geocode", {
        "q": address,
        "fields": "items.point",
        "page_size": 1,
    })
    if not data:
        return None
    items = data.get("result", {}).get("items") or []
    if not items:
        _log(f"геокодер ничего не нашёл по запросу '{address}'")
        return None
    pt = items[0].get("point") or {}
    if "lat" in pt and "lon" in pt:
        return {"lat": pt["lat"], "lon": pt["lon"]}
    return None


def search_nearby(query, lat, lon, radius=3000, limit=10, extra_fields=""):
    """Поиск мест рядом с точкой. Возвращает список items или [].
    extra_fields: дополнительные поля через запятую, например 'items.reviews,items.rubrics'."""
    data = _get(f"{CATALOG}/3.0/items", {
        "q": query,
        "point": f"{lon},{lat}",
        "radius": radius,
        "page_size": limit,
        "fields": "items.point,items.address,items.name" + (f",{extra_fields}" if extra_fields else ""),
    })
    if not data:
        return []
    return data.get("result", {}).get("items") or []


def route(start, end, transport="driving"):
    """Маршрут между {'lat','lon'}. Возвращает {'distance_m','duration_s'} или None."""
    if not KEY:
        _log("ключ не найден: задайте TWOGIS_API_KEY (переменная окружения или файл .env)")
        return None
    body = {
        "points": [
            {"type": "stop", "lon": start["lon"], "lat": start["lat"]},
            {"type": "stop", "lon": end["lon"], "lat": end["lat"]},
        ],
        "transport": transport,
    }
    r = _request("POST", f"{ROUTING}/routing/7.0.0/global", timeout=15,
                 params={"key": KEY}, json=body)
    if r is None:
        return None
    try:
        if r.status_code == 204:
            if not _state.get("warned_204"):
                _state["warned_204"] = True
                _log("routing: 204, маршрута нет (город вне покрытия 2GIS или точка не на дороге); "
                     "в таких случаях трансфер считается по оценке")
            return None
        if r.status_code != 200:
            _log(f"routing HTTP {r.status_code}: {r.text[:300]}")
            return None
        data = r.json()
        result = data.get("result")
        # Успешный ответ Routing API: {"result": [...], "type": "result"}; поля "status" нет
        if not result:
            _log(f"routing: пустой result: {str(data)[:300]}")
            return None
        res = result[0]
        return {"distance_m": res.get("total_distance"),
                "duration_s": res.get("total_duration")}
    except Exception as e:
        _log(f"routing {type(e).__name__}: {e}")
        return None
