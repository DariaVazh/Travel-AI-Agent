from datetime import date
from decimal import Decimal
from sqlalchemy import select
from .connection import AsyncSessionLocal
from .models import Booking


async def create_demo_booking(user_id: int, query: dict, package: dict) -> int:

    hotel = package.get("hotel")

    if not hotel or not hotel.get("name"):
        raise ValueError("Отель не выбран")

    if not query.get("date_from") or not query.get("date_to"):
        raise ValueError("Не указаны даты проживания")

    check_in = date.fromisoformat(query["date_from"])
    check_out = date.fromisoformat(query["date_to"])

    if check_out <= check_in:
        raise ValueError("Некорректные даты")

    price = Decimal(str(package["total_price"]))

    if price < 0:
        raise ValueError("Некорректная стоимость")

    booking = Booking(
        user_id=user_id,
        hotel_name=hotel["name"],
        destination=query["destination"],
        check_in=check_in,
        check_out=check_out,
        total_price=price,
        currency="RUB",
        status="demo_booked",
        package_snapshot={
            "query": query,
            "package": package
        }
    )

    async with AsyncSessionLocal.begin() as session:
        session.add(booking)
        await session.flush()

        return booking.id


async def get_user_bookings(user_id: int) -> list[dict]:

    async with AsyncSessionLocal() as session:

        stmt = (
            select(Booking)
            .where(Booking.user_id == user_id)
            .order_by(Booking.created_at.desc())
            .limit(20)
        )

        result = await session.scalars(stmt)

        return [
            {
                "id": booking.id,
                "hotel_name": booking.hotel_name,
                "destination": booking.destination,
                "check_in": booking.check_in.isoformat(),
                "check_out": booking.check_out.isoformat(),
                "total_price": str(booking.total_price),
                "currency": booking.currency,
                "status": booking.status
            }
            for booking in result.all()
        ]


async def get_booking(user_id: int, booking_id: int) -> dict | None:

    async with AsyncSessionLocal() as session:

        stmt = select(Booking).where(
            Booking.id == booking_id,
            Booking.user_id == user_id
        )

        booking = await session.scalar(stmt)

        if booking is None:
            return None

        return {
            "id": booking.id,
            "hotel_name": booking.hotel_name,
            "destination": booking.destination,
            "check_in": booking.check_in.isoformat(),
            "check_out": booking.check_out.isoformat(),
            "total_price": str(booking.total_price),
            "currency": booking.currency,
            "status": booking.status,
            "details": booking.package_snapshot
        }
