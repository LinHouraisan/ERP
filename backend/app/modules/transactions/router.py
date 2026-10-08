from decimal import Decimal
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from app.core.db import get_db
from app.core.digests import content_hash
from app.core.errors import DomainError
from app.core.security import current_user, owned, require_role
from app.modules.accounts.models import Customer, AccountSnapshot
from app.modules.acceptances.models import Acceptance
from app.modules.recommendations.models import Recommendation
from app.modules.sales.models import SalesOrder, Payment
from app.modules.installations.models import Installation
from app.modules.aftersales.models import AfterSale, Reversal
from app.modules.transactions.models import Transaction, TransactionLink
from app.modules.inventory.schemas import RequestKey
from app.modules.aftersales.schemas import Note

router = APIRouter(prefix='/api/v1/transactions', tags=['组合交易'])


class Links(BaseModel):
    model_config = ConfigDict(extra='forbid')
    order_ids: list[UUID] = Field(default_factory=list, max_length=50)
    acceptance_ids: list[UUID] = Field(default_factory=list, max_length=50)
    installation_ids: list[UUID] = Field(default_factory=list, max_length=50)


class Create(Links):
    request_key: RequestKey
    customer_id: UUID
    title: str = Field(min_length=1, max_length=120)
    required: list[Literal['SALE','TELECOM','INSTALLATION']] = Field(min_length=1, max_length=3)


class Resolve(Note):
    link_id: UUID
    replacement_link_id: UUID | None = None


async def add_links(db, user, row, data):
    customer = await owned(db, Customer, row.customer_id, user)
    for field, ids, model in [('order_id', data.order_ids, SalesOrder), ('acceptance_id', data.acceptance_ids, Acceptance), ('installation_id', data.installation_ids, Installation)]:
        for rid in sorted(set(ids), key=str):
            source = await owned(db, model, rid, user, lock=True)
            prior = await db.scalar(select(TransactionLink).where(getattr(TransactionLink, field) == rid))
            if prior:
                if prior.transaction_id != row.id: raise DomainError('SOURCE_USED', '子单已属于另一笔组合交易')
                continue
            if model == Acceptance:
                rec = await owned(db, Recommendation, source.recommendation_id, user)
                snapshot = await owned(db, AccountSnapshot, rec.snapshot_id, user)
                match = str(customer.external_id) == snapshot.payload.get('customer_external_id')
            else: match = source.customer_id == row.customer_id
            if not match: raise DomainError('CUSTOMER_MISMATCH', '子单与组合交易客户不一致')
            if model == Installation:
                condition = TransactionLink.order_id == source.source_order_id if source.source_order_id else TransactionLink.acceptance_id == source.source_acceptance_id
                linked = await db.scalar(select(TransactionLink.id).where(TransactionLink.transaction_id == row.id, condition))
                if linked is None: raise DomainError('SOURCE_REQUIRED', '请先关联此装维工单的销售或通信来源')
            db.add(TransactionLink(store_id=user.store_id, transaction_id=row.id, **{field: rid})); await db.flush()


