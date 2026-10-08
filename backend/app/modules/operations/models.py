from datetime import datetime
from uuid import UUID
from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, Identity


class OperationsSnapshot(Identity, Base):
    __tablename__ = 'operations_snapshots'
    __table_args__ = (UniqueConstraint('id', 'store_id'),)
    store_id: Mapped[UUID] = mapped_column(ForeignKey('app.stores.id'))
    filters: Mapped[dict] = mapped_column(JSONB)
    metrics: Mapped[dict] = mapped_column(JSONB)


class GEOBatch(Identity, Base):
    __tablename__ = 'geo_batches'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('store_id', 'request_key'),
        ForeignKeyConstraint(['actor_id', 'store_id'], ['app.users.id', 'app.users.store_id']))
    store_id: Mapped[UUID]
    actor_id: Mapped[UUID]
    request_key: Mapped[str] = mapped_column(String(120))
    input_hash: Mapped[str] = mapped_column(String(64))


class GEOSample(Identity, Base):
    __tablename__ = 'geo_samples'
    __table_args__ = (ForeignKeyConstraint(['batch_id', 'store_id'], ['app.geo_batches.id', 'app.geo_batches.store_id']),)
    store_id: Mapped[UUID]
    batch_id: Mapped[UUID]
    platform: Mapped[str] = mapped_column(String(100))
    question: Mapped[str] = mapped_column(String(2000))
    answer: Mapped[str] = mapped_column(String(12000))
    brand: Mapped[str] = mapped_column(String(100))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    simulated: Mapped[bool]
    mentioned: Mapped[bool]
    citations: Mapped[list] = mapped_column(JSONB)
    factual_errors: Mapped[str] = mapped_column(String(3000))
