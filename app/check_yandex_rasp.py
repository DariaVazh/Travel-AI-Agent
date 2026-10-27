"""Проверка API Яндекс.Расписаний (поезда). Запуск: python check_yandex_rasp.py
Ключ берётся из .env: YANDEX_RASP_KEY=... (сам ключ в вывод не печатается).
Адреса и параметры написаны по документации Яндекса по памяти: если придёт 400/404,
пришлите вывод целиком, подстрою."""
from datetime import date, timedelta

import requests

from app.cities import get_city
from app.config import get_secret

BASE = "https://api.rasp.yandex.net/v3.0"
key = get_secret("YANDEX_RASP_KEY")
print("Ключ найден:", bool(key))
if not key:
    raise SystemExit("Добавьте строку YANDEX_RASP_KEY=... в файл .env")


def call(path, **params):
    r = requests.get(f"{BASE}/{path}/", params={"apikey": key, "format": "json", "lang": "ru_RU", **params},
                     timeout=15)
    print(f"  {path}: HTTP {r.status_code}")
    return r


codes = {}
print("1) Коды городов по координатам центра")
for name in ("Санкт-Петербург", "Москва"):
    c = get_city(name)["center"]
    r = call("nearest_settlement", lat=c["lat"], lng=c["lon"], distance=50)
    print("  ", name, "->", r.text[:300])
    try:
        codes[name] = r.json().get("code")
    except Exception:
        pass

if len(codes) == 2 and all(codes.values()):
    day = (date.today() + timedelta(days=10)).isoformat()
    print(f"\n2) Поезда {day}: {codes['Санкт-Петербург']} -> {codes['Москва']}")
    r = call("search", **{"from": codes["Санкт-Петербург"], "to": codes["Москва"], "date": day,
                          "transport_types": "train", "limit": 3})
    print("  Сырой ответ (начало):", r.text[:2500])
    try:
        segs = r.json().get("segments", [])
        print(f"\n  Найдено рейсов: {len(segs)}; с ценой в tickets_info (places не пуст): "
              f"{sum(1 for s in segs if (s.get('tickets_info') or {}).get('places'))} из {len(segs)}")
    except Exception:
        pass
