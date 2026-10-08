from datetime import datetime
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, Identity


class FeedbackToken(Identity, Base):
    __tablename__ = 'feedback_tokens'
    __table_args__ = (ForeignKeyConstraint(['service_id', 'store_id'], ['app.service_sessions.id', 'app.service_sessions.store_id']),)
    store_id: Mapped[UUID]
    service_id: Mapped[UUID]
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Feedback(Identity, Base):
    __tablename__ = 'feedback'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('service_id'),
        ForeignKeyConstraint(['service_id', 'store_id'], ['app.service_sessions.id', 'app.service_sessions.store_id']),
        CheckConstraint('score BETWEEN 1 AND 5', name='ck_feedback_score'))
    store_id: Mapped[UUID]
    service_id: Mapped[UUID]
    score: Mapped[int]
    tags: Mapped[list] = mapped_column(JSONB)
    comment: Mapped[str] = mapped_column(String(2000))
    content_hash: Mapped[str] = mapped_column(String(64))
