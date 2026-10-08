from uuid import UUID
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, Identity


class QualityCheck(Identity, Base):
    __tablename__ = 'quality_checks'
    __table_args__ = (UniqueConstraint('id', 'store_id'),
        ForeignKeyConstraint(['target_id', 'store_id'], ['app.recommendations.id', 'app.recommendations.store_id']),
        ForeignKeyConstraint(['ai_run_id', 'store_id'], ['app.ai_runs.id', 'app.ai_runs.store_id']),
        CheckConstraint("status IN ('PASS','BLOCKED','NEEDS_REVIEW')", name='ck_quality_status'))
    store_id: Mapped[UUID]
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[UUID | None]
    candidate_id: Mapped[UUID | None]
    input_hash: Mapped[str] = mapped_column(String(64))
    rule_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(String(12000))
    policy_version_ids: Mapped[list] = mapped_column(JSONB)
    findings: Mapped[list] = mapped_column(JSONB)
    ai_run_id: Mapped[UUID]
    supersedes_id: Mapped[UUID | None]


class QualityReview(Identity, Base):
    __tablename__ = 'quality_reviews'
    __table_args__ = (ForeignKeyConstraint(['quality_check_id', 'store_id'], ['app.quality_checks.id', 'app.quality_checks.store_id']),
        ForeignKeyConstraint(['reviewer_id', 'store_id'], ['app.users.id', 'app.users.store_id']),
        CheckConstraint("decision IN ('CONFIRM','REJECT','REVISE')", name='ck_review_decision'))
    store_id: Mapped[UUID]
    quality_check_id: Mapped[UUID]
    reviewer_id: Mapped[UUID]
    decision: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(2000))
    revised_text: Mapped[str | None] = mapped_column(String(12000))
