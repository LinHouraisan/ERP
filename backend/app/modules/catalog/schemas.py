from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


class ProductInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=100)
    kind: Literal['PACKAGE', 'SERVICE', 'GOODS'] = 'PACKAGE'
    tracking: Literal['NONE', 'QUANTITY', 'SERIAL'] = 'NONE'
    sku: str | None = Field(default=None, min_length=1, max_length=80, pattern=r'^[A-Z0-9_-]+$')

    @model_validator(mode='after')
    def tracking_mode(self):
        if (self.kind == 'GOODS') != (self.tracking != 'NONE'):
            raise ValueError('实物商品须选择数量或序列号管理，套餐和服务不计库存')
        return self


class ProductOut(ProductInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    simulated: bool


class Conditions(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal[1] = 1
    verified_required: bool = True
    new_customer_only: bool = False
    minimum_tenure_months: int = Field(default=0, ge=0)
    excludes_discount: str | None = None
    region: str | None = Field(default=None, max_length=80)
    sale_discount: Money = Decimal('0.00')
    receipt_category: Literal['OPERATING', 'COLLECTION', 'DEPOSIT'] = 'OPERATING'


class PolicyInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    valid_from: date
    valid_to: date
    monthly_fee: Money | None
    one_time_fee: Money | None
    contract_months: int = Field(ge=0, le=120)
    promotion_months: int | None = Field(default=None, ge=1, le=120)
    broadband: bool | None
    conditions: Conditions = Field(default_factory=Conditions)
    source: str = Field(min_length=1, max_length=255)

    @model_validator(mode='after')
    def dates(self):
        if self.valid_to < self.valid_from:
            raise ValueError('有效期结束日期不能早于开始日期')
        return self


class PolicyOut(PolicyInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    product_id: UUID
    version: int
    status: str
