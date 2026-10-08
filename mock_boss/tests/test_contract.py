import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4
import httpx
from sqlalchemy import select, func
from app.main import app
from app.config import Settings, session_scope
from app.models import Account


async def new_payload(scenario='NORMAL'):
    async with session_scope() as db:
        account=Account(customer_id=uuid4(),number='199'+str(uuid4().int)[-8:],monthly_fee=Decimal('129.00'),facts={'schema_version':1,'simulated':True,'contract_end':None,'restrictions':[]},scenario=scenario,source_time=datetime.now(UTC))
        db.add(account); await db.commit()
        return {'external_request_id':str(uuid4()),'account_id':str(account.id),'policy_version_id':str(uuid4()),'product_id':str(uuid4()),'product_name':'模拟融合89','monthly_fee':'89.00','one_time_fee':'0.00','contract_months':12,'broadband':False,'expected_source_time':account.source_time.isoformat()}


def client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',headers={'Authorization':'Bearer '+Settings().boss_token.get_secret_value()})


async def test_same_key_same_payload_one_order_and_different_payload_conflict():
    payload=await new_payload()
    async with client() as c:
        first=await c.post('/mock/v1/acceptances',json=payload)
        assert first.status_code==200, first.text
        duplicate=await c.post('/mock/v1/acceptances',json=payload)
        assert duplicate.json()['external_order_id']==first.json()['external_order_id']
        conflict=await c.post('/mock/v1/acceptances',json={**payload,'monthly_fee':'99.00'})
        assert conflict.status_code==409
    from app.models import Acceptance
    async with session_scope() as db:
        assert await db.scalar(select(func.count()).select_from(Acceptance).where(Acceptance.external_request_id==payload['external_request_id']))==1
        assert (await db.get(Account,payload['account_id'])).monthly_fee==Decimal('89.00')
        assert (await db.get(Account,payload['account_id'])).facts['broadband'] is False


async def test_timeout_after_commit_still_queryable():
    payload=await new_payload('SUCCESS_TIMEOUT')
    async with client() as c:
        try:
            await asyncio.wait_for(c.post('/mock/v1/acceptances',json=payload),timeout=0.3)
            assert False, 'Expected simulated timeout after commit'
        except TimeoutError: pass
        result=await c.get('/mock/v1/acceptances/by-request/'+payload['external_request_id'])
        assert result.status_code==200, result.text
        assert result.json()['status']=='SUCCESS'