async def view(db, row):
    links = (await db.scalars(select(TransactionLink).where(TransactionLink.transaction_id == row.id).order_by(TransactionLink.created_at))).all()
    children, completed, adjusted = [], 0, False
    total, received, refunds = Decimal('0.00'), Decimal('0.00'), Decimal('0.00')
    unknown_receipt, unknown_refund = False, False
    for link in links:
        if link.order_id:
            source = await db.get(SalesOrder, link.order_id)
            payment = await db.scalar(select(Payment).where(Payment.order_id == source.id))
            cases = (await db.scalars(select(AfterSale).where(AfterSale.order_id == source.id, AfterSale.status != 'REJECTED'))).all()
            refunds += sum((c.amount for c in cases if c.refund_status == 'SUCCESS'), Decimal('0.00'))
            total += source.total
            if payment and payment.status == 'SUCCESS': received += payment.amount
            unknown_receipt |= bool(payment and payment.status in ('PENDING','UNKNOWN'))
            unknown_refund |= any(c.refund_status in ('PENDING','UNKNOWN') for c in cases)
            adjusted |= any(c.status == 'CLOSED' for c in cases) or source.status == 'CANCELLED'
            attention = any(c.status not in ('CLOSED','REJECTED') for c in cases) or source.status != 'CANCELLED' and payment and payment.status in ('UNKNOWN','FAILED')
            done = source.status == 'CANCELLED' or payment and payment.status == 'SUCCESS' and source.stock_status != 'RESERVED'
            kind, url = 'SALE', f'/sales?id={source.id}'
            state = f'{payment.status if payment else source.status}/{source.stock_status}'
        elif link.acceptance_id:
            source = await db.get(Acceptance, link.acceptance_id)
            attention, done, state = source.status in ('UNKNOWN','FAILED'), source.status in ('SUCCESS','CANCELLED'), source.status
            reversal = await db.scalar(select(Reversal).where(Reversal.acceptance_id == source.id, Reversal.status != 'REJECTED'))
            if reversal:
                attention = reversal.status != 'SUCCESS'
                adjusted |= reversal.status == 'SUCCESS'
                state += '/REVERSAL_'+reversal.status
            kind, url = 'TELECOM', f'/services?id={source.service_id}'
        else:
            source = await db.get(Installation, link.installation_id)
            attention, done, state = source.status == 'BLOCKED', source.status in ('COMPLETED','CANCELLED'), source.status
            adjusted |= source.status == 'CANCELLED'
            kind, url = 'INSTALLATION', f'/installations?id={source.id}'
        if link.resolution_note:
            done, attention, adjusted = True, False, True
        completed += bool(done and not attention)
        children.append({'kind': kind, 'id': source.id, 'link_id':link.id, 'state': state, 'completed': bool(done and not attention), 'attention': bool(attention), 'url': url,
            'resolution_note':link.resolution_note, 'resolved_by':link.resolved_by, 'replacement_link_id':link.replacement_link_id})
    missing = sorted(set(row.required)-{c['kind'] for c in children})
    if any(c['attention'] for c in children): status = 'NEEDS_ATTENTION'
    elif not missing and children and completed == len(children): status = 'COMPLETED_WITH_ADJUSTMENTS' if adjusted else 'COMPLETED'
    else: status = 'PARTIAL' if completed else 'PROCESSING'
    return {'id': row.id, 'title': row.title, 'customer_id': row.customer_id, 'actor_id': row.actor_id, 'required': row.required,
        'status': status, 'children': children, 'remaining': missing, 'original_amount': str(total), 'refunded_amount': str(refunds),
        'received_amount': None if unknown_receipt else str(received),
        'net_amount': None if unknown_receipt or unknown_refund else str(received-refunds), 'created_at': row.created_at}


@router.get('')
async def listing(user=Depends(current_user), db=Depends(get_db)):
    rows = (await db.scalars(select(Transaction).where(Transaction.store_id == user.store_id).order_by(Transaction.created_at.desc()).limit(100))).all()
    return {'items': [await view(db, row) for row in rows]}


@router.get('/sources')
async def sources(customer_id: UUID, user=Depends(current_user), db=Depends(get_db)):
    customer = await owned(db, Customer, customer_id, user)
    orders = (await db.scalars(select(SalesOrder).where(SalesOrder.store_id == user.store_id, SalesOrder.customer_id == customer_id).order_by(SalesOrder.created_at.desc()).limit(100))).all()
    accepted = (await db.scalars(select(Acceptance).join(Recommendation, Recommendation.id == Acceptance.recommendation_id)
        .join(AccountSnapshot, AccountSnapshot.id == Recommendation.snapshot_id).where(Acceptance.store_id == user.store_id,
            AccountSnapshot.payload['customer_external_id'].astext == str(customer.external_id)).order_by(Acceptance.created_at.desc()).limit(100))).all()
    jobs = (await db.scalars(select(Installation).where(Installation.store_id == user.store_id, Installation.customer_id == customer_id).order_by(Installation.created_at.desc()).limit(100))).all()
    return {'orders':[{'id':o.id,'label':f'销售 {str(o.id)[:8]} · {o.total} 元 · {o.status}'} for o in orders],
        'acceptances':[{'id':a.id,'label':f'通信 {str(a.id)[:8]} · {a.status}'} for a in accepted],
        'installations':[{'id':i.id,'label':f'{i.address} · {i.status}'} for i in jobs]}


