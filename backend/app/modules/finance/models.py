from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, Identity


class EarningRule(Identity, Base):
    __tablename__ = 'earning_rules'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('store_id', 'business_type', 'version'),
        CheckConstraint("business_type IN ('SALE','TELECOM','INSTALLATION') AND status IN ('DRAFT','PUBLISHED')", name='ck_earning_rule_type'),
        CheckConstraint('fixed_amount >= 0 AND rate BETWEEN 0 AND 1 AND employee_rate BETWEEN 0 AND 1 AND valid_to >= valid_from', name='ck_earning_rule_values'),
        CheckConstraint("settlement_condition IN ('SOURCE_COMPLETE','BILL_MATCHED')", name='ck_earning_rule_settlement'))
    store_id: Mapped[UUID] = mapped_column(ForeignKey('app.stores.id'))
    business_type: Mapped[str] = mapped_column(String(16))
    version: Mapped[int]
    status: Mapped[str] = mapped_column(String(16), default='DRAFT')
    valid_from: Mapped[date]
    valid_to: Mapped[date]
    fixed_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    rate: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    employee_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    settlement_condition: Mapped[str] = mapped_column(String(24))


class Earning(Identity, Base):
    __tablename__ = 'earnings'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('store_id', 'business_no', 'period'),
        UniqueConstraint('order_id'), UniqueConstraint('acceptance_id'), UniqueConstraint('installation_id'),
        ForeignKeyConstraint(['rule_id', 'store_id'], ['app.earning_rules.id', 'app.earning_rules.store_id']),
        ForeignKeyConstraint(['owner_id', 'store_id'], ['app.users.id', 'app.users.store_id']),
        ForeignKeyConstraint(['order_id', 'store_id'], ['app.sales_orders.id', 'app.sales_orders.store_id']),
        ForeignKeyConstraint(['acceptance_id', 'store_id'], ['app.acceptances.id', 'app.acceptances.store_id']),
        ForeignKeyConstraint(['installation_id', 'store_id'], ['app.installations.id', 'app.installations.store_id']),
        CheckConstraint('num_nonnulls(order_id, acceptance_id, installation_id) = 1', name='ck_earning_source'),
        CheckConstraint('expected_amount >= 0 AND commission_amount >= 0', name='ck_earning_amounts'))
    store_id: Mapped[UUID]
    rule_id: Mapped[UUID]
    owner_id: Mapped[UUID]
    order_id: Mapped[UUID | None]
    acceptance_id: Mapped[UUID | None]
    installation_id: Mapped[UUID | None]
    business_no: Mapped[str] = mapped_column(String(100))
    period: Mapped[str] = mapped_column(String(7))
    expected_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    commission_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    snapshot: Mapped[dict] = mapped_column(JSONB)


class BillBatch(Identity, Base):
    __tablename__ = 'bill_batches'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('store_id', 'request_key'),
        ForeignKeyConstraint(['actor_id', 'store_id'], ['app.users.id', 'app.users.store_id']))
    store_id: Mapped[UUID]
    actor_id: Mapped[UUID]
    request_key: Mapped[str] = mapped_column(String(120))
    input_hash: Mapped[str] = mapped_column(String(64))
    period: Mapped[str] = mapped_column(String(7))
    source: Mapped[str] = mapped_column(String(200))


