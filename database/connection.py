import os
import ssl

from dotenv import load_dotenv
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker
)

load_dotenv()

DATABASE_URL = URL.create(
    drivername="postgresql+asyncpg",
    username=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    host=os.environ["DB_HOST"],
    port=int(os.environ["DB_PORT"]),
    database=os.environ["DB_NAME"]
)

engine = create_async_engine(
    DATABASE_URL,
    connect_args={"ssl": ssl.create_default_context()},
    pool_pre_ping=True
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False
)