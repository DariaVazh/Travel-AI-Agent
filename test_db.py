import asyncio

from sqlalchemy import text

from database.connection import engine


async def main():
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT current_database(), current_user")
        )

        print("Подключение успешно!")
        print(result.one())

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())