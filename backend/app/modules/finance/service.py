from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo
from sqlalchemy import select, func
from app.core.digests import content_hash
from app.core.errors import DomainError
from app.core.security import owned, require_role
from app.modules.auth.models import Store
from app.modules.sales.models import SalesOrder, SalesLine, Payment
from app.modules.acceptances.models import Acceptance
from app.modules.services.models import ServiceSession
from app.modules.installations.models import Installation
from app.modules.finance.models import EarningRule, Earning, BillBatch, BillLine, EarningAdjustment, SettlementLine
from app.modules.finance.schemas import rule_view


async def new_rule(db, user, data):
    require_role(user, 'ADMIN')
    await db.scalar(select(Store).where(Store.id == user.store_id).with_for_update())
    version = (await db.scalar(select(func.max(EarningRule.version)).where(EarningRule.store_id == user.store_id, EarningRule.business_type == data.business_type)) or 0)+1
    row = EarningRule(store_id=user.store_id, version=version, **data.model_dump()); db.add(row); await db.commit(); return row


async def accrual(db, user, data):
    require_role(user, 'FINANCE', 'MANAGER', 'ADMIN')
    model, field = {'SALE': (SalesOrder, 'order_id'), 'TELECOM': (Acceptance, 'acceptance_id'), 'INSTALLATION': (Installation, 'installation_id')}[data.source_type]
    source = await owned(db, model, data.source_id, user, lock=True)
    existing = await db.scalar(select(Earning).where(getattr(Earning, field) == source.id))
    if existing: return existing
    base = Decimal('0.00')
    if data.source_type == 'SALE':
        payment = await db.scalar(select(Payment).where(Payment.order_id == source.id))
        if payment is None or payment.status != 'SUCCESS' or source.stock_status == 'RESERVED': raise DomainError('SOURCE_INCOMPLETE', '订单须成功收款并完成实物出库')
        lines = (await db.scalars(select(SalesLine).where(SalesLine.order_id == source.id))).all()
        base = sum((l.amount for l in lines if l.snapshot['receipt_category'] == 'OPERATING'), Decimal('0.00'))
        owner, business_no, at = source.actor_id, str(payment.external_payment_id), source.shipped_at or payment.settled_at
    elif data.source_type == 'TELECOM':
        if source.status != 'SUCCESS': raise DomainError('SOURCE_INCOMPLETE', '仅成功通信受理可预估收益')
        session = await owned(db, ServiceSession, source.service_id, user)
        owner, business_no, at = session.staff_id, str(source.external_order_id), source.updated_at
    else:
        if source.status != 'COMPLETED': raise DomainError('SOURCE_INCOMPLETE', '安装须完成客户验收')
        owner, business_no, at = source.installer_id, str(source.id), source.completed_at
    day = at.astimezone(ZoneInfo('Asia/Shanghai')).date()
    rule = await db.scalar(select(EarningRule).where(EarningRule.store_id == user.store_id, EarningRule.business_type == data.source_type,
        EarningRule.status == 'PUBLISHED', EarningRule.valid_from <= day, EarningRule.valid_to >= day).order_by(EarningRule.version.desc()).limit(1))
    if rule is None: raise DomainError('RULE_REQUIRED', '业务完成日缺少已发布收益规则')
    expected = (rule.fixed_amount+base*rule.rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if expected > Decimal('9999999999.99'): raise DomainError('AMOUNT_LIMIT', '收益超出单据金额上限')
    commission = (expected*rule.employee_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    row = Earning(store_id=user.store_id, rule_id=rule.id, owner_id=owner, **{field: source.id}, business_no=business_no,
        period=day.strftime('%Y-%m'), expected_amount=expected, commission_amount=commission,
        snapshot={'rule': rule_view(rule) | {'id': str(rule.id)}, 'source_type': data.source_type, 'source_id': str(source.id),
            'completed_at': at.isoformat(), 'base_amount': str(base), 'definition': '固定收益 + 经营类实收 × 比例；四舍五入到分；并非实测经营收益'})
    db.add(row); await db.flush()
    from app.modules.aftersales.models import AfterSale, Reversal
    from app.modules.finance.adjustments import refund_adjustment, reversal_adjustment
    if row.order_id:
        for case in (await db.scalars(select(AfterSale).where(AfterSale.order_id == row.order_id, AfterSale.refund_status == 'SUCCESS').order_by(AfterSale.refunded_at))).all():
            await refund_adjustment(db, user, case); await db.flush()
    if row.acceptance_id:
        reversal = await db.scalar(select(Reversal).where(Reversal.acceptance_id == row.acceptance_id, Reversal.status == 'SUCCESS'))
        if reversal: await reversal_adjustment(db, user, reversal)
    await db.commit(); return row


async def earning_view(db, row, settlement_period=None):
    from app.core.config import business_date
    q = select(BillLine).where(BillLine.store_id == row.store_id, BillLine.business_no == row.business_no, BillLine.earning_period == row.period)
    if settlement_period: q = q.where(BillLine.period <= settlement_period)
    bills = (await db.scalars(q.order_by(BillLine.period, BillLine.created_at))).all()
    adjustments = (await db.scalars(select(EarningAdjustment).where(EarningAdjustment.earning_id == row.id).order_by(EarningAdjustment.created_at))).all()
    expected = row.expected_amount+sum((a.expected_delta for a in adjustments), Decimal('0.00'))
    commission = row.commission_amount+sum((a.commission_delta for a in adjustments), Decimal('0.00'))
    due = sum((b.amount for b in bills), Decimal('0.00'))
    known = sum((b.received_amount for b in bills if b.received_amount is not None), Decimal('0.00'))
    unknown = sum(b.received_amount is None for b in bills)
    actual = known if bills and not unknown else None
    match = ('MISSING_BILL' if not bills else 'MATCHED' if due == expected else
        'TIMING_DIFFERENCE' if not any(b.is_final for b in bills) and 0 <= due < expected else 'AMOUNT_MISMATCH')
    eligible = Decimal('0.00')
    if row.snapshot['rule']['settlement_condition'] == 'SOURCE_COMPLETE': eligible = commission
    elif match in ('MATCHED','TIMING_DIFFERENCE') and expected > 0:
        eligible = (commission*min(max(known,Decimal('0.00')),expected)/expected).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    settled = await db.scalar(select(func.coalesce(func.sum(SettlementLine.amount),0)).where(SettlementLine.earning_id == row.id))
    available = min(commission-settled,Decimal('0.00'))+max(eligible-settled,Decimal('0.00'))
    current_period = settlement_period or business_date().strftime('%Y-%m')
    current = [b for b in bills if b.period == current_period]
    return {'id': row.id, 'owner_id': row.owner_id, 'business_no': row.business_no, 'period': row.period,
        'source_type': row.snapshot['source_type'], 'source_id': row.snapshot['source_id'], 'expected_amount': str(row.expected_amount),
        'current_due': str(sum((b.amount for b in current),Decimal('0.00'))) if current else None, 'due_period':current_period,
        'actual_received': str(actual) if actual is not None else None, 'known_received':str(known) if bills else None, 'unknown_receipts':unknown,
        'commission_amount': str(row.commission_amount), 'adjusted_expected':str(expected), 'adjusted_commission':str(commission),
        'settled_commission':str(settled), 'remaining_commission':str(commission-settled), 'available_commission':str(available),
        'settleable': available > 0, 'match_status': match, 'bill_line_id': bills[0].id if bills else None, 'snapshot': row.snapshot,
        'bill_periods':[{'id':b.id,'period':b.period,'amount':str(b.amount),'received_amount':str(b.received_amount) if b.received_amount is not None else None,'is_final':b.is_final} for b in bills],
        'adjustments':[{'id':a.id,'period':a.period,'expected_delta':str(a.expected_delta),'commission_delta':str(a.commission_delta),
            'reason':a.reason,'after_sale_id':a.after_sale_id,'reversal_id':a.reversal_id,'case_id':a.case_id,'snapshot':a.snapshot} for a in adjustments]}


async def import_bill(db, user, data):
    require_role(user, 'FINANCE', 'MANAGER', 'ADMIN')
    # ponytail: serializes one demo store's bill imports; use period locks when measured volume warrants it.
    await db.scalar(select(Store).where(Store.id == user.store_id).with_for_update())
    ih = content_hash(data.model_dump(mode='json'))
    existing = await db.scalar(select(BillBatch).where(BillBatch.store_id == user.store_id, BillBatch.request_key == data.request_key))
    if existing:
        if existing.input_hash != ih: raise DomainError('KEY_CONFLICT', '同一账单请求号对应不同内容')
        return existing
    existing_lines = (await db.scalars(select(BillLine).where(BillLine.store_id == user.store_id, BillLine.period == data.period,
        BillLine.business_no.in_([x.business_no for x in data.rows])))).all()
    keys = {(b.business_no,b.line_key) for b in existing_lines}
    if any((x.business_no,x.line_key) in keys for x in data.rows): raise DomainError('BILL_DUPLICATE', '账期内已有相同业务号和账单行号，请查看原批次')
    batch = BillBatch(store_id=user.store_id, actor_id=user.user_id, request_key=data.request_key, input_hash=ih, period=data.period, source=data.source)
    db.add(batch); await db.flush()
    for index, item in enumerate(data.rows, 1):
        values = item.model_dump(); values['earning_period'] = item.earning_period or data.period
        db.add(BillLine(store_id=user.store_id, batch_id=batch.id, period=data.period, **values,
            original={'row': index, 'period': data.period, **item.model_dump(mode='json'), 'simulated': True}))
    await db.commit(); return batch


async def bill_view(db, row):
    lines = (await db.scalars(select(BillLine).where(BillLine.batch_id == row.id).order_by(BillLine.created_at, BillLine.id))).all()
    items = []
    for line in lines:
        earning = await db.scalar(select(Earning).where(Earning.store_id == row.store_id, Earning.business_no == line.business_no, Earning.period == line.earning_period))
        status = 'MISSING_INTERNAL' if earning is None else (await earning_view(db,earning))['match_status']
        items.append({'id': line.id, 'business_no': line.business_no, 'amount': str(line.amount), 'received_amount': str(line.received_amount) if line.received_amount is not None else None,
            'status': status, 'earning_id': earning.id if earning else None, 'earning_period':line.earning_period, 'line_key':line.line_key, 'is_final':line.is_final, 'original': line.original})
    return {'id': row.id, 'source': row.source, 'period': row.period, 'created_at': row.created_at, 'items': items, 'simulated': True}
