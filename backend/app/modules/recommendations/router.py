from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import select
from app.core.db import get_db
from app.core.security import current_user, owned
from app.modules.recommendations.models import Recommendation
from app.modules.recommendations.schemas import RecommendationInput, RecommendationOut, recommendation_view
from app.modules.recommendations.service import create
from app.modules.services.models import ServiceSession

router = APIRouter(prefix='/api/v1', tags=['方案'])


@router.post('/service-sessions/{sid}/recommendations', response_model=RecommendationOut, status_code=201)
async def make(sid: UUID, data: RecommendationInput, user=Depends(current_user), db=Depends(get_db)):
    return recommendation_view(await create(db, user, sid, data))


@router.get('/service-sessions/{sid}/recommendations')
async def history(sid: UUID, user=Depends(current_user), db=Depends(get_db)):
    await owned(db,ServiceSession,sid,user)
    rows=(await db.scalars(select(Recommendation).where(Recommendation.service_id==sid).order_by(Recommendation.revision.desc()))).all()
    return {'items':[recommendation_view(r) for r in rows]}


@router.get('/recommendations/{rid}', response_model=RecommendationOut)
async def detail(rid: UUID, user=Depends(current_user), db=Depends(get_db)):
    return recommendation_view(await owned(db, Recommendation, rid, user))
