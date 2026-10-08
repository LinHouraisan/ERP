from datetime import date, datetime
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, Identity, utcnow


class Window(Identity, Base):
    __tablename__ = 'windows'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('store_id', 'name'))
    store_id: Mapped[UUID] = mapped_column(ForeignKey('app.stores.id'))
    name: Mapped[str] = mapped_column(String(50))
    categories: Mapped[list] = mapped_column(JSONB)


class QueueTicket(Identity, Base):
    __tablename__ = 'queue_tickets'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('store_id', 'business_day', 'sequence'),
        UniqueConstraint('service_id'), ForeignKeyConstraint(['window_id', 'store_id'], ['app.windows.id', 'app.windows.store_id']),
        ForeignKeyConstraint(['service_id', 'store_id'], ['app.service_sessions.id', 'app.service_sessions.store_id']),
        CheckConstraint("status IN ('WAITING','CALLED','SERVING','DONE','MISSED','CANCELLED')", name='ck_ticket_status'),
        CheckConstraint("category IN ('PLAN','FAULT','OTHER')", name='ck_ticket_category'),
        Index('uq_active_ticket_per_window', 'window_id', unique=True, postgresql_where=text("status IN ('CALLED','SERVING')")))
    store_id: Mapped[UUID] = mapped_column(ForeignKey('app.stores.id'))
    business_day: Mapped[date]
    sequence: Mapped[int]
    ticket_number: Mapped[str] = mapped_column(String(24))
    category: Mapped[str] = mapped_column(String(16))
    window_id: Mapped[UUID | None]
    service_id: Mapped[UUID | None]
    status: Mapped[str] = mapped_column(String(16), default='WAITING')
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    called_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cumulative_wait_seconds: Mapped[int] = mapped_column(default=0)
    round_wait_seconds: Mapped[int | None]


class QueueEvent(Identity, Base):
    __tablename__ = 'queue_events'
    __table_args__ = (ForeignKeyConstraint(['ticket_id', 'store_id'], ['app.queue_tickets.id', 'app.queue_tickets.store_id']),)
    store_id: Mapped[UUID]
    ticket_id: Mapped[UUID]
    actor_id: Mapped[UUID | None]
    action: Mapped[str] = mapped_column(String(32))
    from_status: Mapped[str | None] = mapped_column(String(16))
    to_status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(2000), default='')
