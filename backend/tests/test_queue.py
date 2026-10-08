import asyncio
from uuid import uuid4


async def test_same_window_call_is_idempotent_and_two_windows_do_not_share_ticket():
    from app.core.db import session_scope
    from app.core.security import CurrentUser
    from app.modules.auth.models import Store, User
    from app.modules.queue.models import Window
    from app.modules.queue.service import take_ticket, call_next
    async with session_scope() as db:
        store = Store(name='并发队列测试'); db.add(store); await db.flush()
        user = User(store_id=store.id, username=str(uuid4()), password_hash='unused', role='STAFF'); db.add(user)
        windows = [Window(store_id=store.id, name=f'窗口{i}', categories=['PLAN']) for i in range(2)]
        db.add_all(windows); await db.commit()
        actor=CurrentUser(user_id=user.id,store_id=store.id,username=user.username,role='STAFF',csrf_token='')
        for _ in range(3): await take_ticket(db, store.id, 'PLAN')
    async def call(wid):
        async with session_scope() as db: return await call_next(db,actor,wid)
    same=await asyncio.gather(call(windows[0].id),call(windows[0].id))
    assert same[0].id == same[1].id
    different=await asyncio.gather(call(windows[0].id),call(windows[1].id))
    assert different[0].id != different[1].id


async def test_public_board_has_no_customer_data(client):
    r=await client.get('/api/v1/public/queue-board')
    assert r.status_code==200
    for ticket in r.json()['items']:
        assert set(ticket)=={'ticket_number','category','window','status','updated_at'}


async def test_missed_requeue_cancel_and_finish_preserve_events(client):
    from app.core.db import session_scope
    from app.core.security import CurrentUser
    from app.modules.queue.models import Window
    from app.modules.queue.service import take_ticket,call_next,transition
    from app.modules.queue.schemas import TicketAction
    actor=CurrentUser.model_validate((await client.get('/api/v1/auth/me')).json())
    async with session_scope() as db:
        window=Window(store_id=actor.store_id,name='检查-'+str(uuid4())[:8],categories=['OTHER']);db.add(window);await db.commit()
        ticket=await take_ticket(db,actor.store_id,'OTHER')
        called=await call_next(db,actor,window.id)
        await transition(db,actor,called.id,'miss',TicketAction(reason='未到场'))
        await transition(db,actor,called.id,'requeue',TicketAction(reason='返回队尾'))
        await transition(db,actor,called.id,'adjust',TicketAction(category='OTHER',reason='核实业务类别'))
        await transition(db,actor,called.id,'cancel',TicketAction(reason='客户取消'))
        await take_ticket(db,actor.store_id,'OTHER')
        next_ticket=await call_next(db,actor,window.id)
        serving=await transition(db,actor,next_ticket.id,'start',TicketAction())
        sid,tid=serving.service_id,serving.id
    assert (await client.post(f'/api/v1/service-sessions/{sid}/finish',json={})).status_code==200
    detail=await client.get(f'/api/v1/queue-tickets/{tid}')
    assert detail.status_code==200,detail.text
    assert detail.json()['status']=='DONE'
    assert detail.json()['events'][-1]['action']=='FINISH'
