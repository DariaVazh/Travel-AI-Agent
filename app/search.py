"""Публичные функции. Все принимают JSON (dict) и возвращают JSON-совместимый dict.
Без состояния: ничего не пишут в БД, ничего не знают про Telegram.

  plan_trip(query, pinned=None)            -> готовые пакеты поездки
  replan(query, changes, selected, keep)   -> пересборка плана без поиска с нуля
  compare_destinations(query, cities)      -> сравнение направлений (вдохновение)
  search_transport(query, leg), search_hotels(query) -> отдельные поиски
"""
import copy
import hashlib
import math
import time

from cities import COVERAGE_NOTE, get_city, is_unsupported
from providers import HOTEL_PROVIDERS, TRANSPORT_PROVIDERS
from ranking import check_compat, rank_hotels, rank_transport
from schema import DEFAULTS, normalize_query
from transfer import get_transfer
from weather import get_weather, weather_text

DISCLAIMER = ("Источники: Travelpayouts (кэш Aviasales), Яндекс.Расписания, 2GIS, Open-Meteo. "
              "Оценочные поля перечислены в data_sources.estimated.")
CACHE_TTL = 300          # секунд хранить результаты провайдеров
_cache = {}


def _cached(key, fn):
    """Не ходим к провайдерам повторно за одним и тем же в течение CACHE_TTL."""
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < CACHE_TTL:
        return copy.deepcopy(hit[1])
    val = fn()
    _cache[key] = (now, val)
    return copy.deepcopy(val)


def _prepare(raw):
    """Проверка запроса + превращение городов в канонические названия."""
    q, missing, errors = normalize_query(raw)
    if missing or errors:
        return None, {"status": "need_info", "missing": missing, "errors": errors}
    unknown = []
    for field in ("origin", "destination"):
        c = get_city(q[field])
        if c:
            q[field] = c["name"]
        else:
            unknown.append(q[field])
    if unknown:
        unsupported = [u for u in unknown if is_unsupported(u)]
        errors = [f"город {u} пока вне зоны покрытия: {COVERAGE_NOTE}" if is_unsupported(u)
                  else f"не удалось найти город: {u}" for u in unknown]
        return None, {"status": "need_info", "missing": [], "unknown_cities": unknown,
                      "unsupported_cities": unsupported, "errors": errors}
    return q, None


def _transport_ranked(q, leg, wp, wt):
    a, b, day = q["origin"], q["destination"], q["date_from"]
    if leg == "return":
        a, b, day = b, a, q["date_to"]
        if not day:
            return []
    modes = ["plane", "train"] if q["transport"] == "any" else [q["transport"]]

    def fetch():
        found, covered = [], set()
        for p in sorted(TRANSPORT_PROVIDERS, key=lambda p: p.is_mock):     # реальные первыми
            need = [m for m in modes if m not in covered] if p.is_mock else modes
            if not need:
                continue
            res = p.search(a, b, day, need, q["max_transfers"])
            found += res
            covered |= {o["mode"] for o in res}
            if getattr(p, "authoritative", False) and getattr(p, "enabled", False):
                covered |= p.modes        # у такого источника пусто = рейсов нет, моки не подмешиваем
        return found

    found = _cached(("tr", a, b, day, tuple(modes), q["max_transfers"]), fetch)
    return rank_transport(found, wp, wt)


def _hotels_ranked(q, wp):
    if q["nights"] <= 0:
        return []

    def fetch():
        found = []
        for p in sorted(HOTEL_PROVIDERS, key=lambda p: p.is_mock):
            found += p.search(q["destination"], q["date_from"], q["nights"], q["pets"])
        return found

    found = _cached(("ht", q["destination"], q["date_from"], q["nights"]), fetch)
    found = [h for h in found if h["stars"] >= q["hotel_min_stars"]]
    if q["pets"]:
        found = [h for h in found if h["pets_allowed"]]
    if q["free_cancellation"]:
        found = [h for h in found if h["free_cancellation"]]
    rooms = max(1, math.ceil(q["guests"] / 2))
    for h in found:
        h["price_per_night"] *= rooms     # цена за все номера
        h["rooms"] = rooms
    return rank_hotels(found, wp)


def _pick(options, pinned_id, name, kept, dropped):
    """Лучший вариант; если просили оставить конкретный (pinned_id) и он ещё подходит - берём его."""
    if pinned_id:
        for o in options:
            if o["id"] == pinned_id:
                kept.add(name)
                return o
        dropped.add(name)
    return options[0] if options else None


