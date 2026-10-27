"""Проверка 2GIS. Запуск: python test_twogis.py"""
from app import twogis
from app.transfer import get_transfer

print("Ключ найден:", bool(twogis.KEY))

pt = twogis.geocode("Сочи, аэропорт")
print("Геокодинг:", pt)

if pt:
    hotels = twogis.search_nearby("отель", pt["lat"], pt["lon"], radius=3000, limit=5)
    print(f"Отелей рядом: {len(hotels)}")
    for h in hotels[:3]:
        print("  -", h.get("name"), "|", h.get("address_name"))

airport = {"lat": 43.4499, "lon": 39.9566}
center = {"lat": 43.5855, "lon": 39.7231}
print("Маршрут:", twogis.route(airport, center))
print("Трансфер (через get_transfer):", get_transfer(airport, center))