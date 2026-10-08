from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')
    app_env: Literal['development', 'test', 'demo'] = 'development'
    database_url: str = 'postgresql+asyncpg://localhost/erp_dev'
    boss_url: str = 'http://127.0.0.1:8001'
    boss_token: SecretStr = SecretStr('')
    web_origin: str = 'http://127.0.0.1:5173'
    cookie_secure: bool = False
    ai_mode: Literal['offline', 'deepseek'] = 'offline'
    deepseek_api_key: SecretStr = SecretStr('')
    deepseek_base_url: str = 'https://api.deepseek.com'
    deepseek_model: str = 'deepseek-flash'
    demo_password: SecretStr = SecretStr('')


def business_date():
    return datetime.now(ZoneInfo('Asia/Shanghai')).date()
