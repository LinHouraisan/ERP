from typing import Annotated
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.modules.catalog.schemas import Money

Quantity = Annotated[int, Field(strict=True, ge=1, le=10000)]
RequestKey = Annotated[str, Field(min_length=1, max_length=120)]


class SupplierInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=100)
    contact: str = Field(default='', max_length=200)


class PurchaseItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    product_id: UUID
    quantity: Quantity
    unit_cost: Money


class PurchaseInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_key: RequestKey
    supplier_id: UUID
    lines: list[PurchaseItem] = Field(min_length=1, max_length=50)

    @model_validator(mode='after')
    def unique_products(self):
        if len({x.product_id for x in self.lines}) != len(self.lines):
            raise ValueError('同一商品合并为一行')
        return self


class ReceiptItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    line_id: UUID
    quantity: Quantity
    serials: list[Annotated[str, Field(min_length=1, max_length=100, pattern=r'^\S+$')]] = Field(default_factory=list, max_length=10000)


class ReceiptInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_key: RequestKey
    lines: list[ReceiptItem] = Field(min_length=1, max_length=50)

    @model_validator(mode='after')
    def unique_lines(self):
        serials = [s for row in self.lines for s in row.serials]
        if len({x.line_id for x in self.lines}) != len(self.lines) or len(set(serials)) != len(serials):
            raise ValueError('收货行与序列号不能重复')
        return self


def supplier_view(row):
    return {'id': row.id, 'name': row.name, 'contact': row.contact}


def receipt_view(row):
    return {'id': row.id, 'purchase_id': row.purchase_id, 'actor_id': row.actor_id, 'created_at': row.created_at, 'lines': row.lines}
