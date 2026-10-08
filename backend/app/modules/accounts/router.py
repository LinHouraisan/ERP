from datetime import date, timedelta
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, or_
from sqlalchemy.dialects.postgresql import distinct_on
from app.core.config import business_date
from app.core.db import get_db
from app.core.errors import DomainError
from app.core.security import current_user, owned, require_role
from app.modules.accounts.models import Customer, BusinessAccount, AccountBinding, AccountSnapshot, CustomerBusiness
from app.modules.services.models import ServiceSession, ServiceTask
from app.modules.services.schemas import service_view, TaskCreate, TaskOut
from app.modules.services.service import create_task
from app.modules.acceptances.models import Acceptance
from app.modules.sales.models import SalesOrder
from app.modules.sales.service import order_view
from app.modules.installations.models import Installation
from app.modules.installations.schemas import view as installation_view

router = APIRouter(prefix='/api/v1/customers', tags=['客户全景'])


class CustomerInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    display_name: str = Field(min_length=1, max_length=100)
    contact: str = Field(default='', max_length=80)
    address: str = Field(default='', max_length=300)


def view(row):
    return {'id': row.id, 'display_name': row.display_name, 'contact': row.contact, 'address': row.address, 'simulated': True}


@router.get('')
async def listing(q: str = '', user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'STAFF', 'MANAGER', 'ADMIN')
    rows = (await db.scalars(select(Customer).where(Customer.store_id == user.store_id,
        or_(Customer.display_name.contains(q, autoescape=True), Customer.contact.contains(q, autoescape=True))).order_by(Customer.created_at.desc()).limit(100))).all()
    return {'items': [view(x) for x in rows]}


@router.post('')
async def create(data: CustomerInput, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'STAFF', 'MANAGER', 'ADMIN')
    row = Customer(store_id=user.store_id, external_id=uuid4(), **data.model_dump()); db.add(row); await db.commit()
    return view(row)


@router.post('/{cid}/edit')
async def edit(cid: UUID, data: CustomerInput, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'STAFF', 'MANAGER', 'ADMIN')
    row = await owned(db, Customer, cid, user, lock=True)
    for k, v in data.model_dump().items(): setattr(row, k, v)
    await db.commit(); return view(row)


@router.get('/expiring')
async def expiring(days: int = Query(30, ge=1, le=365), user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'STAFF', 'MANAGER', 'ADMIN')
    snapshots = (await db.scalars(select(AccountSnapshot).where(AccountSnapshot.store_id == user.store_id)
        .ext(distinct_on(AccountSnapshot.account_id)).order_by(AccountSnapshot.account_id, AccountSnapshot.source_time.desc(), AccountSnapshot.created_at.desc()))).all()
    items = []
    for s in snapshots:
        end = s.payload.get('contract_end')
        if end and business_date() <= date.fromisoformat(end) <= business_date()+timedelta(days=days):
            account = await db.get(BusinessAccount, s.account_id)
            items.append({'customer_id': account.customer_id, 'account_id': account.id, 'number': account.number, 'contract_end': end, 'snapshot_id': s.id, 'source': s.source, 'source_time': s.source_time})
    return {'items': items, 'definition': '最新查询快照中的合约到期日，含当天；办理前须重新查询'}


@router.post('/{cid}/follow-up/{snapshot_id}')
async def follow_up(cid: UUID, snapshot_id: UUID, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'STAFF', 'MANAGER', 'ADMIN')
    await owned(db, Customer, cid, user, lock=True)
    snapshot = await owned(db, AccountSnapshot, snapshot_id, user)
    account = await owned(db, BusinessAccount, snapshot.account_id, user)
    if account.customer_id != cid or not snapshot.payload.get('contract_end'):
        raise DomainError('FOLLOWUP_SOURCE', '客户与到期证据不匹配')
    title = f"到期跟进 {account.number} / {snapshot.payload['contract_end']}"
    existing = await db.scalar(select(ServiceTask).where(ServiceTask.store_id == user.store_id, ServiceTask.title == title))
    row = existing or await create_task(db, user, TaskCreate(service_id=snapshot.service_id, title=title, owner_role='STAFF'))
    return TaskOut.model_validate(row)


@router.get('/{cid}')
async def panorama(cid: UUID, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'STAFF', 'MANAGER', 'ADMIN')
    customer = await owned(db, Customer, cid, user)
    accounts = (await db.scalars(select(BusinessAccount).where(BusinessAccount.customer_id == cid, BusinessAccount.store_id == user.store_id))).all()
    bindings = (await db.scalars(select(AccountBinding).where(AccountBinding.customer_id == cid, AccountBinding.store_id == user.store_id).order_by(AccountBinding.created_at))).all()
    snapshots = (await db.scalars(select(AccountSnapshot).where(AccountSnapshot.account_id.in_([a.id for a in accounts]))
        .ext(distinct_on(AccountSnapshot.account_id)).order_by(AccountSnapshot.account_id, AccountSnapshot.source_time.desc(), AccountSnapshot.created_at.desc()))).all()
    services = (await db.scalars(select(ServiceSession).where(ServiceSession.customer_id == cid, ServiceSession.store_id == user.store_id).order_by(ServiceSession.created_at.desc()).limit(100))).all()
    acceptances = (await db.scalars(select(Acceptance).where(Acceptance.service_id.in_([s.id for s in services])))).all()
    tasks = (await db.scalars(select(ServiceTask).where(ServiceTask.service_id.in_([s.id for s in services])))).all()
    orders = (await db.scalars(select(SalesOrder).where(SalesOrder.customer_id == cid, SalesOrder.store_id == user.store_id).order_by(SalesOrder.created_at.desc()).limit(100))).all()
    business = (await db.scalars(select(CustomerBusiness).where(CustomerBusiness.customer_id == cid, CustomerBusiness.store_id == user.store_id).order_by(CustomerBusiness.observed_at.desc()))).all()
    installations = (await db.scalars(select(Installation).where(Installation.customer_id == cid, Installation.store_id == user.store_id).order_by(Installation.created_at.desc()))).all()
    return {**view(customer), 'accounts': [{'id': a.id, 'number': a.number, 'account_type': a.account_type} for a in accounts],
        'bindings': [{'account_id': b.account_id, 'source': b.source, 'source_time': b.source_time, 'recorded_at': b.created_at} for b in bindings],
        'facts': [{'account_id': s.account_id, 'snapshot_id': s.id, 'source': s.source, 'source_time': s.source_time, 'payload': s.payload} for s in snapshots],
        'services': [service_view(s) for s in services], 'follow_ups': [TaskOut.model_validate(t) for t in tasks], 'orders': [await order_view(db, o) for o in orders],
        'installations': [installation_view(w) for w in installations],
        'business': [{'id': b.id, 'account_id': b.account_id, 'acceptance_id': b.acceptance_id, 'external_order_id': b.external_order_id,
            'source': b.source, 'observed_at': b.observed_at, 'payload': b.payload} for b in business],
        'acceptances': [{'id': a.id, 'status': a.status, 'service_id': a.service_id, 'external_order_id': a.external_order_id} for a in acceptances]}
