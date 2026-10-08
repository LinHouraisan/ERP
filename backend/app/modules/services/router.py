from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from app.core.db import get_db
from app.core.security import current_user, owned
from app.modules.accounts.models import AccountSnapshot
from app.modules.accounts.schemas import AccountQuery, snapshot_view
from app.modules.accounts.service import query
from app.modules.services.models import ServiceSession, ServiceEvent
from app.modules.services.schemas import ServiceCreate, ServiceOut, service_view
from app.modules.services.service import create_service, finish_service
from app.modules.services.service import create_task, transition_task
from app.modules.services.models import ServiceTask
from app.modules.services.schemas import TaskCreate, TaskTransition, TaskOut

router = APIRouter(prefix='/api/v1', tags=['服务与查询'])


@router.post('/service-sessions', response_model=ServiceOut, status_code=201)
async def create(data: ServiceCreate, user=Depends(current_user), db=Depends(get_db)):
    return service_view(await create_service(db, user, data.category))


@router.get('/service-sessions')
async def listing(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), user=Depends(current_user), db=Depends(get_db)):
    rows = (await db.scalars(select(ServiceSession).where(ServiceSession.store_id == user.store_id).order_by(ServiceSession.created_at.desc()).offset((page-1)*page_size).limit(page_size))).all()
    return {'items': [service_view(row) for row in rows], 'total': await db.scalar(select(func.count()).select_from(ServiceSession).where(ServiceSession.store_id == user.store_id)), 'page': page, 'page_size': page_size}


@router.get('/service-sessions/{sid}')
async def detail(sid: UUID, user=Depends(current_user), db=Depends(get_db)):
    row = await owned(db, ServiceSession, sid, user)
    snapshots = (await db.scalars(select(AccountSnapshot).where(AccountSnapshot.service_id == sid).order_by(AccountSnapshot.created_at))).all()
    events = (await db.scalars(select(ServiceEvent).where(ServiceEvent.service_id == sid).order_by(ServiceEvent.created_at))).all()
    return {**service_view(row).model_dump(), 'snapshots': [snapshot_view(s) for s in snapshots],
            'events': [{'action': e.action, 'at': e.created_at, 'detail': e.detail} for e in events]}


@router.post('/service-sessions/{sid}/finish', response_model=ServiceOut)
async def finish(sid: UUID, user=Depends(current_user), db=Depends(get_db)):
    from app.modules.queue.models import QueueTicket
    from app.modules.queue.service import transition
    from app.modules.queue.schemas import TicketAction
    await owned(db,ServiceSession,sid,user)
    ticket=await db.scalar(select(QueueTicket).where(QueueTicket.service_id==sid,QueueTicket.store_id==user.store_id))
    if ticket:
        await transition(db,user,ticket.id,'finish',TicketAction())
        return service_view(await owned(db,ServiceSession,sid,user))
    return service_view(await finish_service(db, user, sid))


@router.post('/service-sessions/{sid}/account-query')
async def account_query(sid: UUID, data: AccountQuery, user=Depends(current_user), db=Depends(get_db)):
    snapshot = await query(db, user, sid, data)
    return snapshot_view(snapshot) if snapshot else {'status': 'NOT_FOUND'}


@router.get('/account-snapshots/{snapshot_id}')
async def snapshot_detail(snapshot_id: UUID, user=Depends(current_user), db=Depends(get_db)):
    return snapshot_view(await owned(db, AccountSnapshot, snapshot_id, user))


@router.get('/service-tasks')
async def tasks(service_id: UUID | None = None, user=Depends(current_user), db=Depends(get_db)):
    statement = select(ServiceTask).where(ServiceTask.store_id == user.store_id)
    if service_id: statement = statement.where(ServiceTask.service_id == service_id)
    rows = (await db.scalars(statement.order_by(ServiceTask.created_at.desc()).limit(100))).all()
    return {'items': [TaskOut.model_validate(r) for r in rows], 'total': len(rows), 'page': 1, 'page_size': 100}


@router.post('/service-tasks', response_model=TaskOut, status_code=201)
async def new_task(data: TaskCreate, user=Depends(current_user), db=Depends(get_db)):
    return await create_task(db, user, data)


@router.post('/service-tasks/{tid}/transition', response_model=TaskOut)
async def change_task(tid: UUID, data: TaskTransition, user=Depends(current_user), db=Depends(get_db)):
    return await transition_task(db, user, tid, data)
