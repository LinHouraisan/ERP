from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, Identity


class AfterSale(Identity, Base):
    __tablename__ = 'after_sales'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('store_id', 'request_key'),
        ForeignKeyConstraint(['order_id', 'store_id'], ['app.sales_orders.id', 'app.sales_orders.store_id']),
        ForeignKeyConstraint(['actor_id', 'store_id'], ['app.users.id', 'app.users.store_id']),
        ForeignKeyConstraint(['approved_by', 'store_id'], ['app.users.id', 'app.users.store_id']),
        ForeignKeyConstraint(['day_close_id', 'store_id'], ['app.day_closes.id', 'app.day_closes.store_id']),
        CheckConstraint("status IN ('REQUESTED','APPROVED','REJECTED','CLOSED')", name='ck_after_sale_status'),
        CheckConstraint("refund_status IN ('NONE','PENDING','UNKNOWN','SUCCESS','FAILED') AND amount >= 0", name='ck_refund_status'),
        CheckConstraint("kind IN ('RETURN_REFUND','REFUND_ONLY','CANCEL_UNSHIPPED')", name='ck_after_sale_kind'))
    store_id: Mapped[UUID]
    order_id: Mapped[UUID]
    actor_id: Mapped[UUID]
    approved_by: Mapped[UUID | None]
    day_close_id: Mapped[UUID | None]
    request_key: Mapped[str] = mapped_column(String(120))
    input_hash: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(16), default='REQUESTED')
    lines: Mapped[list] = mapped_column(JSONB)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    refund_status: Mapped[str] = mapped_column(String(16), default='NONE')
    external_request_id: Mapped[UUID] = mapped_column(default=uuid4, unique=True)
    external_refund_id: Mapped[UUID | None] = mapped_column(unique=True)
    scenario: Mapped[str] = mapped_column(String(32))
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stock_processed: Mapped[bool] = mapped_column(default=False)
    return_evidence: Mapped[dict] = mapped_column(JSONB, default=dict)
    service_resolution: Mapped[str] = mapped_column(String(1000), default='')
    last_error: Mapped[str | None] = mapped_column(String(200))


class AfterSaleEvent(Identity, Base):
    __tablename__ = 'after_sale_events'
    __table_args__ = (
        ForeignKeyConstraint(['after_sale_id', 'store_id'], ['app.after_sales.id', 'app.after_sales.store_id']),
        ForeignKeyConstraint(['actor_id', 'store_id'], ['app.users.id', 'app.users.store_id']))
    store_id: Mapped[UUID]
    after_sale_id: Mapped[UUID]
    actor_id: Mapped[UUID]
    action: Mapped[str] = mapped_column(String(32))
    detail: Mapped[dict] = mapped_column(JSONB)


class Reversal(Identity, Base):
    __tablename__ = 'telecom_reversals'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('acceptance_id'), UniqueConstraint('store_id', 'request_key'),
        ForeignKeyConstraint(['acceptance_id', 'store_id'], ['app.acceptances.id', 'app.acceptances.store_id']),
        ForeignKeyConstraint(['actor_id', 'store_id'], ['app.users.id', 'app.users.store_id']),
        ForeignKeyConstraint(['approved_by', 'store_id'], ['app.users.id', 'app.users.store_id']),
        CheckConstraint("status IN ('REQUESTED','APPROVED','REJECTED','PENDING','UNKNOWN','SUCCESS','FAILED')", name='ck_reversal_status'))
    store_id: Mapped[UUID]
    acceptance_id: Mapped[UUID]
    actor_id: Mapped[UUID]
    approved_by: Mapped[UUID | None]
    request_key: Mapped[str] = mapped_column(String(120))
    input_hash: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(1000))
    scenario: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default='REQUESTED')
    external_request_id: Mapped[UUID] = mapped_column(default=uuid4, unique=True)
    external_reversal_id: Mapped[UUID | None] = mapped_column(unique=True)
    last_error: Mapped[str | None] = mapped_column(String(255))
    resolution: Mapped[str] = mapped_column(String(1000), default='')


class ReversalEvent(Identity, Base):
    __tablename__ = 'reversal_events'
    __table_args__ = (
        ForeignKeyConstraint(['reversal_id', 'store_id'], ['app.telecom_reversals.id', 'app.telecom_reversals.store_id']),
        ForeignKeyConstraint(['actor_id', 'store_id'], ['app.users.id', 'app.users.store_id']))
    store_id: Mapped[UUID]
    reversal_id: Mapped[UUID]
    actor_id: Mapped[UUID]
    action: Mapped[str] = mapped_column(String(32))
    detail: Mapped[dict] = mapped_column(JSONB)
