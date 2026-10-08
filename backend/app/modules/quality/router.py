from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import select
from app.core.db import get_db
from app.core.security import current_user, owned
from app.modules.quality.models import QualityCheck, QualityReview
from app.modules.quality.schemas import QualityInput, RecommendationCheck, ReviewInput, quality_view
from app.modules.quality import service

router = APIRouter(prefix='/api/v1', tags=['质检与复核'])


@router.post('/quality-checks', status_code=201)
async def create(data: QualityInput, user=Depends(current_user), db=Depends(get_db)):
    return quality_view(await service.create(db, user, data))


@router.post('/recommendations/{rid}/quality-checks', status_code=201)
async def recommendation_check(rid: UUID, data: RecommendationCheck, user=Depends(current_user), db=Depends(get_db)):
    return quality_view(await service.create(db, user, QualityInput(target_type='RECOMMENDATION', target_id=rid, **data.model_dump())))


@router.get('/quality-checks')
async def checks(target_id: UUID | None = None, user=Depends(current_user), db=Depends(get_db)):
    statement=select(QualityCheck).where(QualityCheck.store_id == user.store_id)
    if target_id: statement=statement.where(QualityCheck.target_id == target_id)
    rows = (await db.scalars(statement.order_by(QualityCheck.created_at.desc()).limit(100))).all()
    return {'items': [quality_view(q) for q in rows], 'total': len(rows), 'page': 1, 'page_size': 100}


@router.get('/quality-checks/{qid}')
async def detail(qid: UUID, user=Depends(current_user), db=Depends(get_db)):
    q = await owned(db, QualityCheck, qid, user)
    rows = (await db.scalars(select(QualityReview).where(QualityReview.quality_check_id == qid).order_by(QualityReview.created_at))).all()
    return {**quality_view(q), 'reviews': [{'id': r.id, 'decision': r.decision, 'reason': r.reason, 'revised_text': r.revised_text, 'created_at': r.created_at} for r in rows]}


@router.post('/quality-checks/{qid}/reviews')
async def review(qid: UUID, data: ReviewInput, user=Depends(current_user), db=Depends(get_db)):
    return await service.review(db, user, qid, data)
