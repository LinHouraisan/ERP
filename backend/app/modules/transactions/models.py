from uuid import UUID
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, Identity


class Transaction(Identity, Base):
    __tablename__ = 'transactions'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('store_id', 'request_key'),
        ForeignKeyConstraint(['customer_id', 'store_id'], ['app.customers.id', 'app.customers.store_id']),
        ForeignKeyConstraint(['actor_id', 'store_id'], ['app.users.id', 'app.users.store_id']))
    store_id: Mapped[UUID]
    customer_id: Mapped[UUID]
    actor_id: Mapped[UUID]
    title: Mapped[str] = mapped_column(String(120))
    required: Mapped[list] = mapped_column(JSONB)
    request_key: Mapped[str] = mapped_column(String(120))
    input_hash: Mapped[str] = mapped_column(String(64))


class TransactionLink(Identity, Base):
    __tablename__ = 'transaction_links'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('order_id'), UniqueConstraint('acceptance_id'), UniqueConstraint('installation_id'),
        ForeignKeyConstraint(['transaction_id', 'store_id'], ['app.transactions.id', 'app.transactions.store_id']),
        ForeignKeyConstraint(['order_id', 'store_id'], ['app.sales_orders.id', 'app.sales_orders.store_id']),
        ForeignKeyConstraint(['acceptance_id', 'store_id'], ['app.acceptances.id', 'app.acceptances.store_id']),
        ForeignKeyConstraint(['installation_id', 'store_id'], ['app.installations.id', 'app.installations.store_id']),
        ForeignKeyConstraint(['resolved_by', 'store_id'], ['app.users.id', 'app.users.store_id']),
        ForeignKeyConstraint(['replacement_link_id', 'store_id'], ['app.transaction_links.id', 'app.transaction_links.store_id']),
        CheckConstraint('num_nonnulls(order_id, acceptance_id, installation_id) = 1', name='ck_transaction_link_source'))
    store_id: Mapped[UUID]
    transaction_id: Mapped[UUID]
    order_id: Mapped[UUID | None]
    acceptance_id: Mapped[UUID | None]
    installation_id: Mapped[UUID | None]
    resolved_by: Mapped[UUID | None]
    replacement_link_id: Mapped[UUID | None]
    resolution_note: Mapped[str] = mapped_column(String(1000), default='')
