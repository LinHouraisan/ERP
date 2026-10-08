from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.modules.catalog.schemas import Money
from app.modules.inventory.schemas import RequestKey


class RefundLine(BaseModel):
    model_config = ConfigDict(extra='forbid')
    line_id: UUID
    refund_amount: Money
    return_quantity: int = Field(default=0, ge=0, le=10000)


class AfterSaleInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_key: RequestKey
    order_id: UUID
    kind: Literal['RETURN_REFUND', 'REFUND_ONLY', 'CANCEL_UNSHIPPED']
    reason: str = Field(min_length=1, max_length=1000)
    scenario: Literal['NORMAL', 'SUCCESS_TIMEOUT', 'DECLINED'] = 'NORMAL'
    lines: list[RefundLine] = Field(min_length=1, max_length=50)

    @model_validator(mode='after')
    def unique_lines(self):
        if len({x.line_id for x in self.lines}) != len(self.lines): raise ValueError('同一原单行须合并')
        if not any(x.refund_amount or x.return_quantity for x in self.lines): raise ValueError('须有退款或退货数量')
        return self


class Note(BaseModel):
    model_config = ConfigDict(extra='forbid')
    note: str = Field(min_length=1, max_length=1000)


class Review(Note):
    decision: Literal['APPROVE', 'REJECT']


class FailedResolution(Note):
    replacement_after_sale_id: UUID | None = None


class ReturnLine(BaseModel):
    model_config = ConfigDict(extra='forbid')
    line_id: UUID
    serials: list[str] = Field(default_factory=list, max_length=10000)


class Receive(Note):
    lines: list[ReturnLine] = Field(min_length=1, max_length=50)

    @model_validator(mode='after')
    def unique_lines(self):
        if len({x.line_id for x in self.lines}) != len(self.lines): raise ValueError('退货行重复')
        serials = [s for x in self.lines for s in x.serials]
        if len(set(serials)) != len(serials): raise ValueError('退货序列号重复')
        return self
