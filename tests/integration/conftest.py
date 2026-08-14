import os

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest_asyncio.fixture
async def db_session():
    if not TEST_DATABASE_URL:
        import pytest

        pytest.skip("TEST_DATABASE_URL is not set (integration tests require PostgreSQL)")
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()
