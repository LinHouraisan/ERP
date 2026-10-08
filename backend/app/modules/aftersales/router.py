from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import select
from app.core.db import get_db
from app.core.errors import DomainError
from app.core.security import current_user, owned, require_role
from app.modules.aftersales.models import AfterSale
from app.modules.aftersales.schemas import AfterSaleInput, Review, Receive, Note, FailedResolution
from app.modules.aftersales import service

router = APIRouter(prefix='/api/v1/aftersales', tags=['售后与模拟退款'])


@router.get('')
async def listing(user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'STAFF','WAREHOUSE','FINANCE','MANAGER','ADMIN')
    rows = (await db.scalars(select(AfterSale).where(AfterSale.store_id == user.store_id).order_by(AfterSale.created_at.desc()).limit(100))).all()
    return {'items': [await service.view(db, row) for row in rows]}


@router.get('/{aid}')
async def detail(aid: UUID, user=Depends(current_user), db=Depends(get_db)):
    return await service.view(db, await owned(db, AfterSale, aid, user))


@router.post('')
async def create(data: AfterSaleInput, user=Depends(current_user), db=Depends(get_db)):
    return await service.view(db, await service.create(db, user, data))


@router.post('/{aid}/review')
async def review(aid: UUID, data: Review, user=Depends(current_user), db=Depends(get_db)):
    return await service.view(db, await service.review(db, user, aid, data))


@router.post('/{aid}/receive')
async def receive(aid: UUID, data: Receive, user=Depends(current_user), db=Depends(get_db)):
    return await service.view(db, await service.receive(db, user, aid, data))


@router.post('/{aid}/refund')
async def refund(aid: UUID, user=Depends(current_user), db=Depends(get_db)):
    return await service.view(db, await service.submit(db, user, aid))


@router.post('/{aid}/reconcile')
async def reconcile(aid: UUID, user=Depends(current_user), db=Depends(get_db)):
    return await service.view(db, await service.submit(db, user, aid, lookup=True))


@router.post('/{aid}/service-resolution')
async def resolve_service(aid: UUID, data: Note, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'MANAGER','ADMIN')
    row = await owned(db, AfterSale, aid, user, lock=True)
    if row.status != 'APPROVED' or row.service_resolution: raise DomainError('IMMUTABLE', '仅已批准且尚未记录的申请可补充履约处理证据')
    row.service_resolution = data.note; service.event(db, user, row, 'SERVICE_RESOLUTION', {'note': data.note})
    await db.commit(); return await service.view(db, row)


@router.post('/{aid}/close')
async def close(aid: UUID, data: Note, user=Depends(current_user), db=Depends(get_db)):
    return await service.view(db, await service.close(db, user, aid, data))


@router.post('/{aid}/resolve-failure')
async def resolve_failure(aid: UUID, data: FailedResolution, user=Depends(current_user), db=Depends(get_db)):
    return await service.view(db, await service.resolve_failure(db, user, aid, data))