def _pick_hotel(hotels, pinned_id, remaining, kept, dropped):
    """Выбранный ранее отель, если он ещё подходит; иначе лучший по рангу в пределах оставшегося
    бюджета; если в бюджет ничего не влезает, самый дешёвый."""
    if pinned_id:
        for h in hotels:
            if h["id"] == pinned_id:
                kept.add("hotel")
                return h
        dropped.add("hotel")
    if not hotels:
        return None
    if remaining is not None:
        fits = [h for h in hotels if h["total_price"] <= remaining]
        return fits[0] if fits else min(hotels, key=lambda h: h["total_price"])
    return hotels[0]


def _travel_min(p):
    return p["outbound"]["duration_min"] + (p["return"]["duration_min"] if p["return"] else 0)


def _explain(pk):
    """Для каждого пакета: почему подходит и чем пришлось пожертвовать (по сравнению с остальными)."""
    if not pk:
        return
    if len(pk) == 1:
        pk[0]["why"], pk[0]["tradeoffs"] = ["единственный вариант под ваши условия"], []
        return
    min_price = min(p["total_price"] for p in pk)
    min_time = min(_travel_min(p) for p in pk)
    ratings = [p["hotel"]["rating"] for p in pk if p["hotel"]]
    best = max(ratings) if ratings else None
    for p in pk:
        why, trade = [], []
        if p["total_price"] == min_price:
            why.append("самый дешёвый из предложенных")
        else:
            trade.append(f"дороже самого дешёвого на {p['total_price'] - min_price} ₽")
        t = _travel_min(p)
        if t == min_time:
            why.append("меньше всего времени в дороге")
        else:
            trade.append(f"в дороге дольше на {(t - min_time) // 60} ч {(t - min_time) % 60} мин")
        h = p["hotel"]
        if h and best is not None:
            if h["rating"] == best:
                why.append(f"отель с лучшим рейтингом ({best})")
            elif best - h["rating"] >= 0.5:
                trade.append(f"рейтинг отеля {h['rating']} вместо {best}")
        p["why"] = why or ["лучший баланс цены и времени по вашим приоритетам"]
        p["tradeoffs"] = trade


def _data_sources(pk, _):
    """Что в выдаче реальное, а что нет"""
    tr = {o["source"] for p in pk for o in (p["outbound"], p["return"]) if o}
    ht = {p["hotel"]["source"] for p in pk if p["hotel"]}
    tf = {p["transfer"]["source"] for p in pk if p.get("transfer")}
    estimated = []
    if any(o and o.get("price_estimated") for p in pk for o in (p["outbound"], p["return"])):
        estimated.append("цены на поезда")
    if any(p["hotel"] and p["hotel"].get("price_estimated") for p in pk):
        estimated.append("итоговая цена отелей за ваши даты")
    if "оценка" in tf or pk:
        estimated.append("стоимость трансфера")
    return {"transport": sorted(tr), "hotels": sorted(ht), "transfer": sorted(tf),
            "weather": "Open-Meteo", "estimated": estimated}


def _suggestions(q):
    """Что можно ослабить, если ничего не нашлось (для LLM: что предложить пользователю)."""
    s = []
    if q["max_transfers"] == 0:
        s.append("разрешить рейсы с пересадкой")
    if q["transport"] != "any":
        s.append("рассмотреть другой вид транспорта")
    if q["free_cancellation"]:
        s.append("убрать требование бесплатной отмены")
    if q["hotel_min_stars"] > 0:
        s.append("снизить минимальное число звёзд")
    if q["pets"]:
        s.append("поездка с питомцем сильно сужает выбор отелей")
    return s


def search_transport(raw, leg="outbound"):
    """Билеты на один участок ('outbound' | 'return'), ранжированные по цене и времени."""
    q, err = _prepare(raw)
    if err:
        return err
    return {"status": "ok", "leg": leg,
            "options": _transport_ranked(q, leg, q["priority"]["price"], q["priority"]["time"])}


def search_hotels(raw):
    q, err = _prepare(raw)
    if err:
        return err
    return {"status": "ok", "options": _hotels_ranked(q, q["priority"]["price"])}


