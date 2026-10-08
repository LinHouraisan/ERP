from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Index, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, Identity


class SalesOrder(Identity, Base):
    __tablename__ = 'sales_orders'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('store_id', 'request_key'),
        Index('uq_sales_acceptance_active', 'source_acceptance_id', unique=True, postgresql_where=text("status <> 'CANCELLED'")),
        ForeignKeyConstraint(['customer_id', 'store_id'], ['app.customers.id', 'app.customers.store_id']),
        ForeignKeyConstraint(['source_service_id', 'store_id'], ['app.service_sessions.id', 'app.service_sessions.store_id']),
        ForeignKeyConstraint(['source_acceptance_id', 'store_id'], ['app.acceptances.id', 'app.acceptances.store_id']),
        ForeignKeyConstraint(['actor_id', 'store_id'], ['app.users.id', 'app.users.store_id']),
        ForeignKeyConstraint(['confirmed_by', 'store_id'], ['app.users.id', 'app.users.store_id']),
        CheckConstraint("status IN ('DRAFT','CONFIRMED','CANCELLED')", name='ck_sales_status'),
        CheckConstraint("stock_status IN ('NONE','RESERVED','SHIPPED')", name='ck_sales_stock_status'),
        CheckConstraint('total >= 0', name='ck_sales_total'))
    store_id: Mapped[UUID]
    customer_id: Mapped[UUID]
    source_service_id: Mapped[UUID | None]
    source_acceptance_id: Mapped[UUID | None]
    actor_id: Mapped[UUID]
    confirmed_by: Mapped[UUID | None]
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default='DRAFT')
    stock_status: Mapped[str] = mapped_column(String(16), default='NONE')
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    request_key: Mapped[str] = mapped_column(String(120))
    input_hash: Mapped[str] = mapped_column(String(64))


class SalesLine(Identity, Base):
    __tablename__ = 'sales_lines'
    __table_args__ = (UniqueConstraint('order_id', 'product_id'),
        ForeignKeyConstraint(['order_id', 'store_id'], ['app.sales_orders.id', 'app.sales_orders.store_id']),
        ForeignKeyConstraint(['product_id', 'store_id'], ['app.products.id', 'app.products.store_id']),
        ForeignKeyConstraint(['policy_version_id', 'store_id'], ['app.policy_versions.id', 'app.policy_versions.store_id']),
        CheckConstraint('quantity > 0 AND unit_price >= 0 AND discount BETWEEN 0 AND unit_price AND amount >= 0', name='ck_sales_line_money'))
    store_id: Mapped[UUID]
    order_id: Mapped[UUID]
    product_id: Mapped[UUID]
    policy_version_id: Mapped[UUID]
    quantity: Mapped[int]
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    discount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    snapshot: Mapped[dict] = mapped_column(JSONB)


class DayClose(Identity, Base):
    __tablename__ = 'day_closes'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('store_id', 'request_key'),
        ForeignKeyConstraint(['cashier_id', 'store_id'], ['app.users.id', 'app.users.store_id']),
        ForeignKeyConstraint(['actor_id', 'store_id'], ['app.users.id', 'app.users.store_id']),
        ForeignKeyConstraint(['confirmed_by', 'store_id'], ['app.users.id', 'app.users.store_id']))
    store_id: Mapped[UUID]
    cashier_id: Mapped[UUID]
    actor_id: Mapped[UUID]
    business_day: Mapped[date]
    request_key: Mapped[str] = mapped_column(String(120))
    input_hash: Mapped[str] = mapped_column(String(64))
    totals: Mapped[dict] = mapped_column(JSONB)
    counted_cash: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    difference: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    confirmed_by: Mapped[UUID | None]
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str] = mapped_column(String(1000), default='')


class Payment(Identity, Base):
    __tablename__ = 'payments'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('order_id'),
        ForeignKeyConstraint(['order_id', 'store_id'], ['app.sales_orders.id', 'app.sales_orders.store_id']),
        ForeignKeyConstraint(['cashier_id', 'store_id'], ['app.users.id', 'app.users.store_id']),
        ForeignKeyConstraint(['day_close_id', 'store_id'], ['app.day_closes.id', 'app.day_closes.store_id']),
        CheckConstraint("status IN ('PENDING','UNKNOWN','SUCCESS','FAILED')", name='ck_payment_status'),
        CheckConstraint("method IN ('CASH','CARD','WECHAT','ALIPAY') AND amount >= 0", name='ck_payment_money'))
    store_id: Mapped[UUID]
    order_id: Mapped[UUID]
    cashier_id: Mapped[UUID]
    day_close_id: Mapped[UUID | None]
    external_request_id: Mapped[UUID] = mapped_column(default=uuid4, unique=True)
    external_payment_id: Mapped[UUID | None] = mapped_column(unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    method: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default='PENDING')
    scenario: Mapped[str] = mapped_column(String(32))
    allocations: Mapped[list] = mapped_column(JSONB)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(200))


class SalesEvent(Identity, Base):
    __tablename__ = 'sales_events'
    __table_args__ = (
        ForeignKeyConstraint(['order_id', 'store_id'], ['app.sales_orders.id', 'app.sales_orders.store_id']),
        ForeignKeyConstraint(['actor_id', 'store_id'], ['app.users.id', 'app.users.store_id']))
    store_id: Mapped[UUID]
    order_id: Mapped[UUID]
    actor_id: Mapped[UUID]
    action: Mapped[str] = mapped_column(String(40))
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
