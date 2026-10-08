from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.integrations.boss import AccountFacts


class AccountQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    number: str = Field(pattern=r'^199[0-9]{8}$')
    account_type: Literal['MOBILE'] = 'MOBILE'


class SnapshotOut(BaseModel):
    snapshot_id: UUID
    account_id: UUID
    source: str
    source_time: datetime
    fetched_at: datetime
    completeness: str
    payload: AccountFacts


def snapshot_view(row):
    return SnapshotOut(snapshot_id=row.id, account_id=row.account_id, source=row.source, source_time=row.source_time,
        fetched_at=row.created_at, completeness=row.completeness, payload=row.payload)
