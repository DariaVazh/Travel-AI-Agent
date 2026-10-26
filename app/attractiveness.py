"""Коэффициент привлекательности отеля, дороги и пакета целиком (0-100).
Функции чистые: dict на входе, dict на выходе."""
from datetime import datetime
from statistics import median


def _clip(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def _lin(x, good, bad):
    """1.0 при x == good, 0.0 при x == bad, между ними линейно."""
    if good == bad:
        return 1.0
    return _clip((x - bad) / (good - bad))


def _price_score(price, peers_prices):
    """Дешевле типичного значения среди альтернатив = лучше. Мало альтернатив = нейтрально."""
    if not price or len(peers_prices) < 3:
        return 0.5
    return _lin(price / median(peers_prices), 0.7, 1.6)


def _label(score):
    return "отлично" if score >= 80 else "хорошо" if score >= 65 else "средне" if score >= 50 else "слабо"


# ───────────────────────── отель ─────────────────────────
def hotel_score(h, query=None, peers=None):
    """h: отель из result['packages'][i]['hotel']; peers: список отелей той же выдачи (для сравнения цены)."""
    q = query or {}
    n = int(h.get("reviews") or 0)
    real = bool(h.get("rating_real"))
    adj = h.get("rating_adj", h.get("rating") or 0)
    reviews_s = _lin(adj, 10, 6) if real else 0.5
    conf = n / (n + 50) if real else 0.1
    value_s = _price_score(h.get("total_price"), [p["total_price"] for p in peers or [] if p.get("total_price")])
    place_s = _lin(h.get("distance_center_km", 4), 1, 8)

    fit_s, why, cautions = 0.5, [], []
    amen = " ".join(h.get("amenities") or []).lower()
    if (q.get("children") or 0) > 0 and "детск" in amen:
        fit_s += 0.3
        why.append("есть детская комната (вы едете с ребёнком)")
    if q.get("pets"):
        if h.get("pets_allowed"):
            fit_s += 0.2
            why.append("можно с животными")
        else:
            fit_s -= 0.5
            cautions.append("не подтверждено, что можно с животными")
    if h.get("meal") in ("BB", "HB", "AI"):
        fit_s += 0.1
        why.append("питание включено")
    fit_s = _clip(fit_s)

    if real and adj >= 9:
        why.append(f"высокий рейтинг {h.get('rating')} по {n} отзывам")
    if value_s >= 0.75:
        why.append("цена ниже типичной для этого города")
    if place_s >= 0.8:
        why.append("рядом с центром")
    if not real:
        cautions.append("рейтинг оценочный: отзывов нет")
    elif n < 30:
        cautions.append(f"мало отзывов ({n}), оценка ненадёжна")
    if value_s <= 0.25:
        cautions.append("дороже большинства вариантов")
    if h.get("distance_center_km", 0) > 5:
        cautions.append(f"далеко от центра ({h['distance_center_km']} км)")

    score = 100 * (0.40 * reviews_s + 0.25 * value_s + 0.15 * place_s + 0.20 * fit_s)
    return {"score": round(score), "confidence": round(conf, 2),
            "components": {"отзывы": round(reviews_s * 100), "цена": round(value_s * 100),
                           "расположение": round(place_s * 100), "соответствие запросу": round(fit_s * 100)},
            "why": why, "cautions": cautions}


# ───────────────────────── дорога ─────────────────────────
def _hour_comfort(hour):
    if 8 <= hour <= 21:
        return 1.0
    if hour in (6, 7, 22):
        return 0.7
    if hour in (5, 23):
        return 0.4
    return 0.2


def route_score(o, peers=None):
    """o: один рейс (outbound/return); peers: другие рейсы этого же участка для сравнения."""
    durs = [p["duration_min"] for p in peers or [] if p.get("duration_min")]
    dur_s = _lin(o["duration_min"], min(durs), max(durs)) if len(durs) >= 2 and max(durs) > min(durs) else 0.7
    tr = o.get("transfers", 0)
    transfers_s = 1.0 if tr == 0 else 0.6 if tr == 1 else 0.3
    dep, arr = datetime.fromisoformat(o["depart"]), datetime.fromisoformat(o["arrive"])
    time_s = (_hour_comfort(dep.hour) + _hour_comfort(arr.hour)) / 2
    price_s = _price_score(o.get("price"), [p["price"] for p in peers or [] if p.get("price")])

    why, cautions = [], []
    if tr == 0:
        why.append("без пересадок")
    else:
        cautions.append(f"пересадок: {tr}")
    if dur_s >= 0.9 and len(durs) >= 2:
        why.append("одна из самых быстрых")
    if dur_s <= 0.2 and len(durs) >= 2:
        cautions.append("одна из самых долгих")
    if time_s >= 0.9:
        why.append("удобное время в пути")
    if arr.hour >= 23 or arr.hour <= 5:
        cautions.append("прибытие ночью")
    if dep.hour <= 5:
        cautions.append("очень ранний/ночной выезд")

    conf = 0.2 if o.get("is_mock") else 0.8
    if o.get("price_estimated"):
        conf -= 0.15
    score = 100 * (0.35 * dur_s + 0.25 * transfers_s + 0.25 * time_s + 0.15 * price_s)
    return {"score": round(score), "confidence": round(max(conf, 0.05), 2),
            "components": {"время в пути": round(dur_s * 100), "пересадки": round(transfers_s * 100),
                           "удобство времени": round(time_s * 100), "цена": round(price_s * 100)},
            "why": why, "cautions": cautions}


# ───────────────────────── пакет целиком ─────────────────────────
def package_attractiveness(package, query=None, hotel_peers=None, out_peers=None, back_peers=None):
    """Итоговый коэффициент пакета: 60% отель, 40% дорога, минус штраф за предупреждения (до 15)."""
    legs = [route_score(package["outbound"], out_peers)]
    if package.get("return"):
        legs.append(route_score(package["return"], back_peers))
    route = {"score": round(sum(x["score"] for x in legs) / len(legs)),
             "confidence": round(min(x["confidence"] for x in legs), 2),
             "why": sorted({w for x in legs for w in x["why"]}),
             "cautions": sorted({c for x in legs for c in x["cautions"]})}
    hotel = hotel_score(package["hotel"], query, hotel_peers) if package.get("hotel") else None
    penalty = min(15, 3 * len(package.get("warnings") or []))
    if hotel:
        total = 0.6 * hotel["score"] + 0.4 * route["score"]
        conf = 0.6 * hotel["confidence"] + 0.4 * route["confidence"]
    else:
        total, conf = route["score"], route["confidence"]
    total = max(0, round(total - penalty))
    return {"score": total, "label": _label(total), "confidence": round(conf, 2),
            "hotel": hotel, "route": route, "penalty": penalty,
            "basis": "отель: рейтинг и число отзывов (2GIS), цена, расположение, соответствие запросу; "
                     "дорога: параметры рейса (отзывов на рейсы в источниках нет); штраф за предупреждения"}
