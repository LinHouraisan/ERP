import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy import text

from app.core.config import Settings
from app.core.db import Base
from app import models


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata,
                      version_table_schema='app', include_schemas=True,
                      include_name=lambda name, type_, parent: type_ != 'schema' or name == 'app')
    with context.begin_transaction():
        context.run_migrations()


async def run():
    engine = create_async_engine(Settings().database_url, poolclass=NullPool)
    async with engine.connect() as connection:
        await connection.execute(text('SET search_path TO public'))
        await connection.commit()
        connection.dialect.default_schema_name = 'public'
        await connection.run_sync(migrate)
    await engine.dispose()


asyncio.run(run())
