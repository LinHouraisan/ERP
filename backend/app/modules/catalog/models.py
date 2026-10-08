from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, ForeignKeyConstraint, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Identity


class Product(Identity, Base):
    __tablename__ = 'products'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('store_id', 'sku'), CheckConstraint("kind IN ('PACKAGE','SERVICE','GOODS')", name='ck_products_kind'),
        CheckConstraint("(kind = 'GOODS' AND tracking IN ('QUANTITY','SERIAL')) OR (kind <> 'GOODS' AND tracking = 'NONE')", name='ck_products_tracking'))
    store_id: Mapped[UUID] = mapped_column(ForeignKey('app.stores.id'))
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(16), default='PACKAGE')
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    tracking: Mapped[str] = mapped_column(String(16), default='NONE', server_default='NONE')
    sku: Mapped[str | None] = mapped_column(String(80))


class PolicyVersion(Identity, Base):
    __tablename__ = 'policy_versions'
    __table_args__ = (
        UniqueConstraint('id', 'store_id'), UniqueConstraint('product_id', 'version'),
        ForeignKeyConstraint(['product_id', 'store_id'], ['app.products.id', 'app.products.store_id']),
        CheckConstraint('valid_to >= valid_from', name='ck_policy_dates'),
        CheckConstraint('monthly_fee >= 0 AND one_time_fee >= 0 AND contract_months >= 0', name='ck_policy_fees'),
        CheckConstraint("status IN ('DRAFT','PUBLISHED')", name='ck_policy_status'),
    )
    store_id: Mapped[UUID]
    product_id: Mapped[UUID]
    version: Mapped[int]
    status: Mapped[str] = mapped_column(String(16), default='DRAFT')
    valid_from: Mapped[date]
    valid_to: Mapped[date]
    monthly_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    one_time_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    contract_months: Mapped[int]
    promotion_months: Mapped[int | None]
    broadband: Mapped[bool | None]
    conditions: Mapped[dict] = mapped_column(JSONB, default=lambda: {'schema_version': 1})
    source: Mapped[str] = mapped_column(String(255))
