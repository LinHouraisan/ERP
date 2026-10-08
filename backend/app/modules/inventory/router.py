from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import select
from app.core.db import get_db
from app.core.security import current_user, owned, require_role
from app.modules.catalog.models import Product
from app.modules.inventory.models import Supplier, Purchase, Receipt, Stock, StockSerial, StockMovement
from app.modules.inventory.schemas import SupplierInput, PurchaseInput, ReceiptInput, supplier_view, receipt_view
from app.modules.inventory import service

router = APIRouter(prefix='/api/v1/inventory', tags=['采购库存'])


@router.get('/suppliers')
async def suppliers(user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'WAREHOUSE', 'MANAGER', 'ADMIN')
    return {'items': [supplier_view(x) for x in (await db.scalars(select(Supplier).where(Supplier.store_id == user.store_id).order_by(Supplier.created_at.desc()).limit(100))).all()]}


@router.post('/suppliers')
async def supplier(data: SupplierInput, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'WAREHOUSE', 'MANAGER', 'ADMIN')
    row = Supplier(store_id=user.store_id, **data.model_dump()); db.add(row); await db.commit()
    return supplier_view(row)


@router.get('/purchases')
async def purchases(user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'WAREHOUSE', 'MANAGER', 'ADMIN')
    rows = (await db.scalars(select(Purchase).where(Purchase.store_id == user.store_id).order_by(Purchase.created_at.desc()).limit(100))).all()
    return {'items': [await service.purchase_view(db, x) for x in rows]}


@router.get('/purchases/{pid}')
async def detail(pid: UUID, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'WAREHOUSE', 'MANAGER', 'ADMIN')
    row = await owned(db, Purchase, pid, user)
    receipts = (await db.scalars(select(Receipt).where(Receipt.purchase_id == pid).order_by(Receipt.created_at))).all()
    return {**await service.purchase_view(db, row), 'receipts': [receipt_view(x) for x in receipts]}


@router.post('/purchases')
async def create(data: PurchaseInput, user=Depends(current_user), db=Depends(get_db)):
    return await service.purchase_view(db, await service.create(db, user, data))


@router.post('/purchases/{pid}/approve')
async def approve(pid: UUID, user=Depends(current_user), db=Depends(get_db)):
    return await service.purchase_view(db, await service.approve(db, user, pid))


@router.post('/purchases/{pid}/receive')
async def receive(pid: UUID, data: ReceiptInput, user=Depends(current_user), db=Depends(get_db)):
    return receipt_view(await service.receive(db, user, pid, data))


@router.get('/stock')
async def stock(user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'STAFF', 'WAREHOUSE', 'MANAGER', 'ADMIN')
    rows = (await db.execute(select(Stock, Product).join(Product, Stock.product_id == Product.id).where(Stock.store_id == user.store_id).order_by(Product.name).limit(300))).all()
    return {'items': [{'product_id': p.id, 'name': p.name, 'sku':p.sku, 'tracking': p.tracking, 'quantity': s.quantity, 'reserved': s.reserved, 'available': s.quantity-s.reserved} for s, p in rows]}


@router.get('/serials')
async def serials(product_id: UUID, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'STAFF', 'WAREHOUSE', 'MANAGER', 'ADMIN')
    await owned(db, Product, product_id, user)
    rows = (await db.scalars(select(StockSerial).where(StockSerial.store_id == user.store_id, StockSerial.product_id == product_id).order_by(StockSerial.created_at).limit(1000))).all()
    return {'items': [{'id': x.id, 'serial': x.serial, 'status': x.status, 'receipt_id': x.receipt_id, 'order_id': x.order_id, 'installation_id': x.installation_id, 'transfer_id':x.transfer_id, 'count_id':x.count_id} for x in rows]}


@router.get('/movements')
async def movements(product_id: UUID | None = None, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'WAREHOUSE', 'MANAGER', 'ADMIN')
    q = select(StockMovement).where(StockMovement.store_id == user.store_id)
    if product_id: q = q.where(StockMovement.product_id == product_id)
    rows = (await db.scalars(q.order_by(StockMovement.created_at.desc()).limit(300))).all()
    return {'items': [{'id': x.id, 'product_id': x.product_id, 'receipt_id': x.receipt_id, 'order_id': x.order_id, 'installation_id': x.installation_id,
        'after_sale_id':x.after_sale_id,'installation_return_id':x.installation_return_id,'transfer_event_id':x.transfer_event_id,'stock_count_id':x.stock_count_id,
        'quantity': x.quantity, 'serials': x.serials, 'actor_id': x.actor_id, 'created_at': x.created_at} for x in rows]}
