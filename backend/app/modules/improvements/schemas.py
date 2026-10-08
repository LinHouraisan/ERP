from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class ProposalInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    snapshot_id: UUID
    request_key: str = Field(min_length=8, max_length=120)


class ManualTask(BaseModel):
    model_config = ConfigDict(extra='forbid')
    snapshot_id: UUID
    suggestion: str = Field(min_length=1, max_length=2000)


class Verification(BaseModel):
    model_config = ConfigDict(extra='forbid')
    before_snapshot_id: UUID
    after_snapshot_id: UUID
    conditions_changed: str = Field(min_length=1, max_length=2000)
    result: str = Field(min_length=1, max_length=2000)
    unresolved_issues: str = Field(default='', max_length=2000)


class TaskTransition(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['APPROVED','IN_PROGRESS','VERIFIED','CLOSED','REJECTED']
    reason: str = Field(min_length=1, max_length=2000)
    owner_id: UUID | None = None
    plan: str | None = Field(default=None, max_length=2000)
    target: str | None = Field(default=None, max_length=2000)
    verification: Verification | None = None


def task_view(row):
    return {k: getattr(row,k) for k in ('id','snapshot_id','ai_run_id','suggestion','status','owner_id','plan','target','verification','created_at','updated_at')}
