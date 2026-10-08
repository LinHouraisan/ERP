from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.core.db import utcnow
from app.core.digests import content_hash
from app.core.errors import DomainError
from app.core.security import owned, require_role
from app.modules.auth.models import User
from app.modules.catalog.models import Product
from app.modules.sales.models import SalesOrder, Payment
from app.modules.acceptances.models import Acceptance
from app.modules.accounts.models import CustomerBusiness
from app.modules.inventory.models import StockSerial, StockMovement
from app.modules.inventory.service import locked_stock
from app.modules.installations.models import Installation, InstallationEvent


def event(db, user, row, action, detail):
    db.add(InstallationEvent(store_id=user.store_id, installation_id=row.id, actor_id=user.user_id, action=action, detail=detail))


async def accessible(db, user, wid, lock=False):
    row = await owned(db, Installation, wid, user)
    if user.role == 'INSTALLER' and row.installer_id != user.user_id: raise DomainError('NOT_FOUND', '工单不存在或未分配给当前人员', 404)
    if lock:
        if row.source_order_id: await owned(db, SalesOrder, row.source_order_id, user, lock=True)
        if row.source_acceptance_id: await owned(db, Acceptance, row.source_acceptance_id, user, lock=True)
        row = await owned(db, Installation, wid, user, lock=True)
        if user.role == 'INSTALLER' and row.installer_id != user.user_id: raise DomainError('NOT_FOUND', '工单已重新分配', 404)
    return row


async def create(db, user, data):
    require_role(user, 'STAFF', 'MANAGER', 'ADMIN')
    from app.modules.aftersales.models import AfterSale, Reversal
    if data.source_order_id:
        source = await owned(db, SalesOrder, data.source_order_id, user, lock=True)
        cases = (await db.scalars(select(AfterSale).where(AfterSale.order_id == source.id))).all()
        from decimal import Decimal
        if any(c.status in ('REQUESTED','APPROVED') for c in cases) or cases and sum((c.amount for c in cases if c.refund_status == 'SUCCESS'), Decimal('0.00')) >= source.total:
            raise DomainError('AFTERSALE_PENDING', '原订单正在售后或已全额退款，不能新建装维')
        payment = await db.scalar(select(Payment).where(Payment.order_id == source.id))
        if payment is None or payment.status != 'SUCCESS': raise DomainError('PAYMENT_REQUIRED', '安装须关联已成功收款的订单')
        customer_id = source.customer_id
        where = Installation.source_order_id == source.id
    else:
        source = await owned(db, Acceptance, data.source_acceptance_id, user, lock=True)
        if await db.scalar(select(Reversal.id).where(Reversal.acceptance_id == source.id, Reversal.status != 'REJECTED')):
            raise DomainError('REVERSAL_PENDING', '原受理已有冲正记录，不能新建装维')
        if source.status != 'SUCCESS': raise DomainError('ACCEPTANCE_REQUIRED', '安装须关联已成功办理的受理')
        business = await db.scalar(select(CustomerBusiness).where(CustomerBusiness.acceptance_id == source.id))
        if business is None: raise DomainError('BUSINESS_RECORD_REQUIRED', '受理成功台账尚未同步，请核查原受理记录')
        customer_id = business.customer_id
        where = Installation.source_acceptance_id == source.id
    ih = content_hash(data.model_dump(mode='json'))
    old = await db.scalar(select(Installation).where(where))
    if old:
        if old.input_hash != ih: raise DomainError('SOURCE_IN_USE', '来源已经有安装工单，请从原工单改约')
        return old
    row = Installation(store_id=user.store_id, customer_id=customer_id, input_hash=ih, **data.model_dump())
    db.add(row); await db.flush(); event(db, user, row, 'APPOINTED', data.model_dump(mode='json'))
    await db.commit(); return row


