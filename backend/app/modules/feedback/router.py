from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import select
from app.core.db import get_db
from app.core.security import current_user, owned
from app.modules.feedback.models import Feedback
from app.modules.feedback.schemas import FeedbackInput
from app.modules.feedback import service
from app.modules.services.models import ServiceSession

router = APIRouter(prefix='/api/v1', tags=['客户评价'])


@router.post('/service-sessions/{sid}/feedback-link')
async def issue(sid: UUID, user=Depends(current_user), db=Depends(get_db)):
    return await service.issue(db, user, sid)


@router.post('/public/feedback')
async def submit(data: FeedbackInput, db=Depends(get_db)):
    return await service.submit(db, data)


@router.get('/service-sessions/{sid}/feedback')
async def detail(sid: UUID, user=Depends(current_user), db=Depends(get_db)):
    await owned(db, ServiceSession, sid, user)
    row = await db.scalar(select(Feedback).where(Feedback.service_id == sid))
    return {'feedback': {k: getattr(row, k) for k in ('id','score','tags','comment','created_at')} if row else None}
