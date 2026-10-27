"""РЕАЛЬНОЕ расписание поездов: API Яндекс.Расписаний. Ключ: YANDEX_RASP_KEY в .env.
Что реальное: время отправления и прибытия, длительность, номер поезда, перевозчик."""
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

from app.cities import get_city
from app.config import get_secret

BASE = "https://api.rasp.yandex.net/v3.0"
CODES_FILE = Path(__file__).with_name(".yandex_codes.json")   # кэш кодов городов (экономим запросы)
MAX_SEGMENTS = 12
DEBUG = True


def _log(msg):
    if DEBUG:
        print(f"[yandex_rasp] {msg}", file=sys.stderr)


def _naive(s):
    """ISO со смещением -> naive datetime по местному времени той станции."""
    return datetime.fromisoformat(str(s).replace("Z", "+00:00")).replace(tzinfo=None)


class YandexTrains:
    name = "yandex_rasp"
    is_mock = False
    modes = {"train"}
    authoritative = True     # если ключ есть и поездов нет, значит их действительно нет (моки не подмешиваем)

    def __init__(self):
        self.key = get_secret("YANDEX_RASP_KEY")
        self.enabled = bool(self.key)
        self._blocked_until = 0.0
        self._codes = {}
        try:
            self._codes = json.loads(CODES_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        if not self.enabled:
            _log("ключ не найден (YANDEX_RASP_KEY): реальные поезда отключены")

    # ── сеть ──
    def _get(self, path, **params):
        if time.time() < self._blocked_until:
            return None
        try:
            r = requests.get(f"{BASE}/{path}/", timeout=15,
                             params={"apikey": self.key, "format": "json", "lang": "ru_RU", **params})
            if r.status_code != 200:
                _log(f"{path}: HTTP {r.status_code}: {r.text[:200]}")
                return None
            return r.json()
        except Exception as e:
            _log(f"{path}: {type(e).__name__}: {str(e)[:150]}")
            self._blocked_until = time.time() + 60
            return None

    def _code(self, city):
        """Код города в системе Яндекса: ищем по координатам центра и запоминаем."""
        name = city["name"]
        if name in self._codes:
            return self._codes[name]
        c = city["center"]
        js = self._get("nearest_settlement", lat=c["lat"], lng=c["lon"], distance=50)
        code = (js or {}).get("code")
        if code:
            self._codes[name] = code
            try:
                CODES_FILE.write_text(json.dumps(self._codes, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
        return code

    # ── поиск ──
    def search(self, origin, destination, day, modes, max_transfers):
        if "train" not in modes or not self.enabled:
            return []
        a, b = get_city(origin), get_city(destination)
        if not (a and b):
            return []
        ca, cb = self._code(a), self._code(b)
        if not (ca and cb):
            return []
        js = self._get("search", **{"from": ca, "to": cb, "date": day,
                                    "transport_types": "train", "transfers": "false", "limit": 100})
        out = []
        for seg in (js or {}).get("segments") or []:
            opt = self._to_option(seg, origin, destination, a, b, ca, cb)
            if opt:
                out.append(opt)
        out.sort(key=lambda o: o["depart"])
        return out[:MAX_SEGMENTS]

    def _price(self, seg, a, b, number):
        """(цена за человека, оценочная ли)."""
        try:
            places = (seg.get("tickets_info") or {}).get("places") or []
            prices = [float(p["price"]["whole"]) + float(p["price"].get("cents", 0)) / 100
                      for p in places if p.get("price")]
            if prices:
                return int(round(min(prices))), False
        except (KeyError, TypeError, ValueError):
            pass
        return None, True

    def _to_option(self, seg, origin, destination, a, b, ca, cb):
        try:
            dep, arr = _naive(seg["departure"]), _naive(seg["arrival"])
            dur = round(float(seg.get("duration") or (arr - dep).total_seconds()) / 60)
        except (KeyError, TypeError, ValueError):
            return None
        if dur <= 0:
            return None
        if arr <= dep:
            arr = dep + timedelta(minutes=dur)
        thread = seg.get("thread") or {}
        number = thread.get("number") or ""
        carrier = ((thread.get("carrier") or {}).get("title")) or ""
        price, estimated = self._price(seg, a, b, number)
        if price is None:
            return None
        return {
            "id": f"ya-{ca}{cb}-{dep:%Y%m%d%H%M}-{number}",
            "mode": "train",
            "carrier": f"{number} {carrier}".strip() or "поезд",
            "origin": origin, "destination": destination,
            "arrival_coords": b["center"],                  # вокзал ≈ центр города
            "depart": dep.isoformat(timespec="minutes"),
            "arrive": arr.isoformat(timespec="minutes"),
            "duration_min": dur, "transfers": 0,
            "price": price, "price_estimated": estimated, "currency": "RUB",
            "source": self.name, "is_mock": False,
        }