async def dispatch(db, user, wid, data):
    require_role(user, 'MANAGER', 'ADMIN')
    row = await accessible(db, user, wid, True)
    installer = await owned(db, User, data.installer_id, user)
    if installer.role != 'INSTALLER' or not installer.active: raise DomainError('INVALID_INSTALLER', '请选择本店有效装维人员')
    if row.status == 'DISPATCHED' and row.installer_id == installer.id: return row
    if row.status != 'APPOINTED': raise DomainError('INVALID_STATE', '领料前可先改约退回待派，再重新派工')
    if row.materials and not data.note.strip(): raise DomainError('HANDOVER_REQUIRED', '复访派工须记录原设备和耗材的保管交接')
    row.status, row.installer_id = 'DISPATCHED', installer.id
    event(db, user, row, 'DISPATCHED', {'installer_id': str(installer.id), 'note': data.note})
    await db.commit(); return row


async def reschedule(db, user, wid, data):
    require_role(user, 'STAFF', 'MANAGER', 'ADMIN', 'INSTALLER')
    row = await accessible(db, user, wid, True)
    if row.status not in ('APPOINTED','DISPATCHED','ACCEPTED','BLOCKED'): raise DomainError('INVALID_STATE', '现场受阻请先登记异常，再安排复访')
    event(db, user, row, 'RESCHEDULED', {'previous': row.appointment_at.isoformat(), 'previous_installer_id': str(row.installer_id) if row.installer_id else None, **data.model_dump(mode='json')})
    row.appointment_at, row.installer_id, row.status = data.appointment_at, None, 'APPOINTED'
    await db.commit(); return row


async def transition(db, user, wid, data):
    require_role(user, 'INSTALLER', 'MANAGER', 'ADMIN')
    row = await accessible(db, user, wid, True)
    ih = content_hash({'id': str(wid), **data.model_dump(mode='json')})
    existing = await db.scalar(select(InstallationEvent).where(InstallationEvent.store_id == user.store_id, InstallationEvent.request_key == data.request_key))
    if existing:
        if existing.input_hash != ih: raise DomainError('KEY_CONFLICT', '同一操作号对应不同工单内容')
        return row
    states = {'accept': ('DISPATCHED','ACCEPTED'), 'collect': ('ACCEPTED','MATERIALS_READY'), 'arrive': ('MATERIALS_READY','ON_SITE'), 'install': ('ON_SITE','INSTALLED'), 'complete': ('INSTALLED','COMPLETED')}
    before, after = states[data.action]
    if row.status != before: raise DomainError('INVALID_STATE', '请按接单、领料、到场、安装、客户验收的顺序执行')
    if data.action == 'complete' and not data.customer_accepted: raise DomainError('CUSTOMER_ACCEPTANCE_REQUIRED', '完成前须记录客户验收确认')
    if data.action == 'collect':
        prior = await db.scalar(select(InstallationEvent.id).where(InstallationEvent.installation_id == wid, InstallationEvent.action == 'MATERIALS_READY').limit(1))
        if prior and data.materials: raise DomainError('MATERIALS_ALREADY_ISSUED', '复访继续使用原领料，不得重复扣库存')
    else: prior = None
    if data.action == 'collect' and not prior:
        materials = []
        if row.source_order_id:
            order = await owned(db, SalesOrder, row.source_order_id, user, lock=True)
            pay = await db.scalar(select(Payment).where(Payment.order_id == order.id))
            from app.modules.aftersales.service import remaining_allocations
            allocations = await remaining_allocations(db, order, pay)
            if allocations and order.stock_status != 'SHIPPED': raise DomainError('DISPATCH_REQUIRED', '销售设备尚未出库，请仓库先确认出库')
            materials.extend({**a, 'source': 'SALE', 'order_id': str(order.id)} for a in allocations)
        for item in sorted(data.materials, key=lambda x: str(x.product_id)):
            product = await owned(db, Product, item.product_id, user)
            if product.kind != 'GOODS': raise DomainError('NOT_STOCK_ITEM', '耗材必须为实物商品')
            stock = await locked_stock(db, user, product.id)
            if stock.quantity-stock.reserved < item.quantity: raise DomainError('NO_STOCK', '耗材可用库存不足')
            serials = []
            if product.tracking == 'SERIAL':
                devices = (await db.scalars(select(StockSerial).where(StockSerial.store_id == user.store_id, StockSerial.product_id == product.id, StockSerial.status == 'AVAILABLE')
                    .order_by(StockSerial.created_at, StockSerial.id).limit(item.quantity).with_for_update())).all()
                if len(devices) != item.quantity: raise DomainError('NO_STOCK', '可用耗材设备不足')
                for device in devices: device.status, device.installation_id = 'SHIPPED', row.id; serials.append(device.serial)
            stock.quantity -= item.quantity
            db.add(StockMovement(store_id=user.store_id, product_id=product.id, installation_id=row.id, actor_id=user.user_id, quantity=-item.quantity, serials=serials))
            materials.append({'product_id': str(product.id), 'name': product.name, 'quantity': item.quantity, 'serials': serials, 'source': 'STOCK'})
        row.materials = materials
    row.status = after
    if after == 'COMPLETED': row.completed_at = utcnow()
    eid = await db.scalar(insert(InstallationEvent).values(store_id=user.store_id, installation_id=wid, actor_id=user.user_id,
        action=after, request_key=data.request_key, input_hash=ih, detail={'from': before, **data.model_dump(mode='json'), 'materials_record': row.materials if data.action == 'collect' else []})
        .on_conflict_do_nothing().returning(InstallationEvent.id))
    if eid is None: raise DomainError('KEY_CONFLICT', '操作号已被其他工单使用')
    await db.commit(); return row


