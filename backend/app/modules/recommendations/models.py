from uuid import UUID
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, Identity


class Recommendation(Identity, Base):
    __tablename__ = 'recommendations'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('service_id', 'revision'),
        ForeignKeyConstraint(['service_id', 'store_id'], ['app.service_sessions.id', 'app.service_sessions.store_id']),
        ForeignKeyConstraint(['snapshot_id', 'store_id'], ['app.account_snapshots.id', 'app.account_snapshots.store_id']),
        ForeignKeyConstraint(['prompt_version_id', 'store_id'], ['app.prompt_versions.id', 'app.prompt_versions.store_id']),
        CheckConstraint("outcome IN ('OPTIONS','KEEP_CURRENT','NO_MATCH','NEEDS_INFO','SERVICE_TASK')", name='ck_recommendation_outcome'))
    store_id: Mapped[UUID]
    service_id: Mapped[UUID]
    snapshot_id: Mapped[UUID]
    revision: Mapped[int]
    rule_version: Mapped[str] = mapped_column(String(32))
    demand: Mapped[dict] = mapped_column(JSONB)
    candidates: Mapped[list] = mapped_column(JSONB)
    outcome: Mapped[str] = mapped_column(String(32))
    missing_fields: Mapped[list] = mapped_column(JSONB)
    service_tasks: Mapped[list] = mapped_column(JSONB)
    input_hash: Mapped[str] = mapped_column(String(64))
    supersedes_id: Mapped[UUID | None]
    prompt_version_id: Mapped[UUID | None]


class PromptVersion(Identity, Base):
    __tablename__ = 'prompt_versions'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('store_id', 'scenario', 'version'),
        CheckConstraint("status IN ('DRAFT','PUBLISHED')", name='ck_prompt_status'))
    store_id: Mapped[UUID]
    scenario: Mapped[str] = mapped_column(String(32))
    version: Mapped[int]
    status: Mapped[str] = mapped_column(String(16), default='DRAFT')
    text: Mapped[str] = mapped_column(String(12000))


class AIRun(Identity, Base):
    __tablename__ = 'ai_runs'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('store_id', 'request_key'),
        ForeignKeyConstraint(['prompt_version_id', 'store_id'], ['app.prompt_versions.id', 'app.prompt_versions.store_id']),
        ForeignKeyConstraint(['service_id', 'store_id'], ['app.service_sessions.id', 'app.service_sessions.store_id']),
        CheckConstraint("status IN ('RUNNING','SUCCEEDED','FAILED','INTERRUPTED')", name='ck_ai_status'))
    store_id: Mapped[UUID]
    service_id: Mapped[UUID | None]
    prompt_version_id: Mapped[UUID]
    scenario: Mapped[str] = mapped_column(String(32))
    request_key: Mapped[str] = mapped_column(String(120))
    input_hash: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(16))
    model: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(16), default='RUNNING')
    input: Mapped[dict] = mapped_column(JSONB)
    output: Mapped[dict | None] = mapped_column(JSONB)
    usage: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(String(200))
    elapsed_ms: Mapped[int | None]
