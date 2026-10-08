from app.core.db import utcnow
from app.core.errors import DomainError
from app.core.security import owned
from app.modules.services.models import ServiceSession, ServiceEvent, ServiceTask


def event(db, user, service_id, action, detail=None):
    db.add(ServiceEvent(store_id=user.store_id, service_id=service_id, actor_id=user.user_id, action=action, detail=detail or {}))


async def open_service(db, user, category):
    row = ServiceSession(store_id=user.store_id, staff_id=user.user_id, category=category)
    db.add(row); await db.flush()
    event(db, user, row.id, 'STARTED')
    return row


async def create_service(db, user, category):
    row = await open_service(db, user, category)
    await db.commit()
    return row


async def finish_service(db, user, sid):
    row = await owned(db, ServiceSession, sid, user, lock=True)
    if row.status == 'ACTIVE':
        row.status, row.ended_at = 'ENDED', utcnow()
        event(db, user, sid, 'ENDED')
        await db.commit()
    return row


def require_active(row):
    if row.status != 'ACTIVE':
        raise DomainError('SERVICE_ENDED', '接待已结束，请新建服务')


async def create_task(db, user, data):
    await owned(db, ServiceSession, data.service_id, user)
    row = ServiceTask(store_id=user.store_id, **data.model_dump())
    db.add(row); await db.flush()
    event(db, user, row.service_id, 'TASK_CREATED', {'task_id': str(row.id), 'title': row.title})
    await db.commit()
    return row


async def transition_task(db, user, tid, data):
    row = await owned(db, ServiceTask, tid, user, lock=True)
    allowed = {'OPEN': {'IN_PROGRESS', 'CANCELLED'}, 'IN_PROGRESS': {'CLOSED', 'CANCELLED'}}
    if data.status not in allowed.get(row.status, set()):
        raise DomainError('INVALID_TRANSITION', '此任务不能执行该状态变更')
    before = row.status
    row.status, row.note = data.status, data.note
    event(db, user, row.service_id, 'TASK_TRANSITION', {'task_id': str(tid), 'from': before, 'to': row.status, 'note': data.note})
    await db.commit()
    return row
