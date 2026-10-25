"""РЕАЛЬНЫЕ авиабилеты: Aviasales Data API (Travelpayouts), метод prices_for_dates.
Цены берутся из кэша поисков пользователей Aviasales (не живая выдача и не гарантия наличия).
Токен: TRAVELPAYOUTS_TOKEN в .env (личный кабинет -> Профиль -> API token).
Ограничения, о которых стоит помнить:
  * на одну дату API отдаёт одно самое дешёвое предложение, поэтому делаем два запроса:
    только прямые и любые (получаем до двух вариантов на участок);
  * время прибытия считается как вылет + длительность в часовом поясе аэропорта вылета
    (для рейсов через часовые пояса может отличаться на пару часов);
  * если в кэше нет билетов на эту дату, провайдер вернёт [] и сработают моки."""
import sys
import time
from datetime import datetime, timedelta

import requests

from cities import get_city
from config import get_secret

URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
DEBUG = True


def _log(msg):
    if DEBUG:
        print(f"[travelpayouts] {msg}", file=sys.stderr)


def _local_naive(s):
    """'2026-11-20T07:00:00+03:00' -> naive datetime по местному времени вылета."""
    return datetime.fromisoformat(str(s).replace("Z", "+00:00")).replace(tzinfo=None)


class TravelpayoutsFlights:
    name = "travelpayouts"
    is_mock = False

    def __init__(self):
        self.token = get_secret("TRAVELPAYOUTS_TOKEN")
        self._blocked_until = 0.0
        if not self.token:
            _log("токен не найден (TRAVELPAYOUTS_TOKEN): реальные авиабилеты отключены")

    def _query(self, o, d, day, direct):
        if time.time() < self._blocked_until:
            return []
        params = {"origin": o, "destination": d, "departure_at": day, "one_way": "true",
                  "currency": "rub", "sorting": "price", "limit": 5}
        if direct:
            params["direct"] = "true"          # для «любых» рейсов параметр не передаём
        for attempt in (1, 2):                              # один повтор: таймауты бывают разовыми
            try:
                r = requests.get(URL, params=params, timeout=(5, 20),
                                 headers={"X-Access-Token": self.token, "Accept-Encoding": "gzip, deflate"})
                if r.status_code != 200:
                    _log(f"HTTP {r.status_code}: {r.text[:200]}")
                    return []
                js = r.json()
                if not js.get("success"):
                    _log(f"success=false: {js.get('error')}")
                    return []
                return js.get("data") or []
            except Exception as e:
                _log(f"{type(e).__name__}: {str(e)[:120]} (попытка {attempt}/2)")
        self._blocked_until = time.time() + 60          # два сбоя подряд: не долбим API минуту
        return []

    def search(self, origin, destination, day, modes, max_transfers):
        if "plane" not in modes or not self.token:
            return []
        a, b = get_city(origin), get_city(destination)
        if not (a and b and a.get("iata") and b.get("iata")):
            return []                                    # нет кода аэропорта: пусть работают моки
        out, seen = [], set()
        for direct in ((True,) if max_transfers == 0 else (True, False)):
            for item in self._query(a["iata"], b["iata"], day, direct):
                opt = self._to_option(item, origin, destination, a, b)
                if opt and opt["id"] not in seen:
                    seen.add(opt["id"])
                    out.append(opt)
        if max_transfers is not None:
            out = [o for o in out if o["transfers"] <= max_transfers]
        return out

    def _to_option(self, item, origin, destination, a, b):
        try:
            dep = _local_naive(item["departure_at"])
            total = int(item.get("duration") or 0)
            to_dest = int(item.get("duration_to") or 0)
            back = int(item.get("duration_back") or 0)
            # Для рейса в одну сторону берём полную длительность маршрута (она включает ожидание
            # на пересадке); duration_to у рейсов с пересадкой бывает заметно короче.
            dur = (total - back) if (total and back) else (total or to_dest)
            price = int(round(float(item["price"])))
        except (KeyError, TypeError, ValueError):
            return None
        if dur <= 0 or price <= 0:
            return None
        airline, flight = item.get("airline") or "", item.get("flight_number") or ""
        return {
            "id": f"tp-{a['iata']}{b['iata']}-{dep:%Y%m%d%H%M}-{airline}{flight}",
            "mode": "plane",
            "carrier": f"{airline} {flight}".strip() or "авиакомпания не указана",
            "origin": origin, "destination": destination,
            "arrival_coords": b["airport"],
            "depart": dep.isoformat(timespec="minutes"),
            "arrive": (dep + timedelta(minutes=dur)).isoformat(timespec="minutes"),
            "duration_min": dur, "transfers": int(item.get("transfers") or 0),
            "price": price, "currency": "RUB",
            "source": self.name, "is_mock": False,
        }
