from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from app.core.config import business_date
from app.core.db import get_db, utcnow
from app.core.errors import DomainError
from app.core.security import current_user, owned, require_role
from app.modules.auth.models import User, Store
from app.modules.catalog.models import PolicyVersion, Product
from app.modules.sales.models import SalesOrder, SalesEvent, DayClose, Payment
from app.modules.sales.schemas import SalesInput, SalesAssistInput, PayInput, CloseInput, CloseReview, payment_view, close_view
from app.modules.accounts.models import Customer
from app.modules.services.models import ServiceSession
from app.modules.recommendations.models import Recommendation
from app.modules.recommendations.ai_service import execute, run_view
from app.modules.sales import service

router = APIRouter(prefix='/api/v1/sales', tags=['销售与模拟收款'])


@router.get('/offers')
async def offers(user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'STAFF', 'MANAGER', 'ADMIN')
    day = business_date()
    store = await db.get(Store, user.store_id)
    rows = (await db.execute(select(PolicyVersion, Product).join(Product, Product.id == PolicyVersion.product_id).where(
        PolicyVersion.store_id == user.store_id, PolicyVersion.status == 'PUBLISHED', PolicyVersion.valid_from <= day, PolicyVersion.valid_to >= day)
        .ext(distinct_on(PolicyVersion.product_id)).order_by(PolicyVersion.product_id, PolicyVersion.version.desc()))).all()
    return {'items': [{'id': p.id, 'product_id': item.id, 'name': item.name, 'kind': item.kind, 'tracking': item.tracking,
        'price': str(p.one_time_fee), 'discount': p.conditions.get('sale_discount', '0.00'), 'version': p.version,
        'conditions': p.conditions, 'monthly_fee': str(p.monthly_fee) if p.monthly_fee is not None else None} for p, item in rows
        if p.one_time_fee is not None and (not p.conditions.get('region') or p.conditions['region'] == store.region)]}


@router.get('/orders')
async def orders(customer_id: UUID | None = None, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'STAFF', 'WAREHOUSE', 'FINANCE', 'MANAGER', 'ADMIN')
    q = select(SalesOrder).where(SalesOrder.store_id == user.store_id)
    if customer_id: q = q.where(SalesOrder.customer_id == customer_id)
    rows = (await db.scalars(q.order_by(SalesOrder.created_at.desc()).limit(100))).all()
    return {'items': [await service.order_view(db, row) for row in rows]}


@router.post('/assist')
async def assist(data: SalesAssistInput, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'STAFF', 'MANAGER', 'ADMIN')
    customer = await owned(db, Customer, data.customer_id, user)
    demand = None
    if data.source_service_id:
        source = await owned(db, ServiceSession, data.source_service_id, user)
        if source.customer_id != customer.id: raise DomainError('CUSTOMER_MISMATCH', '客户与来源接待不一致')
        rec = await db.scalar(select(Recommendation).where(Recommendation.service_id == source.id).order_by(Recommendation.revision.desc()).limit(1))
        demand = rec.demand if rec else None
    available = []
    for offer in (await offers(user=user, db=db))['items']:
        if offer['kind'] == 'PACKAGE': continue
        try: await service.check_policy(db, user, await owned(db, PolicyVersion, offer['id'], user), customer.id, None)
        except DomainError: continue
        available.append({**offer, 'id': str(offer['id']), 'product_id': str(offer['product_id'])})
    import re
    text = data.text
    for private in (customer.display_name, customer.contact, customer.address):
        if private: text = text.replace(private, '[客户信息]')
    payload = {'demand': re.sub(r'\d{7,}', '[号码已脱敏]', text), 'prior_demand': demand, 'offers': available,
        'boundary': '仅生成可供人工选择的商品/服务草稿；不写订单，不编造价格，提交后重新核算。'}
    return run_view(await execute(db, user, 'sales', payload, data.request_key, service_id=data.source_service_id))


