from sqlalchemy import func, select
from app.core.config import business_date
from app.core.db import utcnow
from app.core.errors import DomainError
from app.core.security import owned, require_role
from app.modules.auth.models import Store
from app.modules.queue.models import QueueTicket, QueueEvent, Window
from app.modules.services.service import open_service, finish_service


def event(db, ticket, action, before=None, actor_id=None, reason=''):
    db.add(QueueEvent(store_id=ticket.store_id, ticket_id=ticket.id, actor_id=actor_id,
        action=action, from_status=before, to_status=ticket.status, reason=reason))


async def take_ticket(db, store_id, category):
    store = await db.scalar(select(Store).where(Store.id == store_id).with_for_update())
    if store is None: raise DomainError('STORE_UNAVAILABLE', '门店尚未初始化', 503)
    day = business_date()
    sequence = (await db.scalar(select(func.max(QueueTicket.sequence)).where(QueueTicket.store_id == store_id, QueueTicket.business_day == day)) or 0) + 1
    row = QueueTicket(store_id=store_id, category=category, business_day=day, sequence=sequence,
        ticket_number={'PLAN':'A','FAULT':'B','OTHER':'C'}[category]+str(sequence).zfill(3))
    db.add(row); await db.flush(); event(db, row, 'TAKEN'); await db.commit()
    return row


async def call_next(db, user, window_id):
    # ponytail: three demo windows serialize per store; split scheduling locks only after measured contention.
    await db.scalar(select(Store).where(Store.id == user.store_id).with_for_update())
    window = await owned(db, Window, window_id, user, lock=True)
    current = await db.scalar(select(QueueTicket).where(QueueTicket.window_id == window_id, QueueTicket.status.in_(['CALLED','SERVING'])))
    if current:
        await db.commit(); return current
    row = await db.scalar(select(QueueTicket).where(QueueTicket.store_id == user.store_id,
        QueueTicket.status == 'WAITING', QueueTicket.category.in_(window.categories)).order_by(QueueTicket.queued_at, QueueTicket.id).limit(1).with_for_update())
    if row:
        row.status, row.window_id, row.called_at = 'CALLED', window_id, utcnow()
        row.round_wait_seconds = max(0, int((row.called_at-row.queued_at).total_seconds()))
        row.cumulative_wait_seconds += row.round_wait_seconds
        event(db, row, 'CALLED', 'WAITING', user.user_id)
    await db.commit()
    return row


async def transition(db, user, tid, action, data):
    await db.scalar(select(Store).where(Store.id == user.store_id).with_for_update())
    row = await owned(db, QueueTicket, tid, user)
    if row.window_id: await owned(db, Window, row.window_id, user, lock=True)
    row = await owned(db, QueueTicket, tid, user, lock=True)
    before = row.status
    allowed = {'start': {'CALLED','SERVING'}, 'finish': {'SERVING','DONE'}, 'miss': {'CALLED'},
               'cancel': {'WAITING','CALLED'}, 'requeue': {'MISSED'}, 'adjust': {'WAITING'}}
    if action not in allowed or before not in allowed[action]: raise DomainError('INVALID_TRANSITION', '当前排队状态不能执行该操作')
    if (action == 'start' and before == 'SERVING') or (action == 'finish' and before == 'DONE'):
        await db.commit(); return row
    if action == 'start':
        service = await open_service(db, user, row.category)
        row.service_id, row.status = service.id, 'SERVING'
    elif action == 'finish': row.status = 'DONE'
    elif action == 'miss': row.status = 'MISSED'
    elif action == 'cancel':
        if before == 'WAITING': row.cumulative_wait_seconds += max(0, int((utcnow()-row.queued_at).total_seconds()))
        row.status = 'CANCELLED'
    elif action == 'requeue':
        row.status, row.window_id, row.queued_at, row.called_at, row.round_wait_seconds = 'WAITING', None, utcnow(), None, None
    elif action == 'adjust':
        require_role(user, 'MANAGER', 'ADMIN')
        if not data.reason.strip() or data.category is None: raise DomainError('REASON_REQUIRED', '调整类别必须选择类别并填写原因', 422)
        row.category = data.category
    event(db, row, action.upper(), before, user.user_id, data.reason)
    if action == 'finish': await finish_service(db, user, row.service_id)
    await db.commit()
    return row