async def issue(db, user, wid, data):
    require_role(user, 'INSTALLER','MANAGER','ADMIN')
    row = await accessible(db, user, wid, True)
    if row.status == 'BLOCKED': return row
    if row.status in ('COMPLETED','CANCELLED','APPOINTED'): raise DomainError('INVALID_STATE', '此工单当前不能登记施工异常')
    event(db, user, row, 'BLOCKED', {'from': row.status, 'note': data.note})
    row.status = 'BLOCKED'; await db.commit(); return row


async def cancel(db, user, wid, data):
    require_role(user, 'MANAGER','ADMIN')
    row = await accessible(db, user, wid, True)
    if row.status == 'CANCELLED': return row
    if row.status == 'COMPLETED': raise DomainError('SERVICE_PERFORMED', '已履约服务须保留完成事实，通过售后记录人工处理')
    issued = {x['product_id']: x for x in row.materials if x['source'] == 'STOCK'}
    if issued and not data.materials_confirmed: raise DomainError('MATERIALS_REQUIRED', '须确认全部领料的退回及已消耗数量，原因写入说明')
    for item in sorted(data.returned_materials, key=lambda x: str(x.product_id)):
        source = issued.get(str(item.product_id))
        if not source or item.quantity > source['quantity']: raise DomainError('RETURN_LIMIT', '退料数量超过原工单领用数量')
        product = await owned(db, Product, item.product_id, user)
        if product.tracking == 'SERIAL':
            if len(set(item.serials)) != item.quantity or not set(item.serials) <= set(source['serials']): raise DomainError('SERIAL_MISMATCH', '必须退回原工单设备')
        elif item.serials: raise DomainError('SERIAL_MISMATCH', '数量耗材不填写序列号')
        stock = await locked_stock(db, user, item.product_id)
        for serial in item.serials:
            device = await db.scalar(select(StockSerial).where(StockSerial.store_id == user.store_id, StockSerial.serial == serial).with_for_update())
            if device.status != 'SHIPPED' or device.installation_id != row.id: raise DomainError('SERIAL_STATE', '设备已被其他业务处理')
            device.status, device.installation_id = 'AVAILABLE', None
        stock.quantity += item.quantity
        db.add(StockMovement(store_id=user.store_id, product_id=item.product_id, installation_return_id=row.id,
            actor_id=user.user_id, quantity=item.quantity, serials=item.serials))
    event(db, user, row, 'CANCELLED', {'from': row.status, **data.model_dump(mode='json'), 'original_materials': row.materials})
    row.status = 'CANCELLED'; await db.commit(); return row
