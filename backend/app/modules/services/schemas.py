from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class ServiceCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    category: Literal['PLAN', 'FAULT', 'OTHER'] = 'PLAN'


class ServiceOut(BaseModel):
    service_id: UUID
    category: str
    status: str
    account_id: UUID | None
    customer_id: UUID | None
    started_at: datetime
    ended_at: datetime | None
    preset: bool


def service_view(row):
    return ServiceOut(service_id=row.id, category=row.category, status=row.status, account_id=row.account_id, customer_id=row.customer_id,
                      started_at=row.created_at, ended_at=row.ended_at, preset=row.preset)


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    service_id: UUID
    title: str = Field(min_length=1, max_length=200)
    owner_role: Literal['STAFF', 'MANAGER']


class TaskTransition(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['IN_PROGRESS', 'CLOSED', 'CANCELLED']
    note: str = Field(min_length=1, max_length=2000)


class TaskOut(TaskCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    status: str
    note: str
