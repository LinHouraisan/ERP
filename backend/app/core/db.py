from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, MetaData, Uuid, make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool

from app.core.config import Settings


class Base(DeclarativeBase):
    metadata = MetaData(schema='app', naming_convention={
        'ix': 'ix_%(table_name)s_%(column_0_name)s',
        'uq': 'uq_%(table_name)s_%(column_0_name)s',
        'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
        'pk': 'pk_%(table_name)s',
    })


def utcnow():
    return datetime.now(UTC)


class Identity:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


def require_test_database(url: str):
    parsed = make_url(url)
    if parsed.drivername != 'postgresql+asyncpg' or not (parsed.database or '').startswith('erp_') or not parsed.database.endswith('_test'):
        raise ValueError('Tests require a dedicated PostgreSQL database named erp_*_test')


@asynccontextmanager
async def session_scope(url: str | None = None):
    engine = create_async_engine(url or Settings().database_url, poolclass=NullPool)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session
    finally:
        await engine.dispose()


async def get_db():
    async with session_scope() as session:
        yield session
