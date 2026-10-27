
import asyncio

from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from database.connection import engine
from database.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Структура наших SQLAlchemy-моделей
target_metadata = Base.metadata


def include_name(name, type_, parent_names):
    # Не трогаем посторонние таблицы в общей БД
    if type_ == "table":
        return name in target_metadata.tables

    return True


def do_run_migrations(connection: Connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_name=include_name
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    try:
        async with engine.connect() as connection:
            await connection.run_sync(
                do_run_migrations
            )
    finally:
        await engine.dispose()


def run_migrations_online():
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    raise RuntimeError(
        "Offline-миграции пока не настроены"
    )
else:
    run_migrations_online()
