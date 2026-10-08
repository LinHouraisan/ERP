import asyncio
import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from app.config import session_scope
from app.models import Payment, Refund


class RefundInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    external_request_id: UUID
    external_payment_id: UUID
    amount: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
    scenario: Literal['NORMAL', 'SUCCESS_TIMEOUT', 'DECLINED'] = 'NORMAL'


def view(row):
    return {'external_request_id': str(row.external_request_id), 'external_refund_id': str(row.external_refund_id),
        'external_payment_id': str(row.external_payment_id), 'amount': str(row.amount), 'status': row.status, 'simulated': True}


async def refund(data):
    ih = hashlib.sha256(json.dumps(data.model_dump(mode='json'), sort_keys=True).encode()).hexdigest()
    async with session_scope() as db:
        payment = await db.scalar(select(Payment).where(Payment.external_payment_id == data.external_payment_id).with_for_update())
        if not payment or payment.status != 'SUCCESS': raise HTTPException(409, 'Successful payment required')
        row = await db.get(Refund, data.external_request_id)
        inserted = row is None
        if row:
            if row.payload_hash != ih: raise HTTPException(409, 'Refund key conflict')
        else:
            prior = await db.scalar(select(func.coalesce(func.sum(Refund.amount), 0)).where(Refund.external_payment_id == payment.external_payment_id, Refund.status == 'SUCCESS'))
            if prior + data.amount > payment.amount: raise HTTPException(409, 'Refund exceeds payment')
            row = Refund(external_request_id=data.external_request_id, external_payment_id=data.external_payment_id, amount=data.amount,
                payload_hash=ih, status='FAILED' if data.scenario == 'DECLINED' else 'SUCCESS', created_at=datetime.now(UTC))
            db.add(row)
        await db.commit(); result = view(row)
    if inserted and data.scenario == 'SUCCESS_TIMEOUT': await asyncio.sleep(4)
    return result


async def lookup(rid):
    async with session_scope() as db:
        row = await db.get(Refund, rid)
        return view(row) if row else {'status': 'NOT_FOUND', 'simulated': True}
