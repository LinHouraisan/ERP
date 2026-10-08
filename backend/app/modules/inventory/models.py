from decimal import Decimal
from uuid import UUID
from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, Identity


class Supplier(Identity, Base):
    __tablename__ = 'suppliers'
    __table_args__ = (UniqueConstraint('id', 'store_id'),)
    store_id: Mapped[UUID] = mapped_column(ForeignKey('app.stores.id'))
    name: Mapped[str] = mapped_column(String(100))
    contact: Mapped[str] = mapped_column(String(200), default='')


class Purchase(Identity, Base):
    __tablename__ = 'purchases'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('store_id', 'request_key'),
        ForeignKeyConstraint(['supplier_id', 'store_id'], ['app.suppliers.id', 'app.suppliers.store_id']),
        ForeignKeyConstraint(['actor_id', 'store_id'], ['app.users.id', 'app.users.store_id']),
        ForeignKeyConstraint(['approved_by', 'store_id'], ['app.users.id', 'app.users.store_id']),
        CheckConstraint("status IN ('DRAFT','APPROVED','PARTIAL','RECEIVED')", name='ck_purchase_status'))
    store_id: Mapped[UUID]
    supplier_id: Mapped[UUID]
    actor_id: Mapped[UUID]
    approved_by: Mapped[UUID | None]
    status: Mapped[str] = mapped_column(String(16), default='DRAFT')
    request_key: Mapped[str] = mapped_column(String(120))
    input_hash: Mapped[str] = mapped_column(String(64))


class PurchaseLine(Identity, Base):
    __tablename__ = 'purchase_lines'
    __table_args__ = (UniqueConstraint('purchase_id', 'product_id'),
        ForeignKeyConstraint(['purchase_id', 'store_id'], ['app.purchases.id', 'app.purchases.store_id']),
        ForeignKeyConstraint(['product_id', 'store_id'], ['app.products.id', 'app.products.store_id']),
        CheckConstraint('quantity > 0 AND unit_cost >= 0 AND received_quantity BETWEEN 0 AND quantity', name='ck_purchase_line_values'))
    store_id: Mapped[UUID]
    purchase_id: Mapped[UUID]
    product_id: Mapped[UUID]
    quantity: Mapped[int]
    received_quantity: Mapped[int] = mapped_column(default=0)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class Receipt(Identity, Base):
    __tablename__ = 'stock_receipts'
    __table_args__ = (UniqueConstraint('id', 'store_id'), UniqueConstraint('store_id', 'request_key'),
        ForeignKeyConstraint(['purchase_id', 'store_id'], ['app.purchases.id', 'app.purchases.store_id']),
        ForeignKeyConstraint(['actor_id', 'store_id'], ['app.users.id', 'app.users.store_id']))
    store_id: Mapped[UUID]
    purchase_id: Mapped[UUID]
    actor_id: Mapped[UUID]
    request_key: Mapped[str] = mapped_column(String(120))
    input_hash: Mapped[str] = mapped_column(String(64))
    lines: Mapped[list] = mapped_column(JSONB)


class Stock(Identity, Base):
    __tablename__ = 'stock'
    __table_args__ = (UniqueConstraint('store_id', 'product_id'),
        ForeignKeyConstraint(['product_id', 'store_id'], ['app.products.id', 'app.products.store_id']),
        CheckConstraint('quantity >= 0 AND reserved BETWEEN 0 AND quantity', name='ck_stock_nonnegative'))
    store_id: Mapped[UUID]
    product_id: Mapped[UUID]
    quantity: Mapped[int] = mapped_column(default=0)
    reserved: Mapped[int] = mapped_column(default=0)


class StockSerial(Identity, Base):
    __tablename__ = 'stock_serials'
    __table_args__ = (UniqueConstraint('store_id', 'serial'),
        ForeignKeyConstraint(['product_id', 'store_id'], ['app.products.id', 'app.products.store_id']),
        ForeignKeyConstraint(['receipt_id', 'store_id'], ['app.stock_receipts.id', 'app.stock_receipts.store_id']),
        ForeignKeyConstraint(['order_id', 'store_id'], ['app.sales_orders.id', 'app.sales_orders.store_id']),
        ForeignKeyConstraint(['installation_id', 'store_id'], ['app.installations.id', 'app.installations.store_id']),
        ForeignKeyConstraint(['count_id', 'store_id'], ['app.stock_counts.id', 'app.stock_counts.store_id']),
        Index('uq_serial_current_custody', 'serial', unique=True, postgresql_where=text("status <> 'TRANSFERRED'")),
        CheckConstraint("status IN ('AVAILABLE','RESERVED','SHIPPED','IN_TRANSIT','TRANSFERRED','LOST')", name='ck_stock_serial_status'))
    store_id: Mapped[UUID]
    product_id: Mapped[UUID]
    receipt_id: Mapped[UUID | None]
    transfer_id: Mapped[UUID | None] = mapped_column(ForeignKey('app.transfers.id'))
    count_id: Mapped[UUID | None]
    order_id: Mapped[UUID | None]
    installation_id: Mapped[UUID | None]
    serial: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(16), default='AVAILABLE')


class StockMovement(Identity, Base):
    __tablename__ = 'stock_movements'
    __table_args__ = (
        ForeignKeyConstraint(['product_id', 'store_id'], ['app.products.id', 'app.products.store_id']),
        ForeignKeyConstraint(['receipt_id', 'store_id'], ['app.stock_receipts.id', 'app.stock_receipts.store_id']),
        ForeignKeyConstraint(['order_id', 'store_id'], ['app.sales_orders.id', 'app.sales_orders.store_id']),
        ForeignKeyConstraint(['installation_id', 'store_id'], ['app.installations.id', 'app.installations.store_id']),
        ForeignKeyConstraint(['actor_id', 'store_id'], ['app.users.id', 'app.users.store_id']),
        ForeignKeyConstraint(['after_sale_id', 'store_id'], ['app.after_sales.id', 'app.after_sales.store_id']),
        ForeignKeyConstraint(['installation_return_id', 'store_id'], ['app.installations.id', 'app.installations.store_id']),
        ForeignKeyConstraint(['transfer_event_id', 'store_id'], ['app.transfer_events.id', 'app.transfer_events.store_id']),
        ForeignKeyConstraint(['stock_count_id', 'store_id'], ['app.stock_counts.id', 'app.stock_counts.store_id']),
        UniqueConstraint('receipt_id', 'product_id'), UniqueConstraint('order_id', 'product_id'),
        UniqueConstraint('installation_id', 'product_id'),
        UniqueConstraint('after_sale_id', 'product_id'),
        UniqueConstraint('installation_return_id', 'product_id'),
        UniqueConstraint('transfer_event_id', 'product_id'), UniqueConstraint('stock_count_id', 'product_id'),
        CheckConstraint('num_nonnulls(receipt_id, order_id, installation_id, after_sale_id, installation_return_id, transfer_event_id, stock_count_id) = 1', name='ck_stock_source'),
        CheckConstraint('quantity <> 0', name='ck_stock_movement_quantity'))
    store_id: Mapped[UUID]
    product_id: Mapped[UUID]
    receipt_id: Mapped[UUID | None]
    order_id: Mapped[UUID | None]
    installation_id: Mapped[UUID | None]
    after_sale_id: Mapped[UUID | None]
    installation_return_id: Mapped[UUID | None]
    transfer_event_id: Mapped[UUID | None]
    stock_count_id: Mapped[UUID | None]
    actor_id: Mapped[UUID]
    quantity: Mapped[int]
    serials: Mapped[list] = mapped_column(JSONB, default=list)
