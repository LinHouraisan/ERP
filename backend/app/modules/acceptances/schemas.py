from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class AcceptanceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    recommendation_id: UUID
    candidate_id: UUID


class Confirmation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int = Field(ge=1)
    quality_check_id: UUID


def acceptance_view(row):
    return {'acceptance_id': row.id, **{k: getattr(row, k) for k in ('service_id', 'recommendation_id', 'candidate_id',
        'external_request_id', 'external_order_id', 'status', 'expected_version', 'quality_check_id', 'confirmed_at', 'last_error', 'updated_at')}}