@router.get('/orders/{oid}')
async def detail(oid: UUID, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'STAFF', 'WAREHOUSE', 'FINANCE', 'MANAGER', 'ADMIN')
    row = await owned(db, SalesOrder, oid, user)
    events = (await db.scalars(select(SalesEvent).where(SalesEvent.order_id == oid).order_by(SalesEvent.created_at))).all()
    return {**await service.order_view(db, row), 'events': [{'action': e.action, 'detail': e.detail, 'actor_id': e.actor_id, 'at': e.created_at} for e in events]}


@router.post('/orders')
async def create(data: SalesInput, user=Depends(current_user), db=Depends(get_db)):
    return await service.order_view(db, await service.create(db, user, data))


@router.post('/orders/{oid}/confirm')
async def confirm(oid: UUID, user=Depends(current_user), db=Depends(get_db)):
    return await service.order_view(db, await service.confirm(db, user, oid))


@router.post('/orders/{oid}/cancel')
async def cancel(oid: UUID, user=Depends(current_user), db=Depends(get_db)):
    return await service.order_view(db, await service.cancel(db, user, oid))


@router.post('/orders/{oid}/pay')
async def pay(oid: UUID, data: PayInput, user=Depends(current_user), db=Depends(get_db)):
    return payment_view(await service.pay(db, user, oid, data))


@router.post('/orders/{oid}/reconcile')
async def reconcile(oid: UUID, user=Depends(current_user), db=Depends(get_db)):
    return payment_view(await service.reconcile(db, user, oid))


@router.post('/orders/{oid}/dispatch')
async def dispatch(oid: UUID, user=Depends(current_user), db=Depends(get_db)):
    return await service.order_view(db, await service.dispatch(db, user, oid))


@router.get('/cashiers')
async def cashiers(user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'STAFF', 'FINANCE', 'MANAGER', 'ADMIN')
    q = select(User).where(User.store_id == user.store_id, User.active.is_(True), User.role.in_(['STAFF','MANAGER','ADMIN']))
    if user.role == 'STAFF': q = q.where(User.id == user.user_id)
    return {'items': [{'id': u.id, 'username': u.username} for u in (await db.scalars(q)).all()]}


@router.get('/day-closes')
async def closes(user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'STAFF', 'FINANCE', 'MANAGER', 'ADMIN')
    q = select(DayClose).where(DayClose.store_id == user.store_id)
    if user.role == 'STAFF': q = q.where(DayClose.cashier_id == user.user_id)
    rows = (await db.scalars(q.order_by(DayClose.created_at.desc()).limit(100))).all()
    payments = (await db.scalars(select(Payment).where(Payment.store_id == user.store_id, Payment.day_close_id.in_([r.id for r in rows])))).all()
    details = {}
    for p in payments:
        details.setdefault(p.day_close_id, []).append({'id': p.id, 'order_id': p.order_id, 'amount': str(p.amount), 'method': p.method})
    from app.modules.aftersales.models import AfterSale
    refunds = (await db.scalars(select(AfterSale).where(AfterSale.store_id == user.store_id, AfterSale.day_close_id.in_([r.id for r in rows])))).all()
    return {'items': [close_view(r) | {'payments': details.get(r.id, []),
        'refund_records':[{'id':a.id,'order_id':a.order_id,'amount':str(a.amount)} for a in refunds if a.day_close_id == r.id]} for r in rows]}


@router.post('/day-closes')
async def close(data: CloseInput, user=Depends(current_user), db=Depends(get_db)):
    return close_view(await service.day_close(db, user, data))


@router.post('/day-closes/{cid}/confirm')
async def review(cid: UUID, data: CloseReview, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'FINANCE', 'MANAGER', 'ADMIN')
    row = await owned(db, DayClose, cid, user, lock=True)
    if row.confirmed_by:
        if row.note != data.note: raise DomainError('CLOSE_IMMUTABLE', '已确认交接记录不可覆盖')
        return close_view(row)
    row.confirmed_by, row.confirmed_at, row.note = user.user_id, utcnow(), data.note
    await db.commit(); return close_view(row)
