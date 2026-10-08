from uuid import UUID
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from app.core.db import get_db
from app.core.digests import content_hash
from app.core.errors import DomainError
from app.core.security import current_user, owned, require_role
from app.modules.catalog.models import Product
from app.modules.inventory.models import StockSerial, StockMovement
from app.modules.inventory.service import locked_stock
from app.modules.inventory.schemas import RequestKey
from app.modules.inventory.transfers_models import StockCount
from app.modules.aftersales.schemas import Review

router=APIRouter(prefix='/api/v1/inventory/counts',tags=['库存盘点'])


class Create(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_key: RequestKey
    product_id: UUID
    actual_quantity: int=Field(ge=0,le=1000000)
    actual_serials: list[str]=Field(default_factory=list,max_length=10000)
    note: str=Field(min_length=1,max_length=1000)


def view(row):
    return {**{k:getattr(row,k) for k in ('id','product_id','actor_id','approved_by','book_quantity','actual_quantity','reserved','book_serials','actual_serials','status','note','review_note','created_at')},
        'difference':row.actual_quantity-row.book_quantity}


async def serials(db,user,pid):
    return (await db.scalars(select(StockSerial).where(StockSerial.store_id==user.store_id,StockSerial.product_id==pid,StockSerial.status.in_(['AVAILABLE','RESERVED'])).order_by(StockSerial.serial).with_for_update())).all()


@router.get('')
async def listing(user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'WAREHOUSE','MANAGER','ADMIN')
    rows=(await db.scalars(select(StockCount).where(StockCount.store_id==user.store_id).order_by(StockCount.created_at.desc()).limit(100))).all()
    return {'items':[view(r) for r in rows]}


@router.post('')
async def create(data: Create,user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'WAREHOUSE','MANAGER','ADMIN')
    product=await owned(db,Product,data.product_id,user)
    stock=await locked_stock(db,user,product.id)
    ih=content_hash(data.model_dump(mode='json'))
    old=await db.scalar(select(StockCount).where(StockCount.store_id==user.store_id,StockCount.request_key==data.request_key))
    if old:
        if old.input_hash!=ih: raise DomainError('KEY_CONFLICT','盘点请求号对应不同内容')
        return view(old)
    if product.kind!='GOODS': raise DomainError('NOT_STOCK_ITEM','只对实物商品盘点')
    if product.tracking=='SERIAL':
        if len(set(data.actual_serials))!=data.actual_quantity or len(data.actual_serials)!=data.actual_quantity: raise DomainError('SERIAL_COUNT','实盘数量须与唯一设备序列号数量一致')
    elif data.actual_serials: raise DomainError('SERIAL_COUNT','数量商品不填写序列号')
    devices=await serials(db,user,product.id)
    if data.actual_quantity<stock.reserved or any(d.status=='RESERVED' and d.serial not in data.actual_serials for d in devices):
        raise DomainError('RESERVATION_PROTECTED','不可通过盘点抹除已预留给客户的商品；请先核实原订单')
    row=StockCount(store_id=user.store_id,actor_id=user.user_id,request_key=data.request_key,input_hash=ih,product_id=product.id,
        book_quantity=stock.quantity,reserved=stock.reserved,actual_quantity=data.actual_quantity,actual_serials=data.actual_serials,
        book_serials=[{'serial':d.serial,'status':d.status} for d in devices],note=data.note)
    db.add(row); await db.commit(); return view(row)


@router.post('/{cid}/review')
async def review(cid: UUID,data: Review,user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'MANAGER','ADMIN')
    row=await owned(db,StockCount,cid,user,lock=True)
    target='APPROVED' if data.decision=='APPROVE' else 'REJECTED'
    if row.status==target: return view(row)
    if row.status!='REQUESTED': raise DomainError('REVIEWED','盘点已审核')
    if target=='APPROVED':
        stock=await locked_stock(db,user,row.product_id)
        devices=await serials(db,user,row.product_id)
        if (stock.quantity,stock.reserved,[{'serial':d.serial,'status':d.status} for d in devices])!=(row.book_quantity,row.reserved,row.book_serials):
            raise DomainError('COUNT_STALE','盘点后库存或预留发生变化，请重新盘点；旧记录保留')
        observed=set(row.actual_serials)
        for device in devices:
            if device.serial not in observed: device.status='LOST'
        for serial in observed-{d.serial for d in devices}:
            existing=(await db.scalars(select(StockSerial).where(StockSerial.serial==serial).with_for_update())).all()
            local=next((s for s in existing if s.store_id==user.store_id),None)
            if any(s.status!='TRANSFERRED' and not(s==local and s.status=='LOST' and s.product_id==row.product_id) for s in existing):
                raise DomainError('SERIAL_CUSTODY','此序列号已有销售、装维或其他门店归属，须走原业务退货或调拨核查')
            if local:
                if local.product_id!=row.product_id or local.status!='LOST': raise DomainError('SERIAL_CUSTODY','原序列号不能通过盘点变更商品或绕过调拨')
                local.status,local.count_id='AVAILABLE',row.id
            else: db.add(StockSerial(store_id=user.store_id,product_id=row.product_id,serial=serial,status='AVAILABLE',count_id=row.id))
        delta=row.actual_quantity-row.book_quantity
        stock.quantity=row.actual_quantity
        if delta: db.add(StockMovement(store_id=user.store_id,product_id=row.product_id,stock_count_id=row.id,actor_id=user.user_id,
            quantity=delta,serials=sorted(set(row.actual_serials)^{d.serial for d in devices})))
    row.status,row.approved_by,row.review_note=target,user.user_id,data.note
    await db.commit(); return view(row)
