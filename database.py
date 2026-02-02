import os
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, select
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Ensure data directory exists if using file-based DB

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///data/bot_database.sqlite3")

# Ensure data directory exists if using file-based DB
if "sqlite" in DATABASE_URL and "/data/" in DATABASE_URL:
    os.makedirs("data", exist_ok=True)  # pragma: no cover

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class Monitor(Base):
    __tablename__ = "monitors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    url: Mapped[str] = mapped_column(String)
    frequency: Mapped[int] = mapped_column(Integer, default=60)  # in minutes
    last_checked: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<Monitor(user_id={self.user_id}, url='{self.url}', freq={self.frequency})>"


async def init_db():
    """Initializes the database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_all_active_monitors():
    """Retrieves all active monitors."""
    async with async_session() as session:
        result = await session.execute(select(Monitor).where(Monitor.is_active.is_(True)))
        return result.scalars().all()
