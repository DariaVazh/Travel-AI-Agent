"""Ранжирование + объяснения (плюсы / минусы / риски) для каждого варианта."""
from datetime import datetime


def _norm(vals):
    lo, hi = min(vals), max(vals)
    return [0.0 if hi == lo else (v - lo) / (hi - lo) for v in vals]


def rank_transport(options, w_price, w_time):
    """Чем выше score, тем лучше. Пересадки — небольшой штраф."""
    if not options:
        return []
    p = _norm([o["price"] for o in options])
    t = _norm([o["duration_min"] for o in options])
    min_price = min(o["price"] for o in options)
    min_dur = min(o["duration_min"] for o in options)
    ranked = []
    for o, pn, tn in zip(options, p, t):
        score = w_price * (1 - pn) + w_time * (1 - tn) - 0.05 * o["transfers"]
        pros, cons, risks = [], [], []
        if o["price"] == min_price:
            pros.append("самый дешёвый среди найденных")
        else:
            cons.append(f"дороже самого дешёвого на {o['price'] - min_price} ₽")
        if o["duration_min"] == min_dur:
            pros.append("самый быстрый среди найденных")
        else:
            cons.append(f"дольше самого быстрого на {o['duration_min'] - min_dur} мин")
        if o["transfers"] == 0:
            pros.append("без пересадок")
        else:
            risks.append(f"пересадок: {o['transfers']} (риск не успеть на стыковку)")
        h = datetime.fromisoformat(o["arrive"]).hour
        if h >= 23 or h <= 5:
            risks.append("прибытие ночью")
        ranked.append({**o, "score": round(score, 3), "pros": pros, "cons": cons, "risks": risks})
    return sorted(ranked, key=lambda x: -x["score"])


def rank_hotels(hotels, w_price):
    if not hotels:
        return []
    totals = [h["price_per_night"] * max(h["nights"], 1) for h in hotels]
    pn = _norm(totals)
    rn = _norm([h.get("rating_adj", h["rating"]) for h in hotels])
    dn = _norm([h["distance_center_km"] for h in hotels])
    min_total = min(totals)
    ranked = []
    for h, tot, a, r, d in zip(hotels, totals, pn, rn, dn):
        quality = 0.5 * r + 0.3 * (1 - d) + 0.2 * (1 if h["free_cancellation"] else 0)
        score = w_price * (1 - a) + (1 - w_price) * quality
        pros, cons, risks = [], [], []
        if h.get("rating_adj", h["rating"]) >= 9:
            pros.append(f"высокий рейтинг {h['rating']}")
        if h["distance_center_km"] <= 1:
            pros.append("рядом с центром")
        elif h["distance_center_km"] > 5:
            cons.append(f"далеко от центра ({h['distance_center_km']} км)")
        if h["free_cancellation"]:
            pros.append("бесплатная отмена")
        else:
            risks.append("невозвратный тариф")
        if tot == min_total:
            pros.append("самый дешёвый среди найденных")
        ranked.append({**h, "total_price": tot, "score": round(score, 3),
                       "pros": pros, "cons": cons, "risks": risks})
    return sorted(ranked, key=lambda x: -x["score"])


def check_compat(outbound, ret, hotel):
    """Проверка состыковок: прилёт/заселение и выселение/вылет."""
    warns = []
    if not hotel:
        return warns
    arr = datetime.fromisoformat(outbound["arrive"])
    h, m = map(int, hotel["checkin_from"].split(":"))
    if arr.hour < h or (arr.hour == h and arr.minute < m):
        warns.append(f"прибытие в {arr:%H:%M}, заселение с {hotel['checkin_from']}: "
                     "нужен ранний заезд или камера хранения")
    if arr.hour >= 23 or arr.hour <= 5:
        warns.append("поздний/ночной заезд: предупредите отель заранее")
    if ret:
        dep = datetime.fromisoformat(ret["depart"])
        ch, cm = map(int, hotel["checkout_until"].split(":"))
        gap = (dep.hour * 60 + dep.minute) - (ch * 60 + cm)
        if dep.hour < 8:
            warns.append(f"обратный рейс в {dep:%H:%M}: ранний выезд из отеля")
        elif gap > 360:
            warns.append(f"между выселением ({hotel['checkout_until']}) и рейсом "
                         f"({dep:%H:%M}) ~{gap // 60} ч: понадобится хранение багажа")
    return warns
