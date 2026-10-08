from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from app.modules.inventory.schemas import Quantity, RequestKey


class InstallationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_order_id: UUID | None = None
    source_acceptance_id: UUID | None = None
    address: str = Field(min_length=1, max_length=300)
    appointment_at: AwareDatetime

    @model_validator(mode='after')
    def source(self):
        if (self.source_order_id is None) == (self.source_acceptance_id is None): raise ValueError('请选择一个来源订单或受理')
        return self


class DispatchInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    installer_id: UUID
    note: str = Field(default='', max_length=1000)


class AppointmentInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    appointment_at: AwareDatetime
    note: str = Field(min_length=1, max_length=1000)


class MaterialInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    product_id: UUID
    quantity: Quantity


class ReturnedMaterial(MaterialInput):
    serials: list[str] = Field(default_factory=list, max_length=10000)


class CancelInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    note: str = Field(min_length=1, max_length=1000)
    materials_confirmed: bool = Field(default=False, strict=True)
    returned_materials: list[ReturnedMaterial] = Field(default_factory=list, max_length=50)

    @model_validator(mode='after')
    def unique_products(self):
        if len({x.product_id for x in self.returned_materials}) != len(self.returned_materials): raise ValueError('退料行重复')
        return self


class TransitionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_key: RequestKey
    action: Literal['accept', 'collect', 'arrive', 'install', 'complete']
    note: str = Field(min_length=1, max_length=2000)
    customer_accepted: bool = Field(default=False, strict=True)
    materials: list[MaterialInput] = Field(default_factory=list, max_length=50)

    @model_validator(mode='after')
    def material_action(self):
        if self.materials and self.action != 'collect': raise ValueError('仅领料时可填写耗材')
        if len({x.product_id for x in self.materials}) != len(self.materials): raise ValueError('耗材合并为一行')
        return self


def view(row):
    return {'id': row.id, 'source_order_id': row.source_order_id, 'source_acceptance_id': row.source_acceptance_id,
        'customer_id': row.customer_id, 'installer_id': row.installer_id, 'address': row.address, 'appointment_at': row.appointment_at,
        'status': row.status, 'materials': row.materials, 'completed_at': row.completed_at, 'created_at': row.created_at}
