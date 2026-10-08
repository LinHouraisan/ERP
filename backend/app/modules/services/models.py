from datetime import datetime
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, Identity


class ServiceSession(Identity, Base):
    __tablename__ = 'service_sessions'
    __table_args__ = (UniqueConstraint('id', 'store_id'),
        ForeignKeyConstraint(['staff_id', 'store_id'], ['app.users.id', 'app.users.store_id']),
        ForeignKeyConstraint(['account_id', 'store_id'], ['app.business_accounts.id', 'app.business_accounts.store_id']),
        ForeignKeyConstraint(['customer_id', 'store_id'], ['app.customers.id', 'app.customers.store_id']),
        CheckConstraint("status IN ('ACTIVE','ENDED')", name='ck_service_status'),
        CheckConstraint("category IN ('PLAN','FAULT','OTHER')", name='ck_service_category'))
    store_id: Mapped[UUID]
    staff_id: Mapped[UUID]
    account_id: Mapped[UUID | None]
    customer_id: Mapped[UUID | None]
    category: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default='ACTIVE')
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    preset: Mapped[bool] = mapped_column(default=False)


class ServiceEvent(Identity, Base):
    __tablename__ = 'service_events'
    __table_args__ = (ForeignKeyConstraint(['service_id', 'store_id'], ['app.service_sessions.id', 'app.service_sessions.store_id']),)
    store_id: Mapped[UUID]
    service_id: Mapped[UUID]
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey('app.users.id'))
    action: Mapped[str] = mapped_column(String(60))
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)


class ServiceTask(Identity, Base):
    __tablename__ = 'service_tasks'
    __table_args__ = (UniqueConstraint('id', 'store_id'),
        ForeignKeyConstraint(['service_id', 'store_id'], ['app.service_sessions.id', 'app.service_sessions.store_id']),
        CheckConstraint("status IN ('OPEN','IN_PROGRESS','CLOSED','CANCELLED')", name='ck_service_task_status'))
    store_id: Mapped[UUID]
    service_id: Mapped[UUID]
    title: Mapped[str] = mapped_column(String(200))
    owner_role: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default='OPEN')
    note: Mapped[str] = mapped_column(String(2000), default='')
