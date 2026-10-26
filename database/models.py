from datetime import datetime
from typing import Any


from sqlalchemy import (
    BigInteger,
    DateTime,
    Identity,
    func,
    ForeignKey,
    Text
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

class TripState(Base):
    __tablename__ = "trip_states"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True
    )

    query: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True
    )

    packages: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        default=list,
        nullable=False
    )

    selected_package_id: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    cart: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=lambda: {"items": []},
        nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )