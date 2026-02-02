import pytest
import os
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from database import Base, Monitor, get_all_active_monitors
import database

# Use in-memory database for tests
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

@pytest.fixture
async def override_db():
    """Overrides the database engine for tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    
    # Patch database.engine and async_session
    database.engine = engine
    database.async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield
    
    await engine.dispose()

@pytest.mark.asyncio
async def test_add_monitor(override_db):
    async with database.async_session() as session:
        monitor = Monitor(user_id=123, url="http://example.com", frequency=30)
        session.add(monitor)
        await session.commit()

        result = await session.execute(select(Monitor))
        monitors = result.scalars().all()
        assert len(monitors) == 1
        assert monitors[0].url == "http://example.com"
        assert monitors[0].is_active is True 
        assert monitors[0].is_active is True

@pytest.mark.asyncio
async def test_get_all_active_monitors(override_db):
    async with database.async_session() as session:
        m1 = Monitor(user_id=1, url="http://a.com", is_active=True)
        m2 = Monitor(user_id=2, url="http://b.com", is_active=False)
        session.add_all([m1, m2])
        await session.commit()

    monitors = await get_all_active_monitors()
    assert len(monitors) == 1
    assert monitors[0].url == "http://a.com"

    assert monitors[0].url == "http://a.com"


