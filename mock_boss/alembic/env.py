import asyncio
from alembic import context
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from app.config import Settings
from app.models import Base


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, version_table_schema='boss', include_schemas=True,
                      include_name=lambda name, type_, parent: type_ != 'schema' or name == 'boss')
    with context.begin_transaction(): context.run_migrations()


async def run():
    engine = create_async_engine(Settings().mock_database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        await conn.execute(text('SET search_path TO public'))
        await conn.commit()
        conn.dialect.default_schema_name = 'public'
        await conn.run_sync(migrate)
    await engine.dispose()

asyncio.run(run())
