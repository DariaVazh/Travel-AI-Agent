from datetime import datetime
from typing import Any
from decimal import Decimal
from sqlalchemy import (
    BigInteger,
    DateTime,
    Date,
    Identity,
    func,
    ForeignKey,
    String,
    CheckConstraint,
    Numeric
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column
)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True
    )

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        nullable=False
    )

    name: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True
    )

    memory: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )


class Booking(Base):
    __tablename__ = "bookings"

    __table_args__ = (
        CheckConstraint(
            "check_out > check_in",
            name="check_booking_dates"
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )

    hotel_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False
    )

    destination: Mapped[str] = mapped_column(
        String(120),
        nullable=False
    )

    check_in: Mapped[datetime] = mapped_column(Date)
    check_out: Mapped[datetime] = mapped_column(Date)

    total_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        default="RUB"
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="demo_booked"
    )

    package_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )