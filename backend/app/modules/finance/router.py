from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import select
from app.core.db import get_db
from app.core.security import current_user, owned, require_role
from app.core.errors import DomainError
from app.integrations import boss
from app.modules.finance.models import EarningRule, Earning, BillBatch
from app.modules.finance.schemas import RuleInput, AccrualInput, BillInput, MockBillInput, Period, rule_view
from app.modules.finance import service
from app.modules.sales.models import SalesOrder, Payment
from app.modules.acceptances.models import Acceptance
from app.modules.installations.models import Installation

router = APIRouter(prefix='/api/v1/finance', tags=['收益与账单'])


@router.get('/sources')
async def sources(user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'FINANCE', 'MANAGER', 'ADMIN')
    orders = (await db.scalars(select(SalesOrder).join(Payment, Payment.order_id == SalesOrder.id).where(SalesOrder.store_id == user.store_id,
        Payment.status == 'SUCCESS', SalesOrder.stock_status != 'RESERVED').order_by(SalesOrder.created_at.desc()).limit(100))).all()
    accepted = (await db.scalars(select(Acceptance).where(Acceptance.store_id == user.store_id, Acceptance.status == 'SUCCESS').order_by(Acceptance.created_at.desc()).limit(100))).all()
    work = (await db.scalars(select(Installation).where(Installation.store_id == user.store_id, Installation.status == 'COMPLETED').order_by(Installation.completed_at.desc()).limit(100))).all()
    return {'items': [{'source_type': kind, 'source_id': r.id, 'label': title+' '+str(r.id)[:8], 'service_id': r.service_id if kind == 'TELECOM' else None} for kind, title, rows in [('SALE','销售交付',orders),('TELECOM','成功受理',accepted),('INSTALLATION','安装验收',work)] for r in rows]}


@router.get('/rules')
async def rules(user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'FINANCE', 'MANAGER', 'ADMIN')
    return {'items': [rule_view(r) for r in (await db.scalars(select(EarningRule).where(EarningRule.store_id == user.store_id).order_by(EarningRule.created_at.desc()))).all()]}


@router.post('/rules')
async def new_rule(data: RuleInput, user=Depends(current_user), db=Depends(get_db)):
    return rule_view(await service.new_rule(db, user, data))


@router.post('/rules/{rid}/publish')
async def publish(rid: UUID, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'ADMIN')
    row = await owned(db, EarningRule, rid, user, lock=True)
    if row.status != 'PUBLISHED': row.status = 'PUBLISHED'; await db.commit()
    return rule_view(row)


@router.post('/accruals')
async def accrue(data: AccrualInput, user=Depends(current_user), db=Depends(get_db)):
    return await service.earning_view(db, await service.accrual(db, user, data))


@router.get('/earnings')
async def earnings(period: Period | None = None, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'FINANCE', 'MANAGER', 'ADMIN')
    q = select(Earning).where(Earning.store_id == user.store_id)
    if period: q = q.where(Earning.period == period)
    rows = (await db.scalars(q.order_by(Earning.created_at.desc()).limit(300))).all()
    return {'items': [await service.earning_view(db, r) for r in rows]}


@router.get('/earnings/{eid}')
async def earning_detail(eid: UUID, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'FINANCE', 'MANAGER', 'ADMIN')
    return await service.earning_view(db, await owned(db, Earning, eid, user))


@router.get('/bills')
async def bills(user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'FINANCE', 'MANAGER', 'ADMIN')
    rows = (await db.scalars(select(BillBatch).where(BillBatch.store_id == user.store_id).order_by(BillBatch.created_at.desc()).limit(100))).all()
    return {'items': [await service.bill_view(db, r) for r in rows]}


@router.post('/bills')
async def import_bill(data: BillInput, user=Depends(current_user), db=Depends(get_db)):
    return await service.bill_view(db, await service.import_bill(db, user, data))


@router.get('/mock-bill')
async def preview(period: Period, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'FINANCE', 'MANAGER', 'ADMIN')
    result = await boss.request('GET', f'/mock/v1/bills/{period}')
    if result.get('simulated') is not True or result.get('period') != period: raise DomainError('BILL_INVALID', '模拟账单来源或账期不匹配', 502)
    allowed = {str(x) for x in (await db.scalars(select(Payment.external_payment_id).where(Payment.store_id == user.store_id, Payment.external_payment_id.is_not(None)))).all()}
    allowed.update(str(x) for x in (await db.scalars(select(Acceptance.external_order_id).where(Acceptance.store_id == user.store_id, Acceptance.external_order_id.is_not(None)))).all())
    return {**result, 'rows': [r for r in result.get('rows', []) if r.get('business_no') in allowed]}


@router.post('/bills/from-mock')
async def from_mock(data: MockBillInput, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'FINANCE', 'MANAGER', 'ADMIN')
    # Fetch before any database lock; validate imported data at the same boundary as manual bills.
    result = await preview(data.period, user, db)
    if not result.get('simulated') or result.get('period') != data.period: raise DomainError('BILL_INVALID', '模拟账单来源或账期不匹配', 502)
    if not result.get('rows'): raise DomainError('BILL_EMPTY', '此账期模拟系统没有账单')
    try: parsed = BillInput(**data.model_dump(), source='BOSS_MOCK_BILL', rows=result['rows'])
    except ValueError: raise DomainError('BILL_INVALID', '模拟账单内容不完整', 502) from None
    return await service.bill_view(db, await service.import_bill(db, user, parsed))
