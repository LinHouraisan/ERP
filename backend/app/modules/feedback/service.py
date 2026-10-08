import secrets
from datetime import timedelta
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.core.db import utcnow
from app.core.digests import content_hash
from app.core.errors import DomainError
from app.core.security import owned
from app.modules.auth.service import digest
from app.modules.feedback.models import Feedback, FeedbackToken
from app.modules.services.models import ServiceSession
from app.modules.services.service import event


async def issue(db, user, sid):
    service = await owned(db, ServiceSession, sid, user, lock=True)
    if service.status != 'ENDED': raise DomainError('NOT_ENDED', '接待结束后才能生成评价链接')
    if await db.scalar(select(Feedback.id).where(Feedback.service_id == sid)):
        raise DomainError('ALREADY_RATED', '本次服务已评价')
    token = secrets.token_urlsafe(32)
    row = FeedbackToken(store_id=user.store_id, service_id=sid, token_hash=digest(token), expires_at=utcnow()+timedelta(hours=24))
    db.add(row); event(db, user, sid, 'FEEDBACK_LINK_CREATED')
    await db.commit()
    return {'token': token, 'expires_at': row.expires_at, 'path': '/feedback#token='+token}


async def submit(db, data):
    token = await db.scalar(select(FeedbackToken).where(FeedbackToken.token_hash == digest(data.token)))
    if token is None: raise DomainError('INVALID_TOKEN', '评价链接无效', 404)
    if token.expires_at <= utcnow(): raise DomainError('EXPIRED_TOKEN', '评价链接已过期，请联系工作人员', 410)
    values = {'score': data.score, 'tags': sorted(set(data.tags)), 'comment': data.comment}
    ih = content_hash(values)
    await db.execute(insert(Feedback).values(store_id=token.store_id, service_id=token.service_id, content_hash=ih, **values).on_conflict_do_nothing(index_elements=['service_id']))
    row = await db.scalar(select(Feedback).where(Feedback.service_id == token.service_id))
    if row.content_hash != ih: raise DomainError('FEEDBACK_CONFLICT', '本次服务已评价，不能更改原评价')
    await db.commit()
    return {'feedback_id': row.id, 'submitted': True, 'score': row.score}
