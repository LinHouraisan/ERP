from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from decimal import Decimal
from uuid import UUID


class AccountQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    number: str = Field(pattern=r'^199[0-9]{8}$')
    account_type: Literal['MOBILE'] = 'MOBILE'


class AcceptanceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    external_request_id: UUID
    account_id: UUID
    policy_version_id: UUID
    product_id: UUID
    product_name: str = Field(min_length=1, max_length=100)
    monthly_fee: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    one_time_fee: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    contract_months: int = Field(ge=0, le=120)
    broadband: bool | None = None
    expected_source_time: datetime


class ScenarioInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    scenario: Literal['NORMAL','QUERY_TIMEOUT','SUCCESS_TIMEOUT','PROCESSING','REJECT','LOOKUP_FAILURE']
