from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import MetaData, Numeric, String, DateTime, CheckConstraint, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    metadata = MetaData(schema='boss')


class Account(Base):
    __tablename__ = 'accounts'
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    customer_id: Mapped[UUID]
    number: Mapped[str] = mapped_column(String(32), unique=True)
    account_type: Mapped[str] = mapped_column(String(16), default='MOBILE')
    monthly_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    facts: Mapped[dict] = mapped_column(JSONB)
    scenario: Mapped[str] = mapped_column(String(32), default='NORMAL')
    source_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Acceptance(Base):
    __tablename__ = 'acceptances'
    __table_args__ = (CheckConstraint("status IN ('PROCESSING','SUCCESS','FAILED')", name='ck_mock_status'),)
    external_request_id: Mapped[UUID] = mapped_column(primary_key=True)
    external_order_id: Mapped[UUID] = mapped_column(unique=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(ForeignKey('boss.accounts.id'))
    payload_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16))
    monthly_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    one_time_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reason: Mapped[str | None] = mapped_column(String(255))
    previous_state: Mapped[dict | None] = mapped_column(JSONB)
    applied_source_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Payment(Base):
    __tablename__ = 'payments'
    __table_args__ = (CheckConstraint("status IN ('SUCCESS','FAILED') AND amount >= 0", name='ck_mock_payment'),)
    external_request_id: Mapped[UUID] = mapped_column(primary_key=True)
    external_payment_id: Mapped[UUID] = mapped_column(unique=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(unique=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    method: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Refund(Base):
    __tablename__ = 'refunds'
    __table_args__ = (CheckConstraint("status IN ('SUCCESS','FAILED') AND amount >= 0", name='ck_mock_refund'),)
    external_request_id: Mapped[UUID] = mapped_column(primary_key=True)
    external_refund_id: Mapped[UUID] = mapped_column(unique=True, default=uuid4)
    external_payment_id: Mapped[UUID] = mapped_column(ForeignKey('boss.payments.external_payment_id'))
    payload_hash: Mapped[str] = mapped_column(String(64))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Reversal(Base):
    __tablename__ = 'reversals'
    __table_args__ = (CheckConstraint("status IN ('SUCCESS','FAILED')", name='ck_mock_reversal'),)
    external_request_id: Mapped[UUID] = mapped_column(primary_key=True)
    external_reversal_id: Mapped[UUID] = mapped_column(unique=True, default=uuid4)
    original_request_id: Mapped[UUID] = mapped_column(ForeignKey('boss.acceptances.external_request_id'), unique=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
