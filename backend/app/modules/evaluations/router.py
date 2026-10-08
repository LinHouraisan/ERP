from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import select
from app.core.db import get_db
from app.core.security import current_user, owned, require_role
from app.modules.evaluations.models import EvaluationRun, EvaluationResult
from app.modules.recommendations.models import AIRun
from app.modules.recommendations.ai_service import run_view

router=APIRouter(prefix='/api/v1/evaluation-runs',tags=['评测记录'])


def view(row):
    return {k:getattr(row,k) for k in ('id','prompt_version_id','status','settings','metrics','created_at','updated_at')}


@router.get('')
async def runs(user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'ADMIN','MANAGER')
    rows=(await db.scalars(select(EvaluationRun).where(EvaluationRun.store_id==user.store_id).order_by(EvaluationRun.created_at.desc()).limit(100))).all()
    return {'items':[view(r) for r in rows]}


@router.get('/{rid}')
async def detail(rid: UUID,user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'ADMIN','MANAGER')
    row=await owned(db,EvaluationRun,rid,user)
    results=(await db.scalars(select(EvaluationResult).where(EvaluationResult.run_id==rid).order_by(EvaluationResult.case_id))).all()
    items=[]
    for r in results:
        ai=await db.get(AIRun,r.ai_run_id) if r.ai_run_id else None
        items.append({**{k:getattr(r,k) for k in ('case_id','input','status','actual_issue_ids','deterministic_findings','error')},'ai_run':run_view(ai) if ai else None})
    return {**view(row),'results':items,'recovery_note':'中断批次不会自动续跑；PENDING 表示尚无结果。重新执行会新建批次。'}
