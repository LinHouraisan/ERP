import asyncio
import calendar
import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.config import session_scope
from app.models import Account, Acceptance


async def account_query(data):
    async with session_scope() as db:
        account = await db.scalar(select(Account).where(Account.number == data.number, Account.account_type == data.account_type))
        if account is None:
            return {'status': 'NOT_FOUND'}
        result = {'status': 'FOUND', 'source': 'BOSS_MOCK', 'source_time': account.source_time.isoformat(),
                  'payload': {**account.facts, 'schema_version': 1, 'external_id': str(account.id),
                  'customer_external_id': str(account.customer_id), 'number': account.number,
                  'account_type': account.account_type, 'monthly_fee': str(account.monthly_fee) if account.monthly_fee is not None else None}}
        scenario = account.scenario
    if scenario == 'QUERY_TIMEOUT':
        await asyncio.sleep(4)
    return result


def acceptance_view(row):
    return {'external_request_id': str(row.external_request_id), 'external_order_id': str(row.external_order_id), 'status': row.status, 'reason': row.reason}


def apply_success(account, order):
    payload = order.payload
    order.previous_state = {'facts': account.facts, 'monthly_fee': str(account.monthly_fee) if account.monthly_fee is not None else None}
    today = datetime.now(ZoneInfo('Asia/Shanghai')).date()
    months = payload['contract_months']
    y, m = divmod(today.year*12 + today.month-1 + months, 12)
    end = date(y, m+1, min(today.day, calendar.monthrange(y, m+1)[1])) - timedelta(days=1) if months else None
    account.facts = {**account.facts, 'product_id': payload['product_id'], 'package_name': payload['product_name'], 'contract_end': end.isoformat() if end else None, 'broadband': payload.get('broadband', account.facts.get('broadband'))}
    account.monthly_fee, account.source_time, order.status = order.monthly_fee, datetime.now(UTC), 'SUCCESS'
    order.applied_source_time = account.source_time


async def accept(data):
    payload = data.model_dump(mode='json', exclude_unset=True)
    ih = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    async with session_scope() as db:
        if not await db.get(Account, data.account_id): raise HTTPException(404, 'Account not found')
        inserted = await db.scalar(insert(Acceptance).values(external_request_id=data.external_request_id,
            account_id=data.account_id, payload_hash=ih, payload=payload, status='PROCESSING', monthly_fee=data.monthly_fee,
            one_time_fee=data.one_time_fee, created_at=datetime.now(UTC)).on_conflict_do_nothing().returning(Acceptance.external_request_id))
        order = await db.scalar(select(Acceptance).where(Acceptance.external_request_id == data.external_request_id).with_for_update())
        if order.payload_hash != ih: raise HTTPException(409, 'Request key conflicts with existing content')
        if not inserted:
            return acceptance_view(order)
        account = await db.scalar(select(Account).where(Account.id == data.account_id).with_for_update())
        scenario = account.scenario
        contract = account.facts.get('contract_end')
        if scenario == 'REJECT' or account.source_time != data.expected_source_time or account.facts.get('restrictions') or (contract and date.fromisoformat(contract) >= datetime.now(ZoneInfo('Asia/Shanghai')).date()):
            order.status, order.reason = 'FAILED', '模拟业务拒绝或账号事实已变更'
        elif scenario != 'PROCESSING':
            apply_success(account, order)
        await db.commit()
        result = acceptance_view(order)
    if scenario == 'SUCCESS_TIMEOUT': await asyncio.sleep(4)
    return result


async def lookup(request_id):
    async with session_scope() as db:
        order = await db.get(Acceptance, request_id)
        if order is None: return {'status': 'NOT_FOUND'}
        account = await db.get(Account, order.account_id)
        if account.scenario == 'LOOKUP_FAILURE': raise HTTPException(503, 'Temporary lookup failure')
        return acceptance_view(order)


async def complete(request_id):
    async with session_scope() as db:
        order = await db.scalar(select(Acceptance).where(Acceptance.external_request_id == request_id).with_for_update())
        if not order: raise HTTPException(404, 'Request not found')
        if order.status == 'PROCESSING':
            account = await db.scalar(select(Account).where(Account.id == order.account_id).with_for_update())
            if account.source_time.isoformat() != datetime.fromisoformat(order.payload['expected_source_time'].replace('Z','+00:00')).isoformat():
                order.status, order.reason = 'FAILED', '账号资料已变更'
            else: apply_success(account, order)
            await db.commit()
        return acceptance_view(order)
