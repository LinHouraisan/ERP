from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from app.core.db import get_db
from app.core.digests import content_hash
from app.core.errors import DomainError
from app.core.security import current_user, owned, require_role
from app.integrations import boss
from app.modules.acceptances.models import Acceptance
from app.modules.installations.models import Installation
from app.modules.aftersales.models import Reversal, ReversalEvent
from app.modules.aftersales.schemas import Review, Note
from app.modules.inventory.schemas import RequestKey

router = APIRouter(prefix='/api/v1/reversals', tags=['通信冲正'])


class Create(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_key: RequestKey
    acceptance_id: UUID
    reason: str = Field(min_length=1, max_length=1000)
    scenario: Literal['NORMAL','SUCCESS_TIMEOUT','DECLINED'] = 'NORMAL'


def event(db, user, row, action, detail):
    db.add(ReversalEvent(store_id=user.store_id, reversal_id=row.id, actor_id=user.user_id, action=action, detail=detail))


async def view(db, row):
    events = (await db.scalars(select(ReversalEvent).where(ReversalEvent.reversal_id == row.id).order_by(ReversalEvent.created_at))).all()
    return {**{k: getattr(row,k) for k in ('id','acceptance_id','actor_id','approved_by','reason','status','external_request_id',
        'external_reversal_id','last_error','resolution','created_at')}, 'simulated': True,
        'events':[{'action':e.action,'detail':e.detail,'actor_id':e.actor_id,'at':e.created_at} for e in events]}


@router.get('')
async def listing(user=Depends(current_user), db=Depends(get_db)):
    rows = (await db.scalars(select(Reversal).where(Reversal.store_id == user.store_id).order_by(Reversal.created_at.desc()).limit(100))).all()
    return {'items':[await view(db,row) for row in rows]}


@router.get('/{rid}')
async def detail(rid: UUID, user=Depends(current_user), db=Depends(get_db)):
    return await view(db, await owned(db, Reversal, rid, user))


@router.post('')
async def create(data: Create, user=Depends(current_user), db=Depends(get_db)):
    require_role(user,'STAFF','MANAGER','ADMIN')
    source = await owned(db, Acceptance, data.acceptance_id, user, lock=True)
    ih = content_hash(data.model_dump(mode='json'))
    old = await db.scalar(select(Reversal).where(Reversal.store_id == user.store_id, Reversal.request_key == data.request_key))
    if old:
        if old.input_hash != ih: raise DomainError('KEY_CONFLICT', '冲正请求号不能更换内容')
        return await view(db,old)
    if source.status != 'SUCCESS': raise DomainError('SOURCE_INCOMPLETE', '原受理未成功，不得提交冲正')
    if await db.scalar(select(Reversal.id).where(Reversal.acceptance_id == source.id)): raise DomainError('REVERSAL_EXISTS', '原受理已有冲正记录，请在原记录核查或补充人工依据')
    row = Reversal(store_id=user.store_id, actor_id=user.user_id, input_hash=ih, **data.model_dump())
    db.add(row); await db.flush(); event(db,user,row,'REQUESTED',{'reason':data.reason})
    await db.commit(); return await view(db,row)


@router.post('/{rid}/review')
async def review(rid: UUID, data: Review, user=Depends(current_user), db=Depends(get_db)):
    require_role(user,'MANAGER','ADMIN')
    row = await owned(db, Reversal, rid, user, lock=True)
    target = 'APPROVED' if data.decision=='APPROVE' else 'REJECTED'
    if row.status == target: return await view(db,row)
    if row.status != 'REQUESTED': raise DomainError('REVIEWED', '已审批的冲正不能覆盖')
    row.status, row.approved_by = target, user.user_id
    event(db,user,row,target,{'note':data.note}); await db.commit(); return await view(db,row)


async def execute(db, user, rid, lookup):
    require_role(user,'MANAGER','ADMIN')
    row = await owned(db, Reversal, rid, user)
    source = await owned(db, Acceptance, row.acceptance_id, user, lock=True)
    row = await owned(db, Reversal, rid, user, lock=True)
    if row.status in ('SUCCESS','FAILED'): return await view(db,row)
    if row.status not in ('APPROVED','PENDING','UNKNOWN'): raise DomainError('APPROVAL_REQUIRED', '冲正须由店长批准')
    job = await db.scalar(select(Installation).where(Installation.source_acceptance_id == source.id).with_for_update())
    if job and job.status not in ('COMPLETED','CANCELLED'): raise DomainError('SERVICE_PENDING', '先处理关联装维，不能在施工中冲正')
    if job and job.status == 'COMPLETED' and not row.resolution: raise DomainError('SERVICE_EVIDENCE', '已履约装维需要人工处理依据')
    lookup = lookup or row.status in ('PENDING','UNKNOWN')
    payload = {'external_request_id':str(row.external_request_id), 'original_request_id':str(source.external_request_id), 'scenario':row.scenario}
    row.status = 'PENDING'; event(db,user,row,'SUBMITTED',{'external_request_id':str(row.external_request_id)}); await db.commit()
    try:
        result = await boss.reversal_request('GET',f'/mock/v1/reversals/by-request/{row.external_request_id}') if lookup else {'status':'NOT_FOUND'}
        if result['status']=='NOT_FOUND': result = await boss.reversal_request('POST','/mock/v1/reversals',payload)
    except DomainError: result = {'status':'UNKNOWN'}
    await owned(db, Acceptance, row.acceptance_id, user, lock=True)
    row = await owned(db, Reversal, rid, user, lock=True)
    if row.status in ('SUCCESS','FAILED'): return await view(db,row)
    status = result.get('status')
    if status not in ('SUCCESS','FAILED') or not result.get('external_reversal_id') or any(result.get(k)!=payload[k] for k in ('external_request_id','original_request_id')): status='UNKNOWN'
    row.status = status
    row.last_error = '冲正结果未知，请按原请求号核对' if status=='UNKNOWN' else result.get('reason')
    if status in ('SUCCESS','FAILED'): row.external_reversal_id = UUID(result['external_reversal_id'])
    if status=='SUCCESS':
        from app.modules.finance.adjustments import reversal_adjustment
        await reversal_adjustment(db,user,row)
    event(db,user,row,status,{'external_request_id':str(row.external_request_id), 'reason':row.last_error})
    await db.commit(); return await view(db,row)


@router.post('/{rid}/submit')
async def submit(rid: UUID, user=Depends(current_user), db=Depends(get_db)):
    return await execute(db,user,rid,False)


@router.post('/{rid}/reconcile')
async def reconcile(rid: UUID, user=Depends(current_user), db=Depends(get_db)):
    return await execute(db,user,rid,True)


@router.post('/{rid}/resolution')
async def resolution(rid: UUID, data: Note, user=Depends(current_user), db=Depends(get_db)):
    require_role(user,'MANAGER','ADMIN')
    row = await owned(db,Reversal,rid,user,lock=True)
    if row.status not in ('APPROVED','FAILED') or row.resolution: raise DomainError('IMMUTABLE', '只能补充尚未记录的已批准或失败冲正的人工依据')
    row.resolution = data.note; event(db,user,row,'MANUAL_EVIDENCE',{'note':data.note})
    await db.commit(); return await view(db,row)
