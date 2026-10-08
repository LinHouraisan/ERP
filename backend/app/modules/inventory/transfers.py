from uuid import UUID
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from app.core.db import get_db
from app.core.digests import content_hash
from app.core.errors import DomainError
from app.core.security import current_user, owned, require_role
from app.modules.auth.models import Store
from app.modules.catalog.models import Product
from app.modules.inventory.models import StockSerial, StockMovement
from app.modules.inventory.service import locked_stock
from app.modules.inventory.schemas import Quantity, RequestKey
from app.modules.inventory.transfers_models import Transfer, TransferEvent
from app.modules.aftersales.schemas import Review, Note

router = APIRouter(prefix='/api/v1/transfers', tags=['两店调拨'])


class Create(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_key: RequestKey
    destination_store_id: UUID
    product_id: UUID
    quantity: Quantity
    note: str = Field(min_length=1, max_length=1000)


class Receive(Note):
    request_key: RequestKey
    quantity: int = Field(ge=0, le=10000)
    serials: list[str] = Field(default_factory=list, max_length=10000)


class Resolve(Note):
    write_off_remaining: bool = Field(default=False, strict=True)


async def accessible(db,user,tid,*,side=None,lock=False):
    q=select(Transfer).where(Transfer.id==tid,or_(Transfer.source_store_id==user.store_id,Transfer.destination_store_id==user.store_id))
    row=await db.scalar(q.with_for_update().execution_options(populate_existing=True) if lock else q)
    if not row or side and getattr(row,side+'_store_id')!=user.store_id: raise DomainError('NOT_FOUND','调拨单不存在或当前门店无权执行此动作',404)
    source,dest=await db.get(Store,row.source_store_id),await db.get(Store,row.destination_store_id)
    if not source.organization_id or source.organization_id!=dest.organization_id: raise DomainError('ENTITY_MISMATCH','调拨只适用于同一经营主体下的门店')
    return row


async def event(db,user,row,action,detail,request_key=None,input_hash=None):
    entry=TransferEvent(store_id=user.store_id,transfer_id=row.id,actor_id=user.user_id,action=action,detail=detail,request_key=request_key,input_hash=input_hash)
    db.add(entry); await db.flush(); return entry


async def view(db,row):
    source,dest=await db.get(Store,row.source_store_id),await db.get(Store,row.destination_store_id)
    product=await db.get(Product,row.source_product_id)
    events=(await db.scalars(select(TransferEvent).where(TransferEvent.transfer_id==row.id).order_by(TransferEvent.created_at))).all()
    return {**{k:getattr(row,k) for k in ('id','source_store_id','destination_store_id','source_product_id','destination_product_id','actor_id','status',
        'quantity','received_quantity','lost_quantity','serials','received_serials','note','created_at')}, 'sku':product.sku,'product_name':product.name,'tracking':product.tracking,
        'source_store_name':source.name,'destination_store_name':dest.name,
        'in_transit':row.quantity-row.received_quantity-row.lost_quantity if row.status in ('IN_TRANSIT','DISCREPANCY') else 0,
        'events':[{'action':e.action,'store_id':e.store_id,'actor_id':e.actor_id,'at':e.created_at,'detail':e.detail} for e in events]}


@router.get('/options')
async def options(user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'STAFF','WAREHOUSE','MANAGER','ADMIN')
    home=await db.get(Store,user.store_id)
    stores=(await db.scalars(select(Store).where(Store.organization_id==home.organization_id,Store.id!=home.id))).all() if home.organization_id else []
    products=(await db.scalars(select(Product).where(Product.store_id==home.id,Product.kind=='GOODS',Product.sku.is_not(None)))).all()
    return {'stores':[{'id':s.id,'name':s.name} for s in stores],'products':[{'id':p.id,'name':p.name,'sku':p.sku,'tracking':p.tracking} for p in products]}


@router.get('')
async def listing(user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'STAFF','WAREHOUSE','MANAGER','ADMIN')
    rows=(await db.scalars(select(Transfer).where(or_(Transfer.source_store_id==user.store_id,Transfer.destination_store_id==user.store_id)).order_by(Transfer.created_at.desc()).limit(100))).all()
    return {'items':[await view(db,r) for r in rows]}


@router.get('/{tid}')
async def detail(tid: UUID,user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'STAFF','WAREHOUSE','MANAGER','ADMIN')
    return await view(db,await accessible(db,user,tid))


@router.post('')
async def create(data: Create,user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'STAFF','WAREHOUSE','MANAGER','ADMIN')
    product=await owned(db,Product,data.product_id,user,lock=True)
    source,dest=await db.get(Store,user.store_id),await db.get(Store,data.destination_store_id)
    if not dest or source.id==dest.id or not source.organization_id or source.organization_id!=dest.organization_id:
        raise DomainError('ENTITY_MISMATCH','请选择同一经营主体的另一门店')
    ih=content_hash(data.model_dump(mode='json'))
    old=await db.scalar(select(Transfer).where(Transfer.source_store_id==user.store_id,Transfer.request_key==data.request_key))
    if old:
        if old.input_hash!=ih: raise DomainError('KEY_CONFLICT','调拨请求号对应不同内容')
        return await view(db,old)
    mapped=await db.scalar(select(Product).where(Product.store_id==dest.id,Product.sku==product.sku)) if product.sku else None
    if not mapped or product.kind!='GOODS' or mapped.kind!='GOODS' or product.tracking!=mapped.tracking:
        raise DomainError('SKU_MAPPING_REQUIRED','两店须存在同一商品编码和库存管理方式；不能按名称猜测对应关系')
    row=Transfer(source_store_id=source.id,destination_store_id=dest.id,source_product_id=product.id,destination_product_id=mapped.id,
        actor_id=user.user_id,request_key=data.request_key,input_hash=ih,quantity=data.quantity,note=data.note)
    db.add(row); await db.flush(); await event(db,user,row,'REQUESTED',data.model_dump(mode='json'))
    await db.commit(); return await view(db,row)


@router.post('/{tid}/review')
async def review(tid: UUID,data: Review,user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'MANAGER','ADMIN')
    row=await accessible(db,user,tid,side='source',lock=True)
    target='APPROVED' if data.decision=='APPROVE' else 'REJECTED'
    if row.status==target: return await view(db,row)
    if row.status!='REQUESTED': raise DomainError('REVIEWED','调拨已审批，不能覆盖')
    row.status=target; await event(db,user,row,target,{'note':data.note}); await db.commit(); return await view(db,row)


@router.post('/{tid}/dispatch')
async def dispatch(tid: UUID,data: Note,user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'WAREHOUSE','MANAGER','ADMIN')
    row=await accessible(db,user,tid,side='source',lock=True)
    if row.status in ('IN_TRANSIT','DISCREPANCY','RECEIVED','CLOSED_LOSS'): return await view(db,row)
    if row.status!='APPROVED': raise DomainError('APPROVAL_REQUIRED','调拨须先由调出店负责人批准')
    stock=await locked_stock(db,user,row.source_product_id)
    if stock.quantity-stock.reserved<row.quantity: raise DomainError('NO_STOCK','可用库存不足，已预留给客户的商品不可调出')
    product=await db.get(Product,row.source_product_id)
    serials=[]
    if product.tracking=='SERIAL':
        devices=(await db.scalars(select(StockSerial).where(StockSerial.store_id==user.store_id,StockSerial.product_id==product.id,StockSerial.status=='AVAILABLE')
            .order_by(StockSerial.created_at,StockSerial.id).limit(row.quantity).with_for_update())).all()
        if len(devices)!=row.quantity: raise DomainError('NO_STOCK','可用设备序列号不足')
        for device in devices: device.status,device.transfer_id='IN_TRANSIT',row.id; serials.append(device.serial)
    row.serials,row.status=serials,'IN_TRANSIT'; stock.quantity-=row.quantity
    entry=await event(db,user,row,'DISPATCHED',{'note':data.note,'quantity':row.quantity,'serials':serials})
    db.add(StockMovement(store_id=user.store_id,product_id=product.id,transfer_event_id=entry.id,actor_id=user.user_id,quantity=-row.quantity,serials=serials))
    await db.commit(); return await view(db,row)


@router.post('/{tid}/receive')
async def receive(tid: UUID,data: Receive,user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'WAREHOUSE','MANAGER','ADMIN')
    row=await accessible(db,user,tid,side='destination',lock=True)
    ih=content_hash({'transfer_id':str(tid),**data.model_dump(mode='json')})
    old=await db.scalar(select(TransferEvent).where(TransferEvent.store_id==user.store_id,TransferEvent.request_key==data.request_key))
    if old:
        if old.input_hash!=ih: raise DomainError('KEY_CONFLICT','收货请求号对应不同内容')
        return await view(db,row)
    if row.status not in ('IN_TRANSIT','DISCREPANCY'): raise DomainError('NOT_IN_TRANSIT','调拨单尚未发货或已结案')
    remaining=row.quantity-row.received_quantity-row.lost_quantity
    product=await db.get(Product,row.destination_product_id)
    if len(set(data.serials))!=len(data.serials): raise DomainError('SERIAL_DUPLICATE','同一设备不能重复验收')
    if product.tracking=='SERIAL':
        if len(data.serials)!=data.quantity: raise DomainError('SERIAL_COUNT','实到数量必须与观察到的序列号数量相符')
        accepted=[s for s in data.serials if s in row.serials and s not in row.received_serials]
        quantity=len(accepted)
    else:
        if data.serials: raise DomainError('SERIAL_COUNT','数量商品不填写序列号')
        quantity,accepted=min(data.quantity,remaining),[]
    stock=await locked_stock(db,user,row.destination_product_id)
    for serial in accepted:
        original=await db.scalar(select(StockSerial).where(StockSerial.store_id==row.source_store_id,StockSerial.serial==serial).with_for_update())
        if original.status!='IN_TRANSIT' or original.transfer_id!=row.id: raise DomainError('SERIAL_STATE','原设备已不在本次调拨途中')
        original.status='TRANSFERRED'; await db.flush()
        device=await db.scalar(select(StockSerial).where(StockSerial.store_id==user.store_id,StockSerial.serial==serial).with_for_update())
        if device:
            if device.status!='TRANSFERRED' or device.product_id!=row.destination_product_id: raise DomainError('SERIAL_EXISTS','调入店已有此序列号，须核查')
            device.status,device.transfer_id,device.receipt_id,device.count_id='AVAILABLE',row.id,None,None
        else: db.add(StockSerial(store_id=user.store_id,product_id=row.destination_product_id,serial=serial,status='AVAILABLE',transfer_id=row.id))
    stock.quantity+=quantity; row.received_quantity+=quantity; row.received_serials=[*row.received_serials,*accepted]
    discrepancy=quantity!=data.quantity or row.received_quantity+row.lost_quantity!=row.quantity
    row.status='DISCREPANCY' if discrepancy else 'RECEIVED'
    entry=await event(db,user,row,'RECEIVED',{'observed':data.model_dump(mode='json'),'accepted_quantity':quantity,'accepted_serials':accepted,'discrepancy':discrepancy},data.request_key,ih)
    if quantity: db.add(StockMovement(store_id=user.store_id,product_id=row.destination_product_id,transfer_event_id=entry.id,actor_id=user.user_id,quantity=quantity,serials=accepted))
    await db.commit(); return await view(db,row)


@router.post('/{tid}/resolve')
async def resolve(tid: UUID,data: Resolve,user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'MANAGER','ADMIN')
    row=await accessible(db,user,tid,side='source',lock=True)
    if row.status!='DISCREPANCY': raise DomainError('NO_DISCREPANCY','仅待核查的收货差异可结案')
    remaining=row.quantity-row.received_quantity-row.lost_quantity
    if remaining and not data.write_off_remaining: raise DomainError('IN_TRANSIT_REMAINS','仍有在途商品，须继续收货或依据证据确认在途损失')
    if remaining:
        devices=(await db.scalars(select(StockSerial).where(StockSerial.store_id==user.store_id,StockSerial.transfer_id==row.id,StockSerial.status=='IN_TRANSIT').with_for_update())).all()
        for device in devices: device.status='LOST'
        row.lost_quantity+=remaining
    row.status='CLOSED_LOSS' if row.lost_quantity else 'RECEIVED'
    await event(db,user,row,'DISCREPANCY_RESOLVED',{'note':data.note,'lost_quantity':remaining})
    await db.commit(); return await view(db,row)
