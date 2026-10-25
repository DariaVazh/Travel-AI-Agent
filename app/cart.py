"""Корзина и ИМИТАЦИЯ покупки. Реальных списаний нет, данные карты не запрашиваются.
Функции без состояния: пакет целиком передаёт тот, кто достаёт его из БД по id."""
import hashlib
import re

DISCLAIMER = "Демо: оплата имитируется, реальных списаний нет. Данные карты не запрашиваются и не сохраняются."


def build_cart(package, query):
    """package - один элемент result['packages'], query - result['query']. Возвращает корзину."""
    guests = query["guests"]
    o, b, h, tr = package["outbound"], package["return"], package["hotel"], package.get("transfer")
    items = [{"type": "transport", "direction": "outbound",
              "title": f"{o['carrier']}: {o['origin']} → {o['destination']}",
              "details": f"{o['depart'].replace('T', ' ')} → {o['arrive'].replace('T', ' ')}",
              "qty": guests, "unit_price": o["price"], "price": o["price"] * guests}]
    if b:
        items.append({"type": "transport", "direction": "return",
                      "title": f"{b['carrier']}: {b['origin']} → {b['destination']}",
                      "details": f"{b['depart'].replace('T', ' ')} → {b['arrive'].replace('T', ' ')}",
                      "qty": guests, "unit_price": b["price"], "price": b["price"] * guests})
    if h:
        items.append({"type": "hotel", "title": h["name"],
                      "details": f"{h['nights']} ноч., номеров: {h.get('rooms', 1)}",
                      "qty": 1, "unit_price": h["total_price"], "price": h["total_price"]})
    if tr:
        items.append({"type": "transfer", "title": "Трансфер до отеля (оценка)",
                      "details": f"~{tr['duration_min']} мин, {tr['distance_km']} км",
                      "qty": 1, "unit_price": tr["price_estimate"], "price": tr["price_estimate"]})
    total = sum(i["price"] for i in items)
    return {
        "cart_id": "c" + hashlib.sha1(f"{package['id']}|{guests}".encode()).hexdigest()[:8],
        "package_id": package["id"], "items": items, "total": total, "currency": "RUB",
        "guests": guests,
        "matches_package_total": abs(total - package["total_price"]) < 1,   # контроль сумм
        "requirements": {"contact_name": True, "contact_phone": True, "guest_names": guests},
        "disclaimer": DISCLAIMER,
    }


def mock_checkout(cart, traveler):
    """traveler = {'contact_name': str, 'contact_phone': str, 'guest_names': [str, ...]}.
    Паспорта и карты не нужны. В ответ телефон возвращается замаскированным."""
    traveler = traveler or {}
    missing = []
    name = str(traveler.get("contact_name") or "").strip()
    digits = re.sub(r"\D", "", str(traveler.get("contact_phone") or ""))
    guests = traveler.get("guest_names") or []
    if not name:
        missing.append("contact_name")
    if len(digits) < 10:
        missing.append("contact_phone")
    if len([g for g in guests if str(g).strip()]) != cart["guests"]:
        missing.append(f"guest_names (нужно имён: {cart['guests']})")
    if missing:
        return {"status": "need_info", "missing": missing}
    booking = "MOCK-" + hashlib.sha1(f"{cart['cart_id']}|{digits}".encode()).hexdigest()[:8].upper()
    return {"status": "confirmed", "booking_id": booking, "cart_id": cart["cart_id"],
            "total": cart["total"], "currency": cart["currency"],
            "items": [i["title"] for i in cart["items"]],
            "contact": {"name": name, "phone_masked": "+" + "•" * (len(digits) - 2) + digits[-2:]},
            "text": f"Бронь {booking} оформлена (демо). Итого {int(cart['total'])} ₽.",
            "is_mock": True, "disclaimer": DISCLAIMER}
