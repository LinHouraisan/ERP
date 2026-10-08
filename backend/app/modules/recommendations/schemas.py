from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.modules.catalog.schemas import Money


class DemandProfile(BaseModel):
    model_config = ConfigDict(extra='forbid')
    intent: Literal['REDUCE_COST', 'CHANGE_PLAN', 'KEEP_CURRENT', 'FAULT', 'CONSULT']
    budget: Money | None = None
    must_keep: list[Literal['broadband']] = Field(default_factory=list, max_length=1)
    issues: list[str] = Field(default_factory=list, max_length=10)
    missing_fields: list[str] = Field(default_factory=list, max_length=20)


class RecommendationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    snapshot_id: UUID
    demand: DemandProfile


class Candidate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    candidate_id: UUID
    product_id: UUID
    policy_version_id: UUID
    monthly_fee: Money | None
    one_time_fee: Money | None
    monthly_difference: str | None
    contract_months: int
    promotion_months: int | None
    broadband: bool | None
    eligibility: Literal['eligible', 'ineligible', 'unknown']
    evidence_ids: list[UUID]
    unresolved_needs: list[str]


class RecommendationOut(BaseModel):
    recommendation_id: UUID
    service_id: UUID
    snapshot_id: UUID
    revision: int
    demand: DemandProfile
    candidates: list[Candidate]
    outcome: Literal['OPTIONS', 'KEEP_CURRENT', 'NO_MATCH', 'NEEDS_INFO', 'SERVICE_TASK']
    missing_fields: list[str]
    service_tasks: list[str]
    rule_version: str
    input_hash: str
    prompt_version_id: UUID | None


def recommendation_view(row):
    return RecommendationOut(recommendation_id=row.id, service_id=row.service_id, snapshot_id=row.snapshot_id,
        revision=row.revision, demand=row.demand, candidates=row.candidates, outcome=row.outcome,
        missing_fields=row.missing_fields, service_tasks=row.service_tasks, rule_version=row.rule_version, input_hash=row.input_hash, prompt_version_id=row.prompt_version_id)
