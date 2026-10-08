import asyncio
import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo
from typing import Annotated, Literal
from uuid import UUID
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.config import session_scope
from app.models import Payment, Acceptance


class PaymentInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    external_request_id: UUID
    order_id: UUID
    amount: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
    method: Literal['CASH', 'CARD', 'WECHAT', 'ALIPAY']
    scenario: Literal['NORMAL', 'SUCCESS_TIMEOUT', 'DECLINED'] = 'NORMAL'


def view(row):
    return {'external_request_id': str(row.external_request_id), 'external_payment_id': str(row.external_payment_id),
        'order_id': str(row.order_id), 'amount': str(row.amount), 'method': row.method, 'status': row.status, 'simulated': True}


async def pay(data):
    ih = hashlib.sha256(json.dumps(data.model_dump(mode='json'), sort_keys=True).encode()).hexdigest()
    async with session_scope() as db:
        inserted = await db.scalar(insert(Payment).values(external_request_id=data.external_request_id, order_id=data.order_id,
            amount=data.amount, method=data.method, payload_hash=ih, status='FAILED' if data.scenario == 'DECLINED' else 'SUCCESS', created_at=datetime.now(UTC))
            .on_conflict_do_nothing().returning(Payment.external_request_id))
        row = await db.get(Payment, data.external_request_id)
        if row is None or row.payload_hash != ih: raise HTTPException(409, 'Payment key conflicts with existing content')
        await db.commit(); result = view(row)
    if inserted and data.scenario == 'SUCCESS_TIMEOUT': await asyncio.sleep(4)
    return result


async def lookup(rid):
    async with session_scope() as db:
        row = await db.get(Payment, rid)
        return view(row) if row else {'status': 'NOT_FOUND', 'simulated': True}


async def bill(period):
    year, month = map(int, period.split('-'))
    if not 1 <= year < 9999 or not 1 <= month <= 12: raise HTTPException(422, 'Invalid period')
    start = datetime(year, month, 1, tzinfo=ZoneInfo('Asia/Shanghai'))
    end = datetime(year+int(month == 12), 1 if month == 12 else month+1, 1, tzinfo=ZoneInfo('Asia/Shanghai'))
    async with session_scope() as db:
        payments = (await db.scalars(select(Payment).where(Payment.status == 'SUCCESS', Payment.created_at >= start, Payment.created_at < end))).all()
        acceptances = (await db.scalars(select(Acceptance).where(Acceptance.status == 'SUCCESS', Acceptance.created_at >= start, Acceptance.created_at < end))).all()
        rows = [{'business_no': str(p.external_payment_id), 'amount': str((p.amount*Decimal('0.10')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
            'received_amount': str((p.amount*Decimal('0.10')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))} for p in payments]
        rows.extend({'business_no': str(a.external_order_id), 'amount': '40.00', 'received_amount': '40.00'} for a in acceptances)
        return {'period': period, 'simulated': True, 'source': 'BOSS_MOCK_BILL', 'rows': rows,
            'definition': '模拟固定账单规则：成功支付总额的 10%，成功通信办理 40 元；可能与门店收益规则产生差异'}
