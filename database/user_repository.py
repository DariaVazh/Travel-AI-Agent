from sqlalchemy import select, func
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


# async def save_user_memory(telegram_id: int, memory: dict) -> None:
#     stmt = insert(User).values(
#         telegram_id=telegram_id,
#         memory=memory
#     )
#
#     stmt = stmt.on_conflict_do_update(
#         index_elements=[User.telegram_id],
#         set_={
#             "memory": stmt.excluded.memory,
#             "updated_at": func.now()
#         }
#     )
#
#     async with AsyncSessionLocal.begin() as session:
#         await session.execute(stmt)


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
