import asyncio
import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from app.config import session_scope
from app.models import Account, Acceptance, Reversal


class ReversalInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    external_request_id: UUID
    original_request_id: UUID
    scenario: Literal['NORMAL','SUCCESS_TIMEOUT','DECLINED'] = 'NORMAL'


def view(row):
    return {'external_request_id': str(row.external_request_id), 'external_reversal_id': str(row.external_reversal_id),
        'original_request_id': str(row.original_request_id), 'status': row.status, 'reason': row.reason, 'simulated': True}


async def reverse(data):
    ih = hashlib.sha256(json.dumps(data.model_dump(mode='json'), sort_keys=True).encode()).hexdigest()
    async with session_scope() as db:
        source = await db.scalar(select(Acceptance).where(Acceptance.external_request_id == data.original_request_id).with_for_update())
        if source is None: raise HTTPException(404, 'Original request missing')
        row = await db.get(Reversal, data.external_request_id)
        inserted = row is None
        if row:
            if row.payload_hash != ih: raise HTTPException(409, 'Reversal key conflict')
        else:
            if await db.scalar(select(Reversal).where(Reversal.original_request_id == source.external_request_id)):
                raise HTTPException(409, 'Original request already has a reversal')
            account = await db.scalar(select(Account).where(Account.id == source.account_id).with_for_update())
            reason = None
            if source.status != 'SUCCESS': reason = '原受理尚未成功，不能冲正'
            elif source.previous_state is None: reason = '旧受理缺少变更前事实，只能人工核查，未自动修改账号'
            elif source.applied_source_time != account.source_time: reason = '账号在原受理后已发生变化，需人工核查'
            elif data.scenario == 'DECLINED': reason = '模拟冲正被拒绝，原账号事实保留'
            if reason is None:
                account.facts = source.previous_state['facts']
                fee = source.previous_state['monthly_fee']
                account.monthly_fee = Decimal(fee) if fee is not None else None
                account.source_time = datetime.now(UTC)
            row = Reversal(external_request_id=data.external_request_id, original_request_id=data.original_request_id,
                payload_hash=ih, status='FAILED' if reason else 'SUCCESS', reason=reason, created_at=datetime.now(UTC))
            db.add(row)
        await db.commit(); result = view(row)
    if inserted and data.scenario == 'SUCCESS_TIMEOUT': await asyncio.sleep(4)
    return result


async def lookup(rid):
    async with session_scope() as db:
        row = await db.get(Reversal, rid)
        return view(row) if row else {'status':'NOT_FOUND','simulated':True}
