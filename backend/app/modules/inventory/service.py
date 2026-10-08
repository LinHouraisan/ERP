from sqlalchemy import select
from decimal import Decimal
from sqlalchemy.dialects.postgresql import insert
from app.core.digests import content_hash
from app.core.errors import DomainError
from app.core.security import owned, require_role
from app.modules.catalog.models import Product
from app.modules.inventory.models import Supplier, Purchase, PurchaseLine, Receipt, Stock, StockSerial, StockMovement


async def purchase_view(db, row):
    lines = (await db.scalars(select(PurchaseLine).where(PurchaseLine.purchase_id == row.id).order_by(PurchaseLine.id))).all()
    supplier = await db.get(Supplier, row.supplier_id)
    return {'id': row.id, 'supplier_id': row.supplier_id, 'supplier_name': supplier.name, 'status': row.status,
        'total': str(sum((x.unit_cost*x.quantity for x in lines), Decimal('0.00'))),
        'actor_id': row.actor_id, 'approved_by': row.approved_by, 'created_at': row.created_at,
        'lines': [{'id': x.id, 'product_id': x.product_id, 'quantity': x.quantity, 'received_quantity': x.received_quantity, 'unit_cost': str(x.unit_cost)} for x in lines]}


async def create(db, user, data):
    require_role(user, 'WAREHOUSE', 'MANAGER', 'ADMIN')
    await owned(db, Supplier, data.supplier_id, user)
    ih = content_hash(data.model_dump(mode='json'))
    rid = await db.scalar(insert(Purchase).values(store_id=user.store_id, supplier_id=data.supplier_id,
        actor_id=user.user_id, request_key=data.request_key, input_hash=ih).on_conflict_do_nothing().returning(Purchase.id))
    row = await db.scalar(select(Purchase).where(Purchase.store_id == user.store_id, Purchase.request_key == data.request_key))
    if row.input_hash != ih: raise DomainError('KEY_CONFLICT', '同一请求号对应不同采购内容')
    if rid:
        for line in data.lines:
            product = await owned(db, Product, line.product_id, user)
            if product.kind != 'GOODS': raise DomainError('NOT_STOCK_ITEM', '仅实物商品可采购入库')
            db.add(PurchaseLine(store_id=user.store_id, purchase_id=row.id, **line.model_dump()))
    await db.commit()
    return row


async def approve(db, user, pid):
    require_role(user, 'MANAGER', 'ADMIN')
    row = await owned(db, Purchase, pid, user, lock=True)
    if row.status == 'DRAFT': row.status, row.approved_by = 'APPROVED', user.user_id
    await db.commit()
    return row


async def locked_stock(db, user, product_id):
    await db.execute(insert(Stock).values(store_id=user.store_id, product_id=product_id).on_conflict_do_nothing())
    return await db.scalar(select(Stock).where(Stock.store_id == user.store_id, Stock.product_id == product_id).with_for_update().execution_options(populate_existing=True))


async def receive(db, user, pid, data):
    require_role(user, 'WAREHOUSE', 'MANAGER', 'ADMIN')
    order = await owned(db, Purchase, pid, user, lock=True)
    ih = content_hash({'purchase_id': str(pid), **data.model_dump(mode='json')})
    existing = await db.scalar(select(Receipt).where(Receipt.store_id == user.store_id, Receipt.request_key == data.request_key))
    if existing:
        if existing.input_hash != ih: raise DomainError('KEY_CONFLICT', '同一请求号对应不同收货内容')
        return existing
    if order.status not in ('APPROVED', 'PARTIAL'): raise DomainError('APPROVAL_REQUIRED', '采购单须先审批且仍有待收数量')
    lines = (await db.scalars(select(PurchaseLine).where(PurchaseLine.purchase_id == pid))).all()
    by_id = {x.id: x for x in lines}
    if any(x.line_id not in by_id for x in data.lines): raise DomainError('LINE_MISMATCH', '收货行不属于此采购单')
    rid = await db.scalar(insert(Receipt).values(store_id=user.store_id, purchase_id=pid, actor_id=user.user_id,
        request_key=data.request_key, input_hash=ih, lines=[x.model_dump(mode='json') for x in data.lines]).on_conflict_do_nothing().returning(Receipt.id))
    if not rid: raise DomainError('KEY_CONFLICT', '此收货请求号已被另一张采购单使用')
    for item in sorted(data.lines, key=lambda x: str(by_id[x.line_id].product_id)):
        line = by_id[item.line_id]
        product = await owned(db, Product, line.product_id, user)
        if line.received_quantity + item.quantity > line.quantity: raise DomainError('OVER_RECEIPT', '收货量超过采购单剩余数量')
        if (product.tracking == 'SERIAL' and len(item.serials) != item.quantity) or (product.tracking != 'SERIAL' and item.serials):
            raise DomainError('SERIAL_COUNT', '序列号数量须与实际收货量一致，数量商品不填写序列号')
        stock = await locked_stock(db, user, product.id)
        for serial in item.serials:
            added = await db.scalar(insert(StockSerial).values(store_id=user.store_id, product_id=product.id, receipt_id=rid, serial=serial).on_conflict_do_nothing().returning(StockSerial.id))
            if added is None: raise DomainError('SERIAL_EXISTS', '此设备序列号已经入库')
        stock.quantity += item.quantity
        line.received_quantity += item.quantity
        db.add(StockMovement(store_id=user.store_id, product_id=product.id, receipt_id=rid, actor_id=user.user_id, quantity=item.quantity, serials=item.serials))
    order.status = 'RECEIVED' if all(x.quantity == x.received_quantity for x in lines) else 'PARTIAL'
    await db.commit()
    return await db.get(Receipt, rid)