def plan_trip(raw, pinned=None):
    """Собирает до 3 готовых пакетов: самый дешёвый / самый быстрый / баланс.
    pinned = {'outbound': id, 'return': id, 'hotel': id}: эти варианты оставить, если они ещё подходят."""
    q, err = _prepare(raw)
    if err:
        return err
    pinned = pinned or {}
    # (название, вес цены билетов, вес времени билетов, вес цены при выборе отеля).
    # В "самом быстром" отель не выбираем по одному качеству: иначе получим самый дорогой люкс.
    hp = max(q["priority"]["price"], 0.5)
    presets = [("Самый дешёвый", 1.0, 0.0, 1.0), ("Самый быстрый", 0.0, 1.0, hp),
               ("Баланс по вашим приоритетам", q["priority"]["price"], q["priority"]["time"],
                q["priority"]["price"])]
    packages, kept, dropped, reasons = {}, set(), set(), set()

    for label, wp, wt, hw in presets:
        o = _pick(_transport_ranked(q, "outbound", wp, wt), pinned.get("outbound"), "outbound", kept, dropped)
        b = _pick(_transport_ranked(q, "return", wp, wt), pinned.get("return"), "return", kept, dropped)
        h = None
        if q["nights"] and o:
            remaining = None
            if q["budget"] is not None:                      # сколько останется на отель после билетов
                remaining = q["budget"] - (o["price"] + (b["price"] if b else 0)) * q["guests"] - 1500
            h = _pick_hotel(_hotels_ranked(q, hw), pinned.get("hotel"), remaining, kept, dropped)
        if not o:
            reasons.add("не нашлось подходящих билетов")
            continue
        if q["nights"] and not h:
            reasons.add("не нашлось отелей под ваши условия")
            continue

        key = (o["id"], b["id"] if b else "", h["id"] if h else "")
        if key in packages:
            packages[key]["labels"].append(label)
            continue
        legs = (o["price"] + (b["price"] if b else 0)) * q["guests"]
        tr = get_transfer(o.get("arrival_coords"), h.get("coords")) if h else None
        total = legs + (h["total_price"] if h else 0) + (tr["price_estimate"] if tr else 0)
        warns = check_compat(o, b, h)
        if tr and tr["duration_min"] > 60:
            warns.append(f"долгий трансфер до отеля: ~{tr['duration_min']} мин")
        if q["budget"] is not None and total > q["budget"]:
            warns.append(f"превышает бюджет на {int(total - q['budget'])} ₽")
        packages[key] = {
            "id": "p" + hashlib.sha1("|".join(key).encode()).hexdigest()[:8],   # стабильный id
            "labels": [label], "outbound": o, "return": b, "hotel": h, "transfer": tr,
            "transport_total": legs, "total_price": total,
            "within_budget": q["budget"] is None or total <= q["budget"],
            "warnings": warns,
        }

    pk = list(packages.values())
    _explain(pk)
    data_sources = _data_sources(pk, get_weather is not None)
    weather = get_weather(q["destination"], q["date_from"], q["date_to"])
    res = {"status": "ok" if pk else "no_results", "query": q, "packages": pk, "weather": weather,
           "buttons": [{"id": p["id"], "callback": f"pick:{p['id']}", "label": " / ".join(p["labels"])}
                       for p in pk],
           "data_sources": data_sources,
           "disclaimer": DISCLAIMER, "kept": sorted(kept), "dropped": sorted(dropped)}
    if pk:
        res["text"] = (weather_text(q["destination"], weather) + "\n\n" if weather else "") + to_text(pk)
    else:
        res["reason"] = "; ".join(sorted(reasons)) or "нет вариантов"
        res["suggestions"] = _suggestions(q)
        res["text"] = f"Не получилось собрать поездку: {res['reason']}."
    return res


_RU = {"outbound": "билеты туда", "return": "билеты обратно", "hotel": "отель"}


def replan(query, changes, selected=None, keep=("outbound", "return", "hotel")):
    """Пересборка плана. query - прошлый запрос (можно result['query']), changes - что поменялось
    (например {'date_from': '2026-12-01', 'date_to': '2026-12-08'}, {'pets': True},
    {'budget': 80000}, {'priority': {'price': 1}}), selected - ранее выбранный пакет.
    Оставляет из выбранного пакета всё, что ещё подходит, остальное подбирает заново."""
    new = {k: v for k, v in (query or {}).items() if k in DEFAULTS}
    changes = changes or {}
    for k, v in changes.items():
        if k == "priority" and isinstance(v, dict):
            new["priority"] = {**(new.get("priority") or {}), **v}
        else:
            new[k] = v
    pinned = {k: selected[k]["id"] for k in keep if selected and selected.get(k)}
    res = plan_trip(new, pinned=pinned)
    if res["status"] == "need_info":
        return res
    kept, dropped = res.pop("kept"), res.pop("dropped")
    res["replan"] = {"changes": changes, "kept": kept, "dropped": dropped}
    note = []
    if kept:
        note.append("оставила: " + ", ".join(_RU[k] for k in kept))
    if dropped:
        note.append("подобрала заново: " + ", ".join(_RU[k] for k in dropped))
    if note:
        res["text"] = "Пересобрала план (" + "; ".join(note) + ").\n\n" + res["text"]
    return res


