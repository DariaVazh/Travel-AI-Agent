"""Провайдеры данных. Сейчас только МОК. Реальный API = новый класс с тем же search()
и добавление экземпляра в TRANSPORT_PROVIDERS / HOTEL_PROVIDERS внизу файла."""
import random
from datetime import datetime, timedelta

from app.cities import get_city, haversine_km

class TransportProvider:
    """search() должен вернуть список dict с полями: id, mode ('plane'|'train'), carrier,
    origin, destination, arrival_coords ({lat,lon}), depart, arrive (ISO 'YYYY-MM-DDTHH:MM'),
    duration_min, transfers, price (RUB за 1 человека), currency, source, is_mock."""
    name = "base"
    is_mock = True      # у реальных провайдеров поставьте False: тогда моки не дублируют их виды транспорта

    def search(self, origin, destination, day, modes, max_transfers):
        raise NotImplementedError


class HotelProvider:
    """search() должен вернуть список dict с полями: id, name, city, stars, rating,
    price_per_night (RUB за 1 номер), nights, currency, meal, free_cancellation,
    distance_center_km, checkin_from, checkout_until, pets_allowed, coords ({lat,lon}),
    source, is_mock. Фильтры по звёздам/питомцам/отмене применяет search.py."""
    name = "base"
    is_mock = True      # у реальных провайдеров поставьте False

    def search(self, city, check_in, nights, pets):
        raise NotImplementedError



from app.travelpayouts import TravelpayoutsFlights


from app.yandex_rasp import YandexTrains
from app.hotels_2gis import Hotels2GIS
from app import twogis

_flights, _trains = TravelpayoutsFlights(), YandexTrains()
TRANSPORT_PROVIDERS = [_flights, _trains]
HOTEL_PROVIDERS = [Hotels2GIS()]


def sources_status():
    """Что сейчас подключено: удобно напечатать перед демо."""
    return {
        "авиабилеты": "Travelpayouts (кэш Aviasales)" if _flights.token else "токена нет",
        "поезда": "Яндекс.Расписания" if _trains.enabled else "ключа нет",
        "отели": "2GIS (цены оценочные)" if twogis.KEY else "ключа 2GIS нет",
        "трансфер": "2GIS" if twogis.KEY else "оценка по прямой",
    }
