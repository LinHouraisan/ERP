from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import select
from app.core.db import get_db
from app.core.security import current_user, require_role
from app.modules.auth.models import User
from app.modules.catalog.models import Product
from app.modules.inventory.models import Stock
from app.modules.installations.models import Installation, InstallationEvent
from app.modules.installations.schemas import InstallationInput, DispatchInput, AppointmentInput, TransitionInput, CancelInput, view
from app.modules.aftersales.schemas import Note
from app.modules.installations import service

router = APIRouter(prefix='/api/v1/installations', tags=['安装交付'])


@router.get('')
async def listing(user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'STAFF', 'MANAGER', 'ADMIN', 'INSTALLER', 'WAREHOUSE')
    q = select(Installation).where(Installation.store_id == user.store_id)
    if user.role == 'INSTALLER': q = q.where(Installation.installer_id == user.user_id)
    return {'items': [view(x) for x in (await db.scalars(q.order_by(Installation.created_at.desc()).limit(100))).all()]}


@router.get('/installers')
async def installers(user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'STAFF', 'MANAGER', 'ADMIN')
    rows = (await db.scalars(select(User).where(User.store_id == user.store_id, User.role == 'INSTALLER', User.active.is_(True)))).all()
    return {'items': [{'id': u.id, 'username': u.username} for u in rows]}


@router.get('/material-options')
async def material_options(user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'STAFF', 'MANAGER', 'ADMIN', 'INSTALLER', 'WAREHOUSE')
    rows = (await db.execute(select(Stock, Product).join(Product, Stock.product_id == Product.id).where(Stock.store_id == user.store_id).order_by(Product.name).limit(300))).all()
    return {'items': [{'product_id': p.id, 'name': p.name, 'available': s.quantity-s.reserved} for s,p in rows]}


@router.get('/{wid}')
async def detail(wid: UUID, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'STAFF', 'MANAGER', 'ADMIN', 'INSTALLER', 'WAREHOUSE')
    row = await service.accessible(db, user, wid)
    events = (await db.scalars(select(InstallationEvent).where(InstallationEvent.installation_id == wid).order_by(InstallationEvent.created_at))).all()
    return {**view(row), 'events': [{'action': e.action, 'detail': e.detail, 'actor_id': e.actor_id, 'at': e.created_at} for e in events]}


@router.post('')
async def create(data: InstallationInput, user=Depends(current_user), db=Depends(get_db)):
    return view(await service.create(db, user, data))


@router.post('/{wid}/dispatch')
async def dispatch(wid: UUID, data: DispatchInput, user=Depends(current_user), db=Depends(get_db)):
    return view(await service.dispatch(db, user, wid, data))


@router.post('/{wid}/reschedule')
async def reschedule(wid: UUID, data: AppointmentInput, user=Depends(current_user), db=Depends(get_db)):
    return view(await service.reschedule(db, user, wid, data))


@router.post('/{wid}/transition')
async def transition(wid: UUID, data: TransitionInput, user=Depends(current_user), db=Depends(get_db)):
    return view(await service.transition(db, user, wid, data))


@router.post('/{wid}/issue')
async def issue(wid: UUID, data: Note, user=Depends(current_user), db=Depends(get_db)):
    return view(await service.issue(db, user, wid, data))


@router.post('/{wid}/cancel')
async def cancel(wid: UUID, data: CancelInput, user=Depends(current_user), db=Depends(get_db)):
    return view(await service.cancel(db, user, wid, data))
