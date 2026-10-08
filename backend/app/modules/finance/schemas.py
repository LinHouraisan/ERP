from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.modules.catalog.schemas import Money
from app.modules.inventory.schemas import RequestKey

Period = Annotated[str, Field(pattern=r'^\d{4}-(0[1-9]|1[0-2])$')]
Rate = Annotated[Decimal, Field(ge=0, le=1, max_digits=8, decimal_places=6)]
SignedMoney = Annotated[Decimal, Field(max_digits=12, decimal_places=2)]


class RuleInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    business_type: Literal['SALE', 'TELECOM', 'INSTALLATION']
    valid_from: date
    valid_to: date
    fixed_amount: Money = Decimal('0.00')
    rate: Rate = Decimal('0')
    employee_rate: Rate = Decimal('0')
    settlement_condition: Literal['SOURCE_COMPLETE', 'BILL_MATCHED'] = 'BILL_MATCHED'

    @model_validator(mode='after')
    def dates(self):
        if self.valid_to < self.valid_from: raise ValueError('规则日期无效')
        return self


class AccrualInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_type: Literal['SALE', 'TELECOM', 'INSTALLATION']
    source_id: UUID


class BillItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    business_no: str = Field(min_length=1, max_length=100)
    earning_period: Period | None = None
    line_key: str = Field(default='PRIMARY', min_length=1, max_length=100)
    is_final: bool = Field(default=True, strict=True)
    amount: SignedMoney
    received_amount: SignedMoney | None = None


class MockBillInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_key: RequestKey
    period: Period


class BillInput(MockBillInput):
    source: str = Field(min_length=1, max_length=200)
    rows: list[BillItem] = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def unique_rows(self):
        if len({(x.business_no,x.line_key) for x in self.rows}) != len(self.rows): raise ValueError('同一账期的业务号和账单行号不能重复')
        return self


def rule_view(row):
    return {'id': row.id, 'business_type': row.business_type, 'version': row.version, 'status': row.status,
        'valid_from': str(row.valid_from), 'valid_to': str(row.valid_to), 'fixed_amount': str(row.fixed_amount),
        'rate': str(row.rate), 'employee_rate': str(row.employee_rate), 'settlement_condition': row.settlement_condition}
