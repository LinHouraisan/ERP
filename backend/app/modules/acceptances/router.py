from uuid import UUID
from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy import select
from app.core.db import get_db
from app.core.security import current_user, owned
from app.modules.acceptances.models import Acceptance
from app.modules.acceptances.schemas import AcceptanceInput, Confirmation, acceptance_view
from app.modules.acceptances import service

router = APIRouter(prefix='/api/v1', tags=['受理'])


@router.post('/acceptances', status_code=201)
async def create(data: AcceptanceInput, idempotency_key: str = Header(alias='Idempotency-Key', min_length=8, max_length=120), user=Depends(current_user), db=Depends(get_db)):
    return acceptance_view(await service.create(db, user, data, idempotency_key))


@router.get('/acceptances')
async def listing(service_id: UUID | None = None, user=Depends(current_user), db=Depends(get_db)):
    statement = select(Acceptance).where(Acceptance.store_id == user.store_id)
    if service_id: statement = statement.where(Acceptance.service_id == service_id)
    rows = (await db.scalars(statement.order_by(Acceptance.created_at.desc()).limit(100))).all()
    return {'items': [acceptance_view(r) for r in rows], 'total': len(rows), 'page': 1, 'page_size': 100}


@router.get('/acceptances/{aid}')
async def detail(aid: UUID, user=Depends(current_user), db=Depends(get_db)):
    return acceptance_view(await owned(db, Acceptance, aid, user))


@router.post('/acceptances/{aid}/confirm')
async def confirm(aid: UUID, data: Confirmation, response: Response, user=Depends(current_user), db=Depends(get_db)):
    row = await service.confirm(db, user, aid, data)
    if row.status in ('UNKNOWN','SUBMITTING','SUBMITTED'): response.status_code = 202
    return acceptance_view(row)


@router.post('/acceptances/{aid}/reconcile')
async def reconcile(aid: UUID, user=Depends(current_user), db=Depends(get_db)):
    return acceptance_view(await service.reconcile(db, user, aid))


@router.post('/acceptances/{aid}/cancel')
async def cancel(aid: UUID, user=Depends(current_user), db=Depends(get_db)):
    return acceptance_view(await service.cancel(db, user, aid))
