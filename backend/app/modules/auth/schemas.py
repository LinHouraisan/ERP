from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Login(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class CurrentUser(BaseModel):
    user_id: UUID
    store_id: UUID
    username: str
    role: Literal['STAFF', 'MANAGER', 'ADMIN', 'WAREHOUSE', 'INSTALLER', 'FINANCE']
    csrf_token: str
