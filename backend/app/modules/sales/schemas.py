from datetime import date
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.modules.inventory.schemas import Quantity, RequestKey
from app.modules.finance.schemas import SignedMoney


class SalesItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    policy_version_id: UUID
    quantity: Quantity


class SalesInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_key: RequestKey
    customer_id: UUID
    source_service_id: UUID | None = None
    source_acceptance_id: UUID | None = None
    lines: list[SalesItem] = Field(min_length=1, max_length=50)

    @model_validator(mode='after')
    def unique_lines(self):
        if len({x.policy_version_id for x in self.lines}) != len(self.lines): raise ValueError('商品合并为一行')
        return self


class SalesAssistInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_key: RequestKey
    customer_id: UUID
    source_service_id: UUID | None = None
    text: str = Field(min_length=1, max_length=2000)


class PayInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    method: Literal['CASH', 'CARD', 'WECHAT', 'ALIPAY']
    scenario: Literal['NORMAL', 'SUCCESS_TIMEOUT', 'DECLINED'] = 'NORMAL'


class CloseInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_key: RequestKey
    business_day: date
    cashier_id: UUID
    counted_cash: SignedMoney


class CloseReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    note: str = Field(min_length=1, max_length=1000)


def payment_view(row):
    return {'id': row.id, 'order_id': row.order_id, 'status': row.status, 'method': row.method, 'amount': str(row.amount),
        'cashier_id': row.cashier_id, 'external_request_id': row.external_request_id, 'external_payment_id': row.external_payment_id,
        'allocations': row.allocations, 'settled_at': row.settled_at, 'last_error': row.last_error, 'simulated': True}


def close_view(row):
    return {'id': row.id, 'cashier_id': row.cashier_id, 'business_day': row.business_day, 'totals': row.totals,
        'counted_cash': str(row.counted_cash), 'difference': str(row.difference), 'confirmed_by': row.confirmed_by,
        'confirmed_at': row.confirmed_at, 'note': row.note, 'created_at': row.created_at}