class BillLine(Identity, Base):
    __tablename__ = 'bill_lines'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('store_id', 'business_no', 'period', 'line_key'),
        ForeignKeyConstraint(['batch_id', 'store_id'], ['app.bill_batches.id', 'app.bill_batches.store_id']))
    store_id: Mapped[UUID]
    batch_id: Mapped[UUID]
    business_no: Mapped[str] = mapped_column(String(100))
    period: Mapped[str] = mapped_column(String(7))
    earning_period: Mapped[str] = mapped_column(String(7))
    line_key: Mapped[str] = mapped_column(String(100), default='PRIMARY')
    is_final: Mapped[bool] = mapped_column(default=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    received_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    original: Mapped[dict] = mapped_column(JSONB)


class EarningAdjustment(Identity, Base):
    __tablename__ = 'earning_adjustments'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('earning_id', 'after_sale_id'),
        ForeignKeyConstraint(['earning_id', 'store_id'], ['app.earnings.id', 'app.earnings.store_id']),
        ForeignKeyConstraint(['after_sale_id', 'store_id'], ['app.after_sales.id', 'app.after_sales.store_id']),
        ForeignKeyConstraint(['reversal_id', 'store_id'], ['app.telecom_reversals.id', 'app.telecom_reversals.store_id']),
        ForeignKeyConstraint(['case_id', 'store_id'], ['app.reconciliation_cases.id', 'app.reconciliation_cases.store_id']),
        UniqueConstraint('case_id'),
        UniqueConstraint('earning_id', 'reversal_id', name='uq_adjustment_reversal'),
        CheckConstraint('num_nonnulls(after_sale_id, reversal_id, case_id) = 1', name='ck_adjustment_source'),
        ForeignKeyConstraint(['actor_id', 'store_id'], ['app.users.id', 'app.users.store_id']))
    store_id: Mapped[UUID]
    earning_id: Mapped[UUID]
    after_sale_id: Mapped[UUID | None]
    reversal_id: Mapped[UUID | None]
    case_id: Mapped[UUID | None]
    actor_id: Mapped[UUID]
    period: Mapped[str] = mapped_column(String(7))
    expected_delta: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    commission_delta: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reason: Mapped[str] = mapped_column(String(1000))
    snapshot: Mapped[dict] = mapped_column(JSONB)


class ReconciliationCase(Identity, Base):
    __tablename__ = 'reconciliation_cases'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('store_id', 'request_key'),
        ForeignKeyConstraint(['earning_id', 'store_id'], ['app.earnings.id', 'app.earnings.store_id']),
        ForeignKeyConstraint(['bill_line_id', 'store_id'], ['app.bill_lines.id', 'app.bill_lines.store_id']),
        ForeignKeyConstraint(['actor_id', 'store_id'], ['app.users.id', 'app.users.store_id']),
        ForeignKeyConstraint(['owner_id', 'store_id'], ['app.users.id', 'app.users.store_id']),
        ForeignKeyConstraint(['closed_by', 'store_id'], ['app.users.id', 'app.users.store_id']),
        CheckConstraint('num_nonnulls(earning_id, bill_line_id) > 0', name='ck_case_source'),
        CheckConstraint("status IN ('OPEN','CLOSED')", name='ck_case_status'))
    store_id: Mapped[UUID]
    earning_id: Mapped[UUID | None]
    bill_line_id: Mapped[UUID | None]
    actor_id: Mapped[UUID]
    owner_id: Mapped[UUID]
    request_key: Mapped[str] = mapped_column(String(120))
    input_hash: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(String(1000))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    proposed_delta: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(16), default='OPEN')
    closed_by: Mapped[UUID | None]
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict)


class Settlement(Identity, Base):
    __tablename__ = 'settlements'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('store_id', 'request_key'),
        ForeignKeyConstraint(['owner_id', 'store_id'], ['app.users.id', 'app.users.store_id']),
        ForeignKeyConstraint(['actor_id', 'store_id'], ['app.users.id', 'app.users.store_id']),
        ForeignKeyConstraint(['confirmed_by', 'store_id'], ['app.users.id', 'app.users.store_id']),
        CheckConstraint("status IN ('DRAFT','CONFIRMED') AND amount >= 0", name='ck_settlement'))
    store_id: Mapped[UUID]
    owner_id: Mapped[UUID]
    actor_id: Mapped[UUID]
    confirmed_by: Mapped[UUID | None]
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default='DRAFT')
    request_key: Mapped[str] = mapped_column(String(120))
    input_hash: Mapped[str] = mapped_column(String(64))
    period: Mapped[str] = mapped_column(String(7))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    earning_ids: Mapped[list] = mapped_column(JSONB)
    note: Mapped[str] = mapped_column(String(1000))
    confirmation_note: Mapped[str] = mapped_column(String(1000), default='')


class SettlementLine(Identity, Base):
    __tablename__ = 'settlement_lines'
    __table_args__ = (UniqueConstraint('settlement_id', 'earning_id'),
        ForeignKeyConstraint(['settlement_id', 'store_id'], ['app.settlements.id', 'app.settlements.store_id']),
        ForeignKeyConstraint(['earning_id', 'store_id'], ['app.earnings.id', 'app.earnings.store_id']))
    store_id: Mapped[UUID]
    settlement_id: Mapped[UUID]
    earning_id: Mapped[UUID]
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    snapshot: Mapped[dict] = mapped_column(JSONB)
