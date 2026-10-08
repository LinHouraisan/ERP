from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator


class QualityInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    target_type: Literal['RECOMMENDATION', 'MARKETING', 'REPLY']
    target_id: UUID | None = None
    candidate_id: UUID | None = None
    text: str = Field(default='', max_length=12000)
    policy_version_ids: list[UUID] = Field(default_factory=list, max_length=10)


class RecommendationCheck(BaseModel):
    model_config = ConfigDict(extra='forbid')
    candidate_id: UUID
    text: str = Field(default='', max_length=12000)


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    decision: Literal['CONFIRM', 'REJECT', 'REVISE']
    reason: str = Field(min_length=1, max_length=2000)
    revised_text: str | None = Field(default=None, max_length=12000)

    @model_validator(mode='after')
    def require_revision(self):
        if self.decision == 'REVISE' and not (self.revised_text or '').strip():
            raise ValueError('请填写修订稿')
        return self


def quality_view(row):
    return {'quality_check_id': row.id, **{k: getattr(row, k) for k in ('target_type', 'target_id', 'candidate_id', 'input_hash', 'status', 'findings', 'text', 'policy_version_ids', 'rule_version', 'ai_run_id', 'supersedes_id', 'created_at')}}
