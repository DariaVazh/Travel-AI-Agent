"""Проверка Travelpayouts. Запуск: python check_travelpayouts.py
Токен в вывод НЕ печатается: результат можно присылать."""
from datetime import date, timedelta

import requests

from app import travelpayouts
from app.config import get_secret

token = get_secret("TRAVELPAYOUTS_TOKEN")
print("Токен найден:", bool(token))
if not token:
    raise SystemExit("Добавьте строку TRAVELPAYOUTS_TOKEN=... в файл .env рядом с проектом")

day = (date.today() + timedelta(days=30)).isoformat()
print("Дата:", day)

import time

BASE = {"origin": "LED", "destination": "AER", "departure_at": day, "one_way": "true",
        "currency": "rub", "sorting": "price", "limit": 3}
for title, extra in (("без direct", {}), ("direct=true", {"direct": "true"}), ("direct=false", {"direct": "false"})):
    t = time.perf_counter()
    try:
        r = requests.get(travelpayouts.URL, headers={"X-Access-Token": token}, timeout=(5, 40),
                         params={**BASE, **extra})
        n = len((r.json() or {}).get("data") or []) if r.status_code == 200 else "-"
        print(f"{title:14} HTTP {r.status_code}, вариантов: {n}, {time.perf_counter() - t:.1f} с")
        if title == "без direct":
            print("Сырой ответ (начало):", r.text[:600])
    except Exception as e:
        print(f"{title:14} ОШИБКА {type(e).__name__} через {time.perf_counter() - t:.1f} с")

print("\nЧерез наш провайдер:")
for o in travelpayouts.TravelpayoutsFlights().search("Санкт-Петербург", "Сочи", day, ["plane"], None):
    print(" ", o["carrier"], o["depart"], "->", o["arrive"], f"{o['duration_min']} мин",
          f"пересадок {o['transfers']}", f"{o['price']} ₽")