from datetime import date
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.modules.catalog.schemas import Money


class CasePolicy(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    status: Literal['PUBLISHED'] = 'PUBLISHED'
    monthly_fee: Money | None
    one_time_fee: Money | None
    contract_months: int = Field(ge=0)
    valid_from: date
    valid_to: date
    conditions: dict = Field(default_factory=dict)


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    split: Literal['dev','holdout']
    category: str
    review_status: Literal['PENDING','CONFIRMED']
    reviewer: str | None = None
    review_note: str
    business_date: date
    target_type: Literal['RECOMMENDATION','MARKETING','REPLY']
    facts: dict
    demand: dict
    policies: list[CasePolicy]
    candidate: dict | None = None
    text: str
    expected_issue_ids: list[str]
