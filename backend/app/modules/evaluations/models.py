from uuid import UUID
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, Identity


class EvaluationRun(Identity, Base):
    __tablename__ = 'evaluation_runs'
    __table_args__ = (UniqueConstraint('id','store_id'),
        ForeignKeyConstraint(['prompt_version_id','store_id'],['app.prompt_versions.id','app.prompt_versions.store_id']),
        CheckConstraint("status IN ('RUNNING','COMPLETED','INTERRUPTED')",name='ck_evaluation_status'))
    store_id: Mapped[UUID]
    prompt_version_id: Mapped[UUID]
    status: Mapped[str] = mapped_column(String(16),default='RUNNING')
    settings: Mapped[dict] = mapped_column(JSONB)
    metrics: Mapped[dict | None] = mapped_column(JSONB)


class EvaluationResult(Identity, Base):
    __tablename__ = 'evaluation_results'
    __table_args__ = (UniqueConstraint('run_id','case_id'),
        ForeignKeyConstraint(['run_id','store_id'],['app.evaluation_runs.id','app.evaluation_runs.store_id']),
        ForeignKeyConstraint(['ai_run_id','store_id'],['app.ai_runs.id','app.ai_runs.store_id']))
    store_id: Mapped[UUID]
    run_id: Mapped[UUID]
    case_id: Mapped[str] = mapped_column(String(80))
    input: Mapped[dict] = mapped_column(JSONB)
    ai_run_id: Mapped[UUID | None]
    status: Mapped[str] = mapped_column(String(16),default='PENDING')
    actual_issue_ids: Mapped[list | None] = mapped_column(JSONB)
    deterministic_findings: Mapped[list | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(String(200))
