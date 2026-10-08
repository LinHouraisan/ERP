from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import select
from app.core.db import get_db, utcnow
from app.core.security import current_user, owned
from app.modules.queue.models import Window, QueueTicket, QueueEvent
from app.modules.queue.schemas import TicketCreate, TicketAction, public_ticket, ticket_view
from app.modules.queue import service
from app.seed import DEMO_STORE

router = APIRouter(prefix='/api/v1', tags=['排队'])


@router.post('/public/queue-tickets', status_code=201)
async def take(data: TicketCreate, db=Depends(get_db)):
    return public_ticket(await service.take_ticket(db, DEMO_STORE, data.category))


@router.get('/public/queue-board')
async def board(db=Depends(get_db)):
    rows = (await db.execute(select(QueueTicket, Window.name).outerjoin(Window, Window.id == QueueTicket.window_id).where(
        QueueTicket.store_id == DEMO_STORE, QueueTicket.status.in_(['WAITING','CALLED','SERVING'])).order_by(QueueTicket.queued_at, QueueTicket.id).limit(100))).all()
    return {'items': [public_ticket(row, name) for row, name in rows], 'updated_at': utcnow()}


@router.get('/windows')
async def windows(user=Depends(current_user), db=Depends(get_db)):
    rows = (await db.scalars(select(Window).where(Window.store_id == user.store_id).order_by(Window.name))).all()
    return {'items': [{'id': row.id, 'name': row.name, 'categories': row.categories} for row in rows], 'total': len(rows), 'page': 1, 'page_size': 100}


@router.get('/queue-tickets')
async def tickets(user=Depends(current_user), db=Depends(get_db)):
    rows = (await db.scalars(select(QueueTicket).where(QueueTicket.store_id == user.store_id).order_by(QueueTicket.created_at.desc()).limit(100))).all()
    return {'items': [ticket_view(row) for row in rows], 'total': len(rows), 'page': 1, 'page_size': 100}


@router.post('/windows/{wid}/call-next')
async def call(wid: UUID, user=Depends(current_user), db=Depends(get_db)):
    row = await service.call_next(db, user, wid)
    return {'ticket': ticket_view(row) if row else None}


@router.get('/queue-tickets/{tid}')
async def detail(tid: UUID, user=Depends(current_user), db=Depends(get_db)):
    row=await owned(db,QueueTicket,tid,user)
    events=(await db.scalars(select(QueueEvent).where(QueueEvent.ticket_id==tid).order_by(QueueEvent.created_at))).all()
    return {**ticket_view(row),'events':[{'action':e.action,'from':e.from_status,'to':e.to_status,'reason':e.reason,'at':e.created_at} for e in events]}


@router.post('/queue-tickets/{tid}/{action}')
async def transition(tid: UUID, action: str, data: TicketAction, user=Depends(current_user), db=Depends(get_db)):
    return ticket_view(await service.transition(db, user, tid, action, data))
