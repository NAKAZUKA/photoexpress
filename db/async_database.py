from sqlalchemy.ext.asyncio import (
    async_sessionmaker, AsyncSession, create_async_engine
)
from sqlalchemy.orm import declarative_base

DATABASE_URL = "sqlite+aiosqlite:///db/photoexpress.sqlite"

async_engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    expire_on_commit=False,
)

Base = declarative_base()

async def get_async_session():
    async with AsyncSessionLocal() as session:
        yield session
