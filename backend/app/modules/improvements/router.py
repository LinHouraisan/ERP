from datetime import timedelta
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends
from pydantic import AwareDatetime
from sqlalchemy import select
from app.core.db import get_db, utcnow
from app.core.security import current_user, owned, require_role
from app.modules.auth.models import User
from app.modules.improvements.models import MetricsSnapshot, ImprovementTask, ImprovementEvent
from app.modules.improvements.schemas import ProposalInput, ManualTask, TaskTransition, task_view
from app.modules.improvements import service

router = APIRouter(prefix='/api/v1', tags=['复盘改进'])


def snapshot_view(row):
    return {'snapshot_id': row.id, 'store_id': row.store_id, 'filters': row.filters, 'metrics': row.payload, 'evidence': row.evidence, 'created_at': row.created_at}


@router.get('/service-metrics')
async def metrics(start: AwareDatetime | None = None, end: AwareDatetime | None = None, category: Literal['PLAN','FAULT','OTHER'] | None = None, user=Depends(current_user), db=Depends(get_db)):
    return snapshot_view(await service.metrics(db,user,start or utcnow()-timedelta(days=30),end or utcnow(),category))


@router.get('/metric-snapshots/{sid}')
async def snapshot(sid: UUID, user=Depends(current_user), db=Depends(get_db)):
    require_role(user,'MANAGER','ADMIN')
    return snapshot_view(await owned(db,MetricsSnapshot,sid,user))


@router.get('/staff')
async def staff(user=Depends(current_user), db=Depends(get_db)):
    require_role(user,'MANAGER','ADMIN')
    rows=(await db.scalars(select(User).where(User.store_id==user.store_id,User.active.is_(True)))).all()
    return {'items':[{'id':u.id,'username':u.username,'role':u.role} for u in rows]}


@router.post('/improvement-proposals', status_code=201)
async def propose(data: ProposalInput, user=Depends(current_user), db=Depends(get_db)):
    return task_view(await service.propose(db,user,data))


@router.post('/improvement-tasks', status_code=201)
async def manual(data: ManualTask, user=Depends(current_user), db=Depends(get_db)):
    require_role(user,'MANAGER','ADMIN')
    await owned(db,MetricsSnapshot,data.snapshot_id,user)
    row=ImprovementTask(store_id=user.store_id,snapshot_id=data.snapshot_id,suggestion={'suggestion':data.suggestion,'source':'MANUAL'})
    db.add(row); await db.commit()
    return task_view(row)


@router.get('/improvement-tasks')
async def tasks(user=Depends(current_user), db=Depends(get_db)):
    require_role(user,'MANAGER','ADMIN')
    rows=(await db.scalars(select(ImprovementTask).where(ImprovementTask.store_id==user.store_id).order_by(ImprovementTask.created_at.desc()).limit(100))).all()
    return {'items':[task_view(r) for r in rows],'total':len(rows),'page':1,'page_size':100}


@router.get('/improvement-tasks/{tid}')
async def detail(tid: UUID, user=Depends(current_user), db=Depends(get_db)):
    require_role(user,'MANAGER','ADMIN')
    row=await owned(db,ImprovementTask,tid,user)
    events=(await db.scalars(select(ImprovementEvent).where(ImprovementEvent.task_id==tid).order_by(ImprovementEvent.created_at))).all()
    return {**task_view(row),'events':[{'from':e.from_status,'to':e.to_status,'reason':e.reason,'at':e.created_at} for e in events]}


@router.post('/improvement-tasks/{tid}/transition')
async def transition(tid: UUID, data: TaskTransition, user=Depends(current_user), db=Depends(get_db)):
    return task_view(await service.transition(db,user,tid,data))
