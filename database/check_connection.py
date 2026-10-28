import asyncio

from sqlalchemy import text
from database.connection import engine


async def main():
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT current_database()")
            )
            print("Подключение успешно!")
            print("База данных:", result.scalar())
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())