from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, Identity


class Acceptance(Identity, Base):
    __tablename__ = 'acceptances'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('store_id', 'idempotency_key'),
        UniqueConstraint('recommendation_id', 'candidate_id'),
        ForeignKeyConstraint(['service_id', 'store_id'], ['app.service_sessions.id', 'app.service_sessions.store_id']),
        ForeignKeyConstraint(['recommendation_id', 'store_id'], ['app.recommendations.id', 'app.recommendations.store_id']),
        ForeignKeyConstraint(['quality_check_id', 'store_id'], ['app.quality_checks.id', 'app.quality_checks.store_id']),
        ForeignKeyConstraint(['confirmed_by', 'store_id'], ['app.users.id', 'app.users.store_id']),
        CheckConstraint("status IN ('DRAFT','READY','SUBMITTING','SUBMITTED','SUCCESS','FAILED','UNKNOWN','CANCELLED')", name='ck_acceptance_status'),
        CheckConstraint('expected_version > 0', name='ck_acceptance_version'))
    store_id: Mapped[UUID]
    service_id: Mapped[UUID]
    recommendation_id: Mapped[UUID]
    candidate_id: Mapped[UUID]
    idempotency_key: Mapped[str] = mapped_column(String(120))
    payload_hash: Mapped[str] = mapped_column(String(64))
    external_request_id: Mapped[UUID] = mapped_column(unique=True, default=uuid4)
    external_order_id: Mapped[UUID | None] = mapped_column(unique=True)
    external_payload: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default='DRAFT')
    expected_version: Mapped[int] = mapped_column(default=1)
    quality_check_id: Mapped[UUID | None]
    confirmed_by: Mapped[UUID | None]
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmation_hash: Mapped[str | None] = mapped_column(String(64))
    last_error: Mapped[str | None] = mapped_column(String(255))
