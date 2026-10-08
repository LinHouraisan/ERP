import re
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func
from app.core.db import get_db
from app.core.security import current_user, owned, require_role
from app.modules.auth.models import Store
from app.modules.recommendations.models import AIRun, PromptVersion, Recommendation
from app.modules.recommendations.ai_service import execute, interrupt_expired, run_view
from app.modules.services.models import ServiceSession

router = APIRouter(prefix='/api/v1', tags=['AI 辅助与版本'])


class PromptInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    scenario: Literal['demand', 'explanation', 'quality', 'improvement', 'sales', 'operations']
    text: str = Field(min_length=1, max_length=12000)


class AssistInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_key: str = Field(min_length=8, max_length=120)
    text: str = Field(default='', max_length=4000)


@router.get('/prompt-versions')
async def prompts(user=Depends(current_user), db=Depends(get_db)):
    rows = (await db.scalars(select(PromptVersion).where(PromptVersion.store_id == user.store_id).order_by(PromptVersion.created_at.desc()))).all()
    return {'items': [{'id': p.id, 'scenario': p.scenario, 'version': p.version, 'status': p.status, 'text': p.text} for p in rows], 'total': len(rows), 'page': 1, 'page_size': len(rows)}


@router.post('/prompt-versions', status_code=201)
async def new_prompt(data: PromptInput, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'ADMIN')
    await db.scalar(select(Store).where(Store.id == user.store_id).with_for_update())
    version = (await db.scalar(select(func.max(PromptVersion.version)).where(PromptVersion.store_id == user.store_id, PromptVersion.scenario == data.scenario)) or 0) + 1
    row = PromptVersion(store_id=user.store_id, version=version, **data.model_dump())
    db.add(row); await db.commit()
    return {'id': row.id, 'version': row.version, 'status': row.status}


@router.post('/prompt-versions/{pid}/publish')
async def publish_prompt(pid: UUID, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'ADMIN')
    row = await owned(db, PromptVersion, pid, user, lock=True)
    if row.status != 'PUBLISHED': row.status = 'PUBLISHED'; await db.commit()
    return {'id': row.id, 'status': row.status}


@router.post('/service-sessions/{sid}/analyze')
async def analyze(sid: UUID, data: AssistInput, user=Depends(current_user), db=Depends(get_db)):
    await owned(db, ServiceSession, sid, user)
    payload = {'text': re.sub(r'\d{7,}', '[号码已脱敏]', data.text)}
    return run_view(await execute(db, user, 'demand', payload, data.request_key, service_id=sid))


@router.post('/recommendations/{rid}/explain')
async def explain(rid: UUID, data: AssistInput, user=Depends(current_user), db=Depends(get_db)):
    row = await owned(db, Recommendation, rid, user)
    return run_view(await execute(db, user, 'explanation', {'candidates': row.candidates}, data.request_key, service_id=row.service_id, prompt_id=row.prompt_version_id))


@router.get('/ai-runs')
async def runs(user=Depends(current_user), db=Depends(get_db)):
    rows = (await db.scalars(select(AIRun).where(AIRun.store_id == user.store_id).order_by(AIRun.created_at.desc()).limit(100))).all()
    return {'items': [run_view(row) for row in rows], 'total': len(rows), 'page': 1, 'page_size': 100}


@router.get('/ai-runs/{rid}')
async def run(rid: UUID, user=Depends(current_user), db=Depends(get_db)):
    return run_view(await interrupt_expired(db, await owned(db, AIRun, rid, user)))
