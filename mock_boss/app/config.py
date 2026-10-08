from contextlib import asynccontextmanager
from pathlib import Path
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[2]/'.env', extra='ignore')
    mock_database_url: str = 'postgresql+asyncpg://localhost/erp_dev'
    boss_token: SecretStr = SecretStr('')
    app_env: str = 'development'


@asynccontextmanager
async def session_scope():
    engine = create_async_engine(Settings().mock_database_url, poolclass=NullPool)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            yield db
    finally:
        await engine.dispose()
