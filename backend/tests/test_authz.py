import httpx
from uuid import uuid4
import pytest

from app.main import app


async def test_login_logout_csrf_and_roles():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1:5173') as c:
        assert (await c.get('/api/v1/auth/me')).status_code == 401
        from app.modules.auth.models import Store, User
        from app.modules.auth.service import hash_password
        from app.core.db import session_scope
        username = str(uuid4())
        async with session_scope() as db:
            store = Store(name='权限测试门店')
            db.add(store)
            await db.flush()
            db.add(User(store_id=store.id, username=username, password_hash=hash_password('test-password-123'), role='STAFF'))
            await db.commit()
        login = await c.post('/api/v1/auth/login', json={'username': username, 'password': 'test-password-123'}, headers={'Origin': 'http://127.0.0.1:5173'})
        assert login.status_code == 200, login.text
        assert 'HttpOnly' in login.headers['set-cookie']
        assert (await c.get('/api/v1/auth/me')).json()['role'] == 'STAFF'
        assert (await c.get('/api/v1/service-metrics')).status_code == 403
        assert (await c.post('/api/v1/auth/logout', json={})).status_code == 403
        cookie = c.cookies.get('erp_session')
        headers = {'Origin': 'http://127.0.0.1:5173', 'X-CSRF-Token': login.json()['csrf_token']}
        assert (await c.post(f'/api/v1/policy-versions/{uuid4()}/publish', json={}, headers=headers)).status_code == 403
        assert (await c.post(f'/api/v1/improvement-tasks/{uuid4()}/transition', json={'status':'REJECTED','reason':'无管理权限审核'}, headers=headers)).status_code == 403
        assert (await c.post('/api/v1/auth/logout', json={}, headers=headers)).status_code == 200
        c.cookies.set('erp_session', cookie)
        assert (await c.get('/api/v1/auth/me')).status_code == 401


async def test_cross_store_resource_and_staff_action_rejected():
    from app.core.security import CurrentUser, require_role, owned
    from app.core.errors import DomainError
    from app.modules.auth.models import Store, User
    from app.core.db import session_scope
    user = CurrentUser(user_id=uuid4(), store_id=uuid4(), role='STAFF', username='staff', csrf_token='')
    with pytest.raises(DomainError) as error:
        require_role(user, 'ADMIN', 'MANAGER')
    assert error.value.status == 403
    async with session_scope() as db:
        with pytest.raises(DomainError) as error:
            await owned(db, User, uuid4(), user)
        assert error.value.status == 404


async def test_real_cross_store_service_is_hidden(client):
    from app.core.db import session_scope
    from app.modules.auth.models import Store, User
    from app.modules.services.models import ServiceSession
    async with session_scope() as db:
        store=Store(name='隔离门店');db.add(store);await db.flush()
        user=User(store_id=store.id,username=str(uuid4()),password_hash='unused',role='STAFF');db.add(user);await db.flush()
        service=ServiceSession(store_id=store.id,staff_id=user.id,category='PLAN');db.add(service);await db.commit()
        sid=service.id
    response=await client.get(f'/api/v1/service-sessions/{sid}')
    assert response.status_code==404 and '隔离门店' not in response.text
    assert (await client.post(f'/api/v1/service-sessions/{sid}/finish',json={})).status_code==404
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:5173') as anonymous:
        assert (await anonymous.get(f'/api/v1/service-sessions/{sid}')).status_code==401
