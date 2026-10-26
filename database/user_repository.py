from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from connection import AsyncSessionLocal
from models import User


async def get_or_create_user(telegram_id: int) -> int:
    async with AsyncSessionLocal.begin() as session:
        stmt = (
            insert(User)
            .values(telegram_id=telegram_id, memory={})
            .on_conflict_do_nothing(
                index_elements=[User.telegram_id]
            )
            .returning(User.id)
        )

        result = await session.execute(stmt)
        user_id = result.scalar_one_or_none()

        if user_id is None:
            user_id = await session.scalar(
                select(User.id).where(
                    User.telegram_id == telegram_id
                )
            )

        if user_id is None:
            raise RuntimeError("Не удалось получить пользователя")

        return user_id


async def get_user_memory(telegram_id: int) -> dict:
    async with AsyncSessionLocal() as session:
        stmt = select(User.memory).where(
            User.telegram_id == telegram_id
        )

        memory = await session.scalar(stmt)
        return memory if memory is not None else {}


async def save_user_memory(telegram_id: int, memory: dict) -> None:
    stmt = insert(User).values(
        telegram_id=telegram_id,
        memory=memory
    )

    stmt = stmt.on_conflict_do_update(
        index_elements=[User.telegram_id],
        set_={
            "memory": stmt.excluded.memory,
            "updated_at": func.now()
        }
    )

    async with AsyncSessionLocal.begin() as session:
        await session.execute(stmt)
