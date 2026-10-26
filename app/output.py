def _human_dur(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    return f"{h} ч {m:02d} мин" if h else f"{m} мин"


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
        "duration_human": _human_dur(o.get("duration_min", 0)),
        "transfers": o.get("transfers", 0),
        "price_per_person": o.get("price"),
        "price_total": (o.get("price") or 0) * guests,
        "currency": o.get("currency", "RUB"),
        "source": o.get("source"),
        "is_mock": bool(o.get("is_mock")),
        "estimated": bool(o.get("price_estimated")),
        "arrival_coords": o.get("arrival_coords"),
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


def _norm_package(p, q):
    guests = q.get("guests", 1)
    totals = {
        "transport": p.get("transport_total"),
        "hotel": (p["hotel"] or {}).get("total_price"),
        "transfer": (p.get("transfer") or {}).get("price_estimate"),
        "total": p.get("total_price"),
        "currency": "RUB",
        "within_budget": p.get("within_budget"),
        "budget": q.get("budget"),
        "over_budget_by": max(0, int((p.get("total_price") or 0) - (q.get("budget") or 0))) if q.get("budget") else 0,
    }
    return {
        "id": p["id"],
        "labels": p.get("labels", []),
        "totals": totals,
        "outbound": _norm_leg(p.get("outbound"), guests),
        "return": _norm_leg(p.get("return"), guests),
        "hotel": _norm_hotel(p.get("hotel")),
        "transfer": _norm_transfer(p.get("transfer")),
        "attractiveness": p.get("attractiveness"),
        "why": p.get("why", []),
        "tradeoffs": p.get("tradeoffs", []),
        "warnings": p.get("warnings", []),
    }


def to_api(result: dict) -> dict:
    status = result.get("status")
    out = {
        "status": status,
        "query": result.get("query"),
        "weather": result.get("weather"),
        "packages": [_norm_package(p, result.get("query") or {}) for p in result.get("packages", [])],
        "data_sources": result.get("data_sources"),
        "text": result.get("text"),
        "disclaimer": result.get("disclaimer"),
        "buttons": result.get("buttons", []),
    }
    for k in ("reason", "suggestions", "errors", "missing", "unknown_cities", "unsupported_cities"):
        if k in result:
            out[k] = result[k]
    return out

def to_api_cart(cart):
    return {
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
        "disclaimer": cart["disclaimer"],
    }

def to_api_checkout(chk):
    return {**chk}