from datetime import datetime
from uuid import UUID
from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, Identity


class Customer(Identity, Base):
    __tablename__ = 'customers'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('store_id', 'external_id'))
    store_id: Mapped[UUID] = mapped_column(ForeignKey('app.stores.id'))
    external_id: Mapped[UUID]
    display_name: Mapped[str] = mapped_column(String(100), default='模拟客户', server_default='模拟客户')
    contact: Mapped[str] = mapped_column(String(80), default='', server_default='')
    address: Mapped[str] = mapped_column(String(300), default='', server_default='')


class AccountBinding(Identity, Base):
    __tablename__ = 'account_bindings'
    __table_args__ = (
        ForeignKeyConstraint(['account_id', 'store_id'], ['app.business_accounts.id', 'app.business_accounts.store_id']),
        ForeignKeyConstraint(['customer_id', 'store_id'], ['app.customers.id', 'app.customers.store_id']),
    )
    store_id: Mapped[UUID]
    account_id: Mapped[UUID]
    customer_id: Mapped[UUID]
    source: Mapped[str] = mapped_column(String(32))
    source_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BusinessAccount(Identity, Base):
    __tablename__ = 'business_accounts'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('store_id', 'source', 'account_type', 'number'),
        ForeignKeyConstraint(['customer_id', 'store_id'], ['app.customers.id', 'app.customers.store_id']))
    store_id: Mapped[UUID]
    customer_id: Mapped[UUID]
    external_id: Mapped[UUID]
    source: Mapped[str] = mapped_column(String(32))
    account_type: Mapped[str] = mapped_column(String(16))
    number: Mapped[str] = mapped_column(String(32))


class AccountSnapshot(Identity, Base):
    __tablename__ = 'account_snapshots'
    __table_args__ = (UniqueConstraint('id', 'store_id'),
        ForeignKeyConstraint(['account_id', 'store_id'], ['app.business_accounts.id', 'app.business_accounts.store_id']),
        ForeignKeyConstraint(['service_id', 'store_id'], ['app.service_sessions.id', 'app.service_sessions.store_id']))
    store_id: Mapped[UUID]
    account_id: Mapped[UUID]
    service_id: Mapped[UUID]
    source: Mapped[str] = mapped_column(String(32))
    source_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completeness: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict] = mapped_column(JSONB)


class CustomerBusiness(Identity, Base):
    __tablename__ = 'customer_business'
    __table_args__ = (UniqueConstraint('acceptance_id'),
        ForeignKeyConstraint(['customer_id', 'store_id'], ['app.customers.id', 'app.customers.store_id']),
        ForeignKeyConstraint(['account_id', 'store_id'], ['app.business_accounts.id', 'app.business_accounts.store_id']),
        ForeignKeyConstraint(['acceptance_id', 'store_id'], ['app.acceptances.id', 'app.acceptances.store_id']))
    store_id: Mapped[UUID]
    customer_id: Mapped[UUID]
    account_id: Mapped[UUID]
    acceptance_id: Mapped[UUID]
    external_order_id: Mapped[UUID]
    source: Mapped[str] = mapped_column(String(40))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSONB)
