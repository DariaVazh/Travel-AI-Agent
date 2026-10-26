import json

def _ensure_json(obj):
    json.dumps(obj, ensure_ascii=False)
    return obj


def _norm_leg(o, guests):
    if not o:
        return None
    return {
        "mode": o.get("mode"),
        "carrier": o.get("carrier"),
        "origin": o.get("origin"),
        "destination": o.get("destination"),
        "depart": o.get("depart"),
        "arrive": o.get("arrive"),
        "duration_min": o.get("duration_min"),
        "transfers": o.get("transfers", 0),
        "price_per_person": o.get("price"),
        "currency": o.get("currency", "RUB"),
        "source": o.get("source"),
        "is_mock": bool(o.get("is_mock")),
    }


def _norm_hotel(h):
    if not h:
        return None
    return {
        "name": h.get("name"),
        "stars": h.get("stars"),
        "rating": h.get("rating"),
        "rating_real": bool(h.get("rating_real")),
        "reviews": h.get("reviews"),
        "price_total": h.get("total_price"),
        "price_per_night": h.get("price_per_night"),
        "nights": h.get("nights"),
        "rooms": h.get("rooms", 1),
        "meal": h.get("meal"),
        "pets_allowed": h.get("pets_allowed"),
        "free_cancellation": h.get("free_cancellation"),
        "distance_center_km": h.get("distance_center_km"),
        "checkin_from": h.get("checkin_from"),
        "checkout_until": h.get("checkout_until"),
        "amenities": h.get("amenities", []),
        "currency": h.get("currency", "RUB"),
        "source": h.get("source"),
        "is_mock": bool(h.get("is_mock")),
        "estimated_price": bool(h.get("price_estimated") or h.get("price_source") == "2gis_from"),
    }


def _norm_transfer(t):
    if not t:
        return None
    return {
        "duration_min": t.get("duration_min"),
        "distance_km": t.get("distance_km"),
        "price": t.get("price_estimate"),
        "currency": "RUB",
        "source": t.get("source"),
    }


def _norm_attractiveness(a):
    if not a:
        return None
    return {
        "score": a.get("score"),
        "confidence": a.get("confidence"),
    }


def _norm_package(p, q):
    q = q or {}
    budget = q.get("budget")
    total = p.get("total_price") or 0
    return {
        "id": p["id"],
        "totals": {
            "transport": p.get("transport_total"),
            "hotel": (p.get("hotel") or {}).get("total_price"),
            "transfer": (p.get("transfer") or {}).get("price_estimate"),
            "total": total,
            "currency": "RUB",
            "within_budget": p.get("within_budget"),
            "budget": budget,
            "over_budget_by": max(0, int(total - budget)) if budget else 0,
        },
        "outbound": _norm_leg(p.get("outbound"), q.get("guests", 1)),
        "return": _norm_leg(p.get("return"), q.get("guests", 1)),
        "hotel": _norm_hotel(p.get("hotel")),
        "transfer": _norm_transfer(p.get("transfer")),
        "attractiveness": _norm_attractiveness(p.get("attractiveness")),
        "warnings": p.get("warnings", []),
    }


def to_api(result):
    out = {
        "status": result.get("status"),
        "query": result.get("query"),
        "weather": result.get("weather"),
        "packages": [_norm_package(p, result.get("query")) for p in result.get("packages", [])],
    }
    for k in ("reason", "suggestions", "errors", "missing", "unknown_cities", "unsupported_cities"):
        if k in result:
            out[k] = result[k]
    return _ensure_json(out)


def to_api_cart(cart):
    return _ensure_json({
        "cart_id": cart["cart_id"],
        "package_id": cart["package_id"],
        "items": [
            {
                "type": i["type"],
                "direction": i.get("direction"),
                "title": i["title"],
                "details": i["details"],
                "qty": i["qty"],
                "unit_price": i["unit_price"],
                "price": i["price"],
            } for i in cart["items"]
        ],
        "total": cart["total"],
        "currency": cart["currency"],
        "guests": cart["guests"],
        "matches_package_total": cart["matches_package_total"],
        "requirements": cart["requirements"],
    })


def to_api_checkout(chk):
    return _ensure_json(chk)