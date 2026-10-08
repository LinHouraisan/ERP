from datetime import datetime
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, Identity


class Installation(Identity, Base):
    __tablename__ = 'installations'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('source_order_id'), UniqueConstraint('source_acceptance_id'),
        ForeignKeyConstraint(['source_order_id', 'store_id'], ['app.sales_orders.id', 'app.sales_orders.store_id']),
        ForeignKeyConstraint(['source_acceptance_id', 'store_id'], ['app.acceptances.id', 'app.acceptances.store_id']),
        ForeignKeyConstraint(['customer_id', 'store_id'], ['app.customers.id', 'app.customers.store_id']),
        ForeignKeyConstraint(['installer_id', 'store_id'], ['app.users.id', 'app.users.store_id']),
        CheckConstraint('num_nonnulls(source_order_id, source_acceptance_id) = 1', name='ck_installation_source'),
        CheckConstraint("status IN ('APPOINTED','DISPATCHED','ACCEPTED','MATERIALS_READY','ON_SITE','INSTALLED','COMPLETED','BLOCKED','CANCELLED')", name='ck_installation_status'))
    store_id: Mapped[UUID]
    source_order_id: Mapped[UUID | None]
    source_acceptance_id: Mapped[UUID | None]
    customer_id: Mapped[UUID]
    installer_id: Mapped[UUID | None]
    input_hash: Mapped[str] = mapped_column(String(64))
    address: Mapped[str] = mapped_column(String(300))
    appointment_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default='APPOINTED')
    materials: Mapped[list] = mapped_column(JSONB, default=list)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InstallationEvent(Identity, Base):
    __tablename__ = 'installation_events'
    __table_args__ = (UniqueConstraint('store_id', 'request_key'),
        ForeignKeyConstraint(['installation_id', 'store_id'], ['app.installations.id', 'app.installations.store_id']),
        ForeignKeyConstraint(['actor_id', 'store_id'], ['app.users.id', 'app.users.store_id']))
    store_id: Mapped[UUID]
    installation_id: Mapped[UUID]
    actor_id: Mapped[UUID]
    action: Mapped[str] = mapped_column(String(40))
    request_key: Mapped[str | None] = mapped_column(String(120))
    input_hash: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict] = mapped_column(JSONB)
