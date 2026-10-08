import hmac
from fastapi import FastAPI, Request, Depends, HTTPException, Path as PathParam
from typing import Annotated
from sqlalchemy import text
from app.config import Settings, session_scope
from app.schemas import AccountQuery
from app.service import account_query
from app import service
from app.schemas import AcceptanceInput, ScenarioInput
from app.models import Account
from sqlalchemy import select
from uuid import UUID
from pathlib import Path
from alembic.config import Config
from alembic.script import ScriptDirectory
from app import payments

app = FastAPI(title='BOSS 模拟服务')


@app.get('/health/live')
async def live():
    return {'status': 'alive', 'simulated': True}


async def internal_auth(request: Request):
    token = Settings().boss_token.get_secret_value()
    if not token or not hmac.compare_digest(request.headers.get('authorization', ''), 'Bearer '+token):
        raise HTTPException(401, 'Internal token required')


@app.get('/health/ready')
async def ready():
    try:
        async with session_scope() as db:
            version=await db.scalar(text('select version_num from boss.alembic_version'))
        cfg=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))
        if version!=ScriptDirectory.from_config(cfg).get_current_head(): raise ValueError('Migration required')
    except Exception:
        raise HTTPException(503, 'Database or migration unavailable') from None
    return {'status': 'ready', 'simulated': True}


@app.post('/mock/v1/account-query', dependencies=[Depends(internal_auth)])
async def query_account(data: AccountQuery):
    return await account_query(data)


@app.post('/mock/v1/acceptances', dependencies=[Depends(internal_auth)])
async def accept(data: AcceptanceInput):
    return await service.accept(data)


@app.get('/mock/v1/acceptances/by-request/{rid}', dependencies=[Depends(internal_auth)])
async def lookup(rid: UUID):
    return await service.lookup(rid)


@app.post('/mock/v1/scenarios/accounts/{number}', dependencies=[Depends(internal_auth)])
async def scenario(number: str, data: ScenarioInput):
    if Settings().app_env not in ('test', 'demo'): raise HTTPException(403, 'Scenario controls require demo/test mode')
    async with session_scope() as db:
        row = await db.scalar(select(Account).where(Account.number == number).with_for_update())
        if row is None: raise HTTPException(404, 'Account not found')
        row.scenario = data.scenario
        await db.commit()
        return {'scenario': row.scenario}


@app.post('/mock/v1/acceptances/by-request/{rid}/complete', dependencies=[Depends(internal_auth)])
async def complete(rid: UUID):
    if Settings().app_env not in ('test', 'demo'): raise HTTPException(403, 'Demo/test mode required')
    return await service.complete(rid)


@app.post('/mock/v1/payments', dependencies=[Depends(internal_auth)])
async def pay(data: payments.PaymentInput):
    return await payments.pay(data)


@app.get('/mock/v1/payments/by-request/{rid}', dependencies=[Depends(internal_auth)])
async def payment_lookup(rid: UUID):
    return await payments.lookup(rid)


@app.get('/mock/v1/bills/{period}', dependencies=[Depends(internal_auth)])
async def bill(period: Annotated[str, PathParam(pattern=r'^\d{4}-(0[1-9]|1[0-2])$')]):
    return await payments.bill(period)


from app import refunds


@app.post('/mock/v1/refunds', dependencies=[Depends(internal_auth)])
async def refund(data: refunds.RefundInput):
    return await refunds.refund(data)


@app.get('/mock/v1/refunds/by-request/{rid}', dependencies=[Depends(internal_auth)])
async def refund_lookup(rid: UUID):
    return await refunds.lookup(rid)


from app import reversals


@app.post('/mock/v1/reversals', dependencies=[Depends(internal_auth)])
async def reverse(data: reversals.ReversalInput):
    return await reversals.reverse(data)


@app.get('/mock/v1/reversals/by-request/{rid}', dependencies=[Depends(internal_auth)])
async def reversal_lookup(rid: UUID):
    return await reversals.lookup(rid)
