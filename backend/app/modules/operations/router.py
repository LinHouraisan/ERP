from datetime import timedelta
from uuid import UUID
from fastapi import APIRouter, Depends
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl
from sqlalchemy import select
from app.core.db import get_db, utcnow
from app.core.security import current_user, owned, require_role
from app.modules.inventory.schemas import RequestKey
from app.modules.recommendations.ai_service import execute, run_view
from app.modules.operations.models import OperationsSnapshot, GEOSample
from app.modules.operations import service

router = APIRouter(prefix='/api/v1/operations', tags=['经营看板与 GEO'])


class SummaryInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    snapshot_id: UUID
    request_key: RequestKey
    question: str = Field(default='概括本期经营情况，并指出需要核查的事项。', max_length=2000)


class GEOSampleInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    platform: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=12000)
    brand: str = Field(min_length=1, max_length=100)
    captured_at: AwareDatetime
    simulated: bool = Field(strict=True)
    citations: list[HttpUrl] = Field(default_factory=list, max_length=30)
    factual_errors: str = Field(default='', max_length=3000)


class GEOInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_key: RequestKey
    samples: list[GEOSampleInput] = Field(min_length=1, max_length=100)


def snapshot_view(row):
    return {'id': row.id, 'filters': row.filters, 'metrics': row.metrics, 'created_at': row.created_at}


@router.get('/overview')
async def overview(start: AwareDatetime | None = None, end: AwareDatetime | None = None, user=Depends(current_user), db=Depends(get_db)):
    return snapshot_view(await service.overview(db, user, start or utcnow()-timedelta(days=30), end or utcnow()))


@router.get('/snapshots/{sid}')
async def detail(sid: UUID, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'MANAGER', 'ADMIN')
    return snapshot_view(await owned(db, OperationsSnapshot, sid, user))


@router.post('/summary')
async def summary(data: SummaryInput, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'MANAGER', 'ADMIN')
    row = await owned(db, OperationsSnapshot, data.snapshot_id, user)
    import re
    payload = {'filters': row.filters, 'metrics': row.metrics, 'question': re.sub(r'\d{7,}', '[号码已脱敏]', data.question)}
    return run_view(await execute(db, user, 'operations', payload, data.request_key))


@router.post('/geo-samples')
async def add_geo(data: GEOInput, user=Depends(current_user), db=Depends(get_db)):
    return await service.import_geo(db, user, data)


@router.get('/geo-samples')
async def geo(user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'MANAGER', 'ADMIN')
    rows = (await db.scalars(select(GEOSample).where(GEOSample.store_id == user.store_id).order_by(GEOSample.captured_at.desc(), GEOSample.id).limit(300))).all()
    return {'items': [{k: getattr(s, k) for k in ('id','platform','question','answer','brand','captured_at','simulated','mentioned','citations','factual_errors')} for s in rows],
        'sample_counts': {label: {'sample_count': len([r for r in rows if r.simulated == flag]), 'mentioned_count': len([r for r in rows if r.simulated == flag and r.mentioned])} for label, flag in [('simulated',True),('real',False)]},
        'definition': '最近 300 条人工采样的品牌字面命中；真实与模拟分别计数，不代表平台总体曝光或推荐份额。事实错误为人工核查备注。'}
