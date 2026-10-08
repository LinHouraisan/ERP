from uuid import UUID
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, Identity


class MetricsSnapshot(Identity, Base):
    __tablename__ = 'metrics_snapshots'
    __table_args__ = (UniqueConstraint('id', 'store_id'),)
    store_id: Mapped[UUID]
    filters: Mapped[dict] = mapped_column(JSONB)
    payload: Mapped[dict] = mapped_column(JSONB)
    evidence: Mapped[dict] = mapped_column(JSONB)


class ImprovementTask(Identity, Base):
    __tablename__ = 'improvement_tasks'
    __table_args__ = (UniqueConstraint('id', 'store_id'),
        ForeignKeyConstraint(['snapshot_id', 'store_id'], ['app.metrics_snapshots.id', 'app.metrics_snapshots.store_id']),
        ForeignKeyConstraint(['ai_run_id', 'store_id'], ['app.ai_runs.id', 'app.ai_runs.store_id']),
        ForeignKeyConstraint(['owner_id', 'store_id'], ['app.users.id', 'app.users.store_id']),
        CheckConstraint("status IN ('PROPOSED','APPROVED','IN_PROGRESS','VERIFIED','CLOSED','REJECTED')", name='ck_improvement_status'))
    store_id: Mapped[UUID]
    snapshot_id: Mapped[UUID]
    ai_run_id: Mapped[UUID | None] = mapped_column(unique=True)
    suggestion: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default='PROPOSED')
    owner_id: Mapped[UUID | None]
    plan: Mapped[str | None] = mapped_column(String(2000))
    target: Mapped[str | None] = mapped_column(String(2000))
    verification: Mapped[dict | None] = mapped_column(JSONB)


class ImprovementEvent(Identity, Base):
    __tablename__ = 'improvement_events'
    __table_args__ = (ForeignKeyConstraint(['task_id', 'store_id'], ['app.improvement_tasks.id', 'app.improvement_tasks.store_id']),)
    store_id: Mapped[UUID]
    task_id: Mapped[UUID]
    actor_id: Mapped[UUID]
    from_status: Mapped[str] = mapped_column(String(16))
    to_status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(2000))
