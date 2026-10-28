"""Какие данные об отелях реально отдаёт ваш ключ 2GIS. Запуск: python check_2gis_hotels.py
Скрипт по очереди пробует дополнительные поля Places API и показывает, какие из них доступны,
а потом печатает сводку по первым отелям. Ключ и контакты (телефоны) в вывод не попадают,
результат можно присылать целиком."""
import json
import re

from app import twogis
from app.cities import get_city

if not twogis.KEY:
    raise SystemExit("Ключ 2GIS не найден: проверьте TWOGIS_API_KEY в .env")

CITY = "Сочи"
c = get_city(CITY)["center"]
URL = f"{twogis.CATALOG}/3.0/items"
BASE = {"q": "отель", "point": f"{c['lon']},{c['lat']}", "radius": 5000, "page_size": 5}

# поле запроса -> ключ в ответе
CANDIDATES = {
    "items.reviews": "reviews",                 # рейтинг и число отзывов
    "items.rubrics": "rubrics",                 # рубрики: гостиница, хостел, апартаменты...
    "items.attribute_groups": "attribute_groups",  # удобства и признаки (парковка, Wi-Fi...)
    "items.description": "description",
    "items.schedule": "schedule",
    "items.adm_div": "adm_div",
    "items.org": "org",
    "items.name_ex": "name_ex",
    "items.flags": "flags",
    "items.links": "links",
    "items.external_content": "external_content",
}


def call(fields):
    r = twogis._request("GET", URL, params={**BASE, "fields": fields, "key": twogis.KEY})
    if r is None:
        return None, "нет ответа (сеть или пауза после сбоев)", []
    try:
        js = r.json()
    except Exception:
        return r.status_code, f"не JSON: {r.text[:120]}", []
    meta = js.get("meta") or {}
    if r.status_code != 200 or meta.get("code") != 200:
        err = (meta.get("error") or {}).get("message") or js.get("error") or r.text[:150]
        return r.status_code, f"код {meta.get('code')}: {err}", []
    return 200, "", (js.get("result") or {}).get("items") or []


print(f"Город: {CITY}. Проверяем поля Places API по одному.\n")
allowed = []
for field, key in CANDIDATES.items():
    status, err, items = call(f"items.point,{field}")
    if status != 200:
        print(f"  ✗ {field:28} отказ: HTTP {status}, {err}")
    elif any(key in it for it in items):
        print(f"  ✓ {field:28} доступно (есть у {sum(1 for it in items if key in it)} из {len(items)})")
        allowed.append(field)
    else:
        print(f"  ~ {field:28} принято, но в ответе пусто")

fields = ",".join(["items.point", "items.address"] + allowed)
status, err, items = call(fields)
print(f"\nИтоговый запрос ({len(allowed)} доп. полей): HTTP {status} {err}")
print(f"Найдено объектов по запросу «отель»: {len(items)}\n")

HOTEL_RE = re.compile(r"гостиниц|отел|хостел|апартамент|гостев|мини-отел|санатор|пансионат|база отдыха", re.I)


def names(lst, key="name"):
    return [x.get(key) for x in lst or [] if isinstance(x, dict) and x.get(key)]


for it in items[:5]:
    rub = names(it.get("rubrics"))
    reviews = it.get("reviews") or {}
    groups = it.get("attribute_groups") or []
    attrs = []
    for g in groups:
        attrs += names(g.get("attributes") if isinstance(g, dict) else [], "name")
    print(f"• {it.get('name')} | {it.get('address_name')}")
    print(f"    рубрики: {rub[:4]}")
    print(f"    рейтинг: {reviews.get('general_rating')} (отзывов: {reviews.get('general_review_count')})")
    print(f"    удобства/признаки: {attrs[:8]}")
    print(f"    описание: {bool(it.get('description'))} | расписание: {bool(it.get('schedule'))}")

hotels = [it for it in items if HOTEL_RE.search(" ".join(names(it.get("rubrics")) + [it.get("name") or ""]))]
print(f"\nПохожи на жильё (по рубрикам и названию): {len(hotels)} из {len(items)}")
all_attrs = []
for it in items:
    for g in it.get("attribute_groups") or []:
        for a in (g.get("attributes") or []) if isinstance(g, dict) else []:
            all_attrs.append(str(a.get("name", "")).replace("\xa0", " ").lower())
has = lambda *words: any(any(w in a for w in words) for a in all_attrs)
print("\nЧто есть в признаках 2GIS (по найденным отелям):")
print("  рейтинг и отзывы  :", "да (reviews)" if "items.reviews" in allowed else "нет")
print("  звёзды            :", "да" if has("звезд", "звёзд") else "не встретились")
print("  «цена от»         :", "да" if has("цена от") else "не встретилась")
print("  можно с животными :", "да" if has("животн") else "не встретилось")
print("  завтрак / питание :", "да" if has("завтрак", "всё включено", "все включено") else "не встретилось")
print("  условия отмены    : в 2GIS нет, остаются оценочными")
