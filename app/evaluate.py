"""Метрики качества агента (дополнительная задача кейса). Запуск: python evaluate.py"""
import time
from datetime import date, timedelta

from app.cart import build_cart, mock_checkout
from app.search import plan_trip, replan

d = lambda n: (date.today() + timedelta(days=n)).isoformat()
base = {"origin": "Москва", "destination": "Сочи", "date_from": d(30), "date_to": d(37)}

# (название, запрос, допустимые статусы)
CASES = [
    ("семья с ребёнком, бюджет", {**base, "adults": 2, "children": 1, "budget": 120000}, {"ok"}),
    ("только поезд, в одну сторону", {"origin": "Москва", "destination": "Санкт-Петербург",
                                      "date_from": d(20), "transport": "train"}, {"ok"}),
    ("с собакой", {**base, "pets": True}, {"ok", "no_results"}),
    ("жёсткие условия отеля", {**base, "free_cancellation": True, "hotel_min_stars": 4}, {"ok", "no_results"}),
    ("без пересадок, самолёт", {**base, "transport": "plane", "max_transfers": 0}, {"ok", "no_results"}),
    ("очень маленький бюджет", {**base, "budget": 5000}, {"ok"}),
    ("четверо гостей", {**base, "adults": 3, "children": 1}, {"ok"}),
    ("нет дат", {"origin": "Москва", "destination": "Сочи"}, {"need_info"}),
    ("дата в прошлом", {**base, "date_from": "2020-01-01", "date_to": "2020-01-05"}, {"need_info"}),
    ("откуда = куда", {**base, "origin": "Сочи"}, {"need_info"}),
    ("конец раньше начала", {**base, "date_to": d(10)}, {"need_info"}),
]

print(f"{'сценарий':36} {'статус':10} {'пакетов':8} {'мс':>6}  предупреждений")
ok_cases, times, pkgs, warned = 0, [], 0, 0
for name, q, allowed in CASES:
    t = time.perf_counter()
    r = plan_trip(q)
    ms = (time.perf_counter() - t) * 1000
    n = len(r.get("packages", []))
    w = sum(len(p["warnings"]) for p in r.get("packages", []))
    good = r["status"] in allowed
    ok_cases += good
    if r["status"] == "ok":
        times.append(ms); pkgs += n; warned += sum(1 for p in r["packages"] if p["warnings"])
    print(f"{name:36} {r['status']:10} {n:<8} {ms:6.0f}  {w}  {'' if good else '← НЕ ТО, ЧТО ОЖИДАЛОСЬ'}")

# пересборка и покупка
print("\nПересборка и покупка:")
r = plan_trip({**base, "adults": 2, "budget": 200000})
chosen = r["packages"][0]
checks = {}
r2 = replan(r["query"], {"budget": 90000}, selected=chosen)
checks["бюджет изменён: билеты и отель сохранены"] = set(r2["replan"]["kept"]) == {"outbound", "return", "hotel"}
r3 = replan(r["query"], {"date_from": d(32), "date_to": d(39)}, selected=chosen)
checks["даты сдвинуты: билеты пересобраны"] = {"outbound", "return"} <= set(r3["replan"]["dropped"])
checks["даты сдвинуты: отель сохранён"] = "hotel" in r3["replan"]["kept"]
cart = build_cart(chosen, r["query"])
checks["сумма корзины = сумме пакета"] = cart["matches_package_total"]
checks["покупка без данных отклонена"] = mock_checkout(cart, {})["status"] == "need_info"
checks["покупка с данными подтверждена"] = mock_checkout(cart, {
    "contact_name": "Анна", "contact_phone": "+79991234567",
    "guest_names": ["Анна Иванова", "Пётр Иванов"]})["status"] == "confirmed"
checks["id пакета стабилен между запусками"] = plan_trip({**base, "adults": 2, "budget": 200000})["packages"][0]["id"] == chosen["id"]
for k, v in checks.items():
    print(f"  {'✓' if v else '✗'} {k}")

print("\nИтого:")
print(f"  сценариев обработано как ожидалось: {ok_cases}/{len(CASES)}")
if times:
    print(f"  среднее время до рекомендации: {sum(times) / len(times):.0f} мс")
    print(f"  доля пакетов с предупреждениями о состыковках/рисках: {warned}/{pkgs}")
print(f"  проверок пересборки и покупки пройдено: {sum(checks.values())}/{len(checks)}")
