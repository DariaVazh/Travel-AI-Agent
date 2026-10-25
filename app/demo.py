"""Сквозной сценарий: запрос -> пакеты -> пересборка -> корзина -> 'оплата'."""
import json
from datetime import date, timedelta

from cart import build_cart, mock_checkout
from search import compare_destinations, plan_trip, replan

d = lambda n: (date.today() + timedelta(days=n)).isoformat()

from providers import sources_status

print("Источники данных:")
for k, v in sources_status().items():
    print(f"  {k:11}: {v}")
print()

query = {"origin": "Санкт-Петербург", "destination": "Сочи",
         "date_from": d(30), "date_to": d(37),
         "budget": 120000, "transport": "any", "adults": 2, "children": 1,
         "priority": {"price": 0.6, "time": 0.4}}

print("=== 1. Поиск ===")
res = plan_trip(query)
print(res["text"])
print("Кнопки:", [(b["callback"], b["label"]) for b in res["buttons"]])

print("\n=== 2. Пользователь выбрал первый пакет, потом: 'а если на два дня позже?' ===")
chosen = res["packages"][0]
res2 = replan(res["query"], {"date_from": d(32), "date_to": d(39)}, selected=chosen)
print(res2["text"][:700])
print("replan:", res2["replan"])

print("\n=== 3. 'С нами едет собака' ===")
res3 = replan(res2["query"], {"pets": True}, selected=res2["packages"][0])
print(res3["text"][:300], "\nreplan:", res3["replan"])

print("\n=== 4. Корзина и имитация оплаты ===")
pkg = res3["packages"][0] if res3["packages"] else res2["packages"][0]
q = res3["query"] if res3["packages"] else res2["query"]
cart = build_cart(pkg, q)
print("Корзина:", cart["total"], "₽; сумма совпала с пакетом:", cart["matches_package_total"])
print("Без данных:", mock_checkout(cart, {}))
traveler = {"contact_name": "Анна", "contact_phone": "+7 999 123-45-67",
            "guest_names": ["Анна Иванова", "Пётр Иванов", "Мария Иванова"]}
print("С данными:", json.dumps(mock_checkout(cart, traveler), ensure_ascii=False, indent=2))

print("\n=== 5. Вдохновение: сравнение направлений ===")
print(compare_destinations({k: v for k, v in query.items() if k != "destination"},
                           ["Сочи", "Казань", "Минск", "Дубай", "Париж"])["text"])

print("\n=== 6. Чего не хватает ===")
print(plan_trip({"origin": "Москва"}))