def compare_destinations(raw, cities, top=5):
    """Для вдохновения: сравнивает города-кандидаты (их предлагает LLM) по реальным данным:
    самый дешёвый пакет, время в пути, погода. raw - запрос БЕЗ destination."""
    rows = []
    for c in cities:
        res = plan_trip({**raw, "destination": c})
        if res["status"] == "need_info":
            if res.get("unknown_cities"):
                rows.append({"city": c, "status": "unsupported_city" if res.get("unsupported_cities")
                             else "unknown_city"})
                continue
            return res                                  # не хватает общих данных (даты, откуда)
        if res["status"] != "ok":
            rows.append({"city": c, "status": "no_results", "reason": res.get("reason")})
            continue
        balanced = [p for p in res["packages"] if "Баланс по вашим приоритетам" in p["labels"]]
        best = balanced[0] if balanced else min(res["packages"], key=lambda p: p["total_price"])
        rows.append({"city": res["query"]["destination"], "status": "ok",
                     "total_price": best["total_price"], "within_budget": best["within_budget"],
                     "travel_min": best["outbound"]["duration_min"], "mode": best["outbound"]["mode"],
                     "weather": res["weather"], "package_id": best["id"]})
    rows.sort(key=lambda r: (r["status"] != "ok", not r.get("within_budget", False), r.get("total_price", 0)))
    rows = rows[:top]
    lines = []
    for i, r in enumerate(rows, 1):
        if r["status"] != "ok":
            why = {"unsupported_city": "пока вне зоны покрытия", "unknown_city": "город не найден"}.get(
                r["status"], "нет подходящих вариантов")
            lines.append(f"{i}. {r['city']}: {why}")
            continue
        w = r["weather"]
        temp = f", днём ~{w['temp_max_avg']}°C" if w else ""
        lines.append(f"{i}. {r['city']}: от {int(r['total_price'])} ₽, дорога {r['travel_min'] // 60} ч "
                     f"{r['travel_min'] % 60} мин{temp}" + ("" if r["within_budget"] else " (выше бюджета)"))
    return {"status": "ok", "rows": rows, "text": "\n".join(lines), "disclaimer": DISCLAIMER}


# ───────────────────────── текст для чата ─────────────────────────
def _tag(x):
    """Короткая пометка происхождения данных для текста."""
    src = {"travelpayouts": "цена из кэша Aviasales", "yandex_rasp": "расписание Яндекса",
           "2gis": "отель из 2GIS"}.get(x["source"], x["source"])
    return src + (", цена оценочная" if x.get("price_estimated") else "")


def to_text(packages):
    lines = []
    for p in packages:
        o, b, h, tr = p["outbound"], p["return"], p["hotel"], p.get("transfer")
        lines.append(f"▶ {' / '.join(p['labels'])}: {int(p['total_price'])} ₽")
        station = f", {o['arrival_station']}" if o.get("arrival_station") else ""
        lines.append(f"  Туда: {o['carrier']} {o['depart'][5:].replace('T', ' ')} → {o['arrive'][11:]}{station}, "
                     f"{o['duration_min'] // 60} ч {o['duration_min'] % 60} мин, {o['price']} ₽/чел ({_tag(o)})")
        if b:
            lines.append(f"  Обратно: {b['depart'][5:].replace('T', ' ')} → {b['arrive'][11:]}, {b['price']} ₽/чел")
        if h:
            stars = f"{h['stars']}★" if h.get("stars") else "без категории"
            reviews = f" ({h['reviews']} отз.)" if h.get("reviews") else ""
            lines.append(f"  Отель: {h['name']}, {stars}, рейтинг {h['rating']}{reviews}, "
                         f"{int(h['total_price'])} ₽ ({_tag(h)})")
            if h.get("amenities"):
                lines.append("  Удобства (2GIS): " + ", ".join(h["amenities"][:5]))
        if tr:
            lines.append(f"  Трансфер до отеля: ~{tr['duration_min']} мин, {tr['distance_km']} км, "
                         f"≈{tr['price_estimate']} ₽ ({tr['source']})")
        lines.append("  Почему: " + ", ".join(p["why"]))
        if p["tradeoffs"]:
            lines.append("  Чем пришлось пожертвовать: " + ", ".join(p["tradeoffs"]))
        risks = (h["cons"] + h["risks"]) if h else []
        if risks:
            lines.append("  Риски отеля: " + ", ".join(risks))
        for w in p["warnings"]:
            lines.append(f"  ⚠ {w}")
        lines.append("")
    return "\n".join(lines).strip()
