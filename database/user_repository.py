from sqlalchemy import select, func, update
from sqlalchemy.dialects.postgresql import insert
from connection import AsyncSessionLocal
from models import User


async def get_or_create_user(telegram_id: int, name: str,) -> int:

    stmt = insert(User).values(
        telegram_id=telegram_id,
        name=name,
        memory={"schema_version": 1}
    )

    stmt = stmt.on_conflict_do_update(
        index_elements=[User.telegram_id],
        set_={
            "name": stmt.excluded.name,
            "updated_at": func.now()
        }
    ).returning(User.id)

    async with AsyncSessionLocal.begin() as session:
        result = await session.execute(stmt)
        return result.scalar_one()


async def get_user_memory(telegram_id: int) -> dict:
    async with AsyncSessionLocal() as session:
        stmt = select(User.memory).where(
            User.telegram_id == telegram_id
        )

        memory = await session.scalar(stmt)
        return memory if memory is not None else {}


async def update_user_memory(telegram_id: int, changes: dict) -> None:

    async with AsyncSessionLocal.begin() as session:

        stmt = (
            select(User)
            .where(User.telegram_id == telegram_id)
            .with_for_update()
        )

        user = await session.scalar(stmt)

        if user is None:
            raise ValueError(
                f"Пользователь {telegram_id} не найден"
            )

        user.memory = merge_dicts(
            user.memory,
            changes
        )

        user.updated_at = func.now()


def merge_dicts(old: dict, new: dict) -> dict:
    result = old.copy()

    for key, value in new.items():
        if (
            isinstance(value, dict)
            and isinstance(result.get(key), dict)
        ):
            result[key] = merge_dicts(
                result[key],
                value
            )
        else:
            result[key] = value

    return result


async def save_user_phone(
    telegram_id: int,
    phone_number: str
) -> None:

    phone_number = phone_number.strip()

    if not phone_number or len(phone_number) > 32:
        raise ValueError("Некорректный номер телефона")

    async with AsyncSessionLocal.begin() as session:
        stmt = (
            update(User)
            .where(User.telegram_id == telegram_id)
            .values(
                phone_number=phone_number,
                updated_at=func.now()
            )
            .returning(User.id)
        )

        user_id = await session.scalar(stmt)

        if user_id is None:
            raise ValueError("Пользователь не найден")


async def get_user_profile(
    telegram_id: int
) -> dict | None:

    async with AsyncSessionLocal() as session:
        stmt = select(User).where(
            User.telegram_id == telegram_id
        )

        user = await session.scalar(stmt)

        if user is None:
            return None

        return {
            "id": user.id,
            "telegram_id": user.telegram_id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "username": user.username,
            "phone_number": user.phone_number
        }
