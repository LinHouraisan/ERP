from uuid import UUID
from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, Identity


class Transfer(Identity, Base):
    __tablename__ = 'transfers'
    __table_args__ = (UniqueConstraint('source_store_id', 'request_key'),
        ForeignKeyConstraint(['source_product_id','source_store_id'], ['app.products.id','app.products.store_id']),
        ForeignKeyConstraint(['destination_product_id','destination_store_id'], ['app.products.id','app.products.store_id']),
        ForeignKeyConstraint(['actor_id','source_store_id'], ['app.users.id','app.users.store_id']),
        CheckConstraint('source_store_id <> destination_store_id AND quantity > 0 AND received_quantity >= 0 AND lost_quantity >= 0 AND received_quantity + lost_quantity <= quantity', name='ck_transfer_quantity'),
        CheckConstraint("status IN ('REQUESTED','APPROVED','REJECTED','IN_TRANSIT','DISCREPANCY','RECEIVED','CLOSED_LOSS')", name='ck_transfer_status'))
    source_store_id: Mapped[UUID]
    destination_store_id: Mapped[UUID]
    source_product_id: Mapped[UUID]
    destination_product_id: Mapped[UUID]
    actor_id: Mapped[UUID]
    request_key: Mapped[str] = mapped_column(String(120))
    input_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default='REQUESTED')
    quantity: Mapped[int]
    received_quantity: Mapped[int] = mapped_column(default=0)
    lost_quantity: Mapped[int] = mapped_column(default=0)
    serials: Mapped[list] = mapped_column(JSONB, default=list)
    received_serials: Mapped[list] = mapped_column(JSONB, default=list)
    note: Mapped[str] = mapped_column(String(1000))


class TransferEvent(Identity, Base):
    __tablename__ = 'transfer_events'
    __table_args__ = (UniqueConstraint('id','store_id'), UniqueConstraint('store_id','request_key'),
        ForeignKeyConstraint(['actor_id','store_id'], ['app.users.id','app.users.store_id']))
    transfer_id: Mapped[UUID] = mapped_column(ForeignKey('app.transfers.id'))
    store_id: Mapped[UUID]
    actor_id: Mapped[UUID]
    request_key: Mapped[str | None] = mapped_column(String(120))
    input_hash: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(32))
    detail: Mapped[dict] = mapped_column(JSONB)


class StockCount(Identity, Base):
    __tablename__ = 'stock_counts'
    __table_args__ = (UniqueConstraint('id','store_id'), UniqueConstraint('store_id','request_key'),
        ForeignKeyConstraint(['product_id','store_id'], ['app.products.id','app.products.store_id']),
        ForeignKeyConstraint(['actor_id','store_id'], ['app.users.id','app.users.store_id']),
        ForeignKeyConstraint(['approved_by','store_id'], ['app.users.id','app.users.store_id']),
        CheckConstraint('book_quantity >= 0 AND actual_quantity >= 0 AND reserved >= 0',name='ck_stock_count_quantity'),
        CheckConstraint("status IN ('REQUESTED','APPROVED','REJECTED')",name='ck_stock_count_status'))
    store_id: Mapped[UUID]
    product_id: Mapped[UUID]
    actor_id: Mapped[UUID]
    approved_by: Mapped[UUID | None]
    request_key: Mapped[str] = mapped_column(String(120))
    input_hash: Mapped[str] = mapped_column(String(64))
    book_quantity: Mapped[int]
    actual_quantity: Mapped[int]
    reserved: Mapped[int]
    book_serials: Mapped[list] = mapped_column(JSONB)
    actual_serials: Mapped[list] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default='REQUESTED')
    note: Mapped[str] = mapped_column(String(1000))
    review_note: Mapped[str] = mapped_column(String(1000), default='')