@router.get('/{tid}')
async def detail(tid: UUID, user=Depends(current_user), db=Depends(get_db)):
    return await view(db, await owned(db, Transaction, tid, user))


@router.post('')
async def create(data: Create, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'STAFF','MANAGER','ADMIN')
    await owned(db, Customer, data.customer_id, user, lock=True)
    ih = content_hash(data.model_dump(mode='json'))
    row = await db.scalar(select(Transaction).where(Transaction.store_id == user.store_id, Transaction.request_key == data.request_key))
    if row:
        if row.input_hash != ih: raise DomainError('KEY_CONFLICT', '组合交易请求号对应不同内容')
    else:
        row = Transaction(store_id=user.store_id, customer_id=data.customer_id, actor_id=user.user_id, title=data.title,
            required=list(dict.fromkeys(data.required)), request_key=data.request_key, input_hash=ih)
        db.add(row); await db.flush(); await add_links(db, user, row, data); await db.commit()
    return await view(db, row)


@router.post('/{tid}/links')
async def link(tid: UUID, data: Links, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'STAFF','MANAGER','ADMIN')
    row = await owned(db, Transaction, tid, user, lock=True)
    await add_links(db, user, row, data); await db.commit(); return await view(db, row)


@router.post('/{tid}/resolve-component')
async def resolve(tid: UUID, data: Resolve, user=Depends(current_user), db=Depends(get_db)):
    require_role(user,'MANAGER','ADMIN')
    row = await owned(db,Transaction,tid,user,lock=True)
    link = await owned(db,TransactionLink,data.link_id,user,lock=True)
    if link.transaction_id != tid: raise DomainError('SOURCE_MISMATCH','子单不属于当前组合')
    if link.resolution_note:
        if link.resolution_note != data.note or link.replacement_link_id != data.replacement_link_id: raise DomainError('IMMUTABLE','已确认的异常处理依据不能覆盖')
        return await view(db,row)
    if link.order_id:
        source = await owned(db,SalesOrder,link.order_id,user,lock=True)
        payment = await db.scalar(select(Payment).where(Payment.order_id == source.id))
        allowed = source.status == 'CANCELLED' and (not payment or payment.status == 'FAILED')
        field = 'order_id'
    elif link.acceptance_id:
        source = await owned(db,Acceptance,link.acceptance_id,user,lock=True)
        reversal = await db.scalar(select(Reversal).where(Reversal.acceptance_id == source.id))
        allowed = source.status in ('FAILED','CANCELLED') or source.status == 'SUCCESS' and reversal and (reversal.status == 'SUCCESS' or reversal.status == 'FAILED' and reversal.resolution)
        field = 'acceptance_id'
    else:
        source = await owned(db,Installation,link.installation_id,user,lock=True)
        allowed,field = source.status == 'CANCELLED','installation_id'
    if not allowed: raise DomainError('UNRESOLVED_COMPONENT','须先在原单核实失败、取消或冲正结果；未知结果和未交付项目不能人工标为完成')
    if data.replacement_link_id:
        replacement = await owned(db,TransactionLink,data.replacement_link_id,user)
        if replacement.transaction_id != tid or replacement.id == link.id or getattr(replacement,field) is None or replacement.resolution_note:
            raise DomainError('REPLACEMENT_MISMATCH','替代子单须属于同一组合、同类业务且仍然有效')
    link.resolution_note,link.resolved_by,link.replacement_link_id = data.note,user.user_id,data.replacement_link_id
    await db.commit(); return await view(db,row)
