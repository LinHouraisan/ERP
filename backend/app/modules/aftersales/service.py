from decimal import Decimal
from uuid import UUID
from sqlalchemy import select
from app.core.db import utcnow
from app.core.digests import content_hash
from app.core.errors import DomainError
from app.core.security import owned, require_role
from app.integrations import boss
from app.modules.aftersales.models import AfterSale, AfterSaleEvent
from app.modules.sales.models import SalesOrder, SalesLine, Payment
from app.modules.inventory.models import StockSerial, StockMovement
from app.modules.inventory.service import locked_stock
from app.modules.installations.models import Installation


def event(db, user, row, action, detail):
    db.add(AfterSaleEvent(store_id=user.store_id, after_sale_id=row.id, actor_id=user.user_id, action=action, detail=detail))


async def view(db, row):
    events = (await db.scalars(select(AfterSaleEvent).where(AfterSaleEvent.after_sale_id == row.id).order_by(AfterSaleEvent.created_at))).all()
    return {**{k: getattr(row, k) for k in ('id','order_id','actor_id','approved_by','kind','reason','status','lines','refund_status',
        'external_request_id','external_refund_id','refunded_at','stock_processed','return_evidence','service_resolution','last_error','created_at')},
        'amount': str(row.amount), 'simulated': True,
        'events': [{'action': e.action, 'actor_id': e.actor_id, 'detail': e.detail, 'at': e.created_at} for e in events]}


async def create(db, user, data):
    require_role(user, 'STAFF', 'MANAGER', 'ADMIN')
    order = await owned(db, SalesOrder, data.order_id, user, lock=True)
    ih = content_hash(data.model_dump(mode='json'))
    old = await db.scalar(select(AfterSale).where(AfterSale.store_id == user.store_id, AfterSale.request_key == data.request_key))
    if old:
        if old.input_hash != ih: raise DomainError('KEY_CONFLICT', '原售后请求号不能更换内容')
        return old
    payment = await db.scalar(select(Payment).where(Payment.order_id == order.id))
    if not payment or payment.status != 'SUCCESS': raise DomainError('PAYMENT_REQUIRED', '请先核明原单成功收款，未知结果不能退款')
    if data.kind == 'RETURN_REFUND' and order.stock_status != 'SHIPPED': raise DomainError('NOT_SHIPPED', '未出库订单请选择取消未交付项目')
    if data.kind == 'CANCEL_UNSHIPPED' and order.stock_status == 'SHIPPED': raise DomainError('ALREADY_SHIPPED', '已出库商品须办理实物退货')
    lines = {x.id: x for x in (await db.scalars(select(SalesLine).where(SalesLine.order_id == order.id))).all()}
    prior = (await db.scalars(select(AfterSale).where(AfterSale.order_id == order.id, AfterSale.status != 'REJECTED'))).all()
    frozen = []
    for item in data.lines:
        line = lines.get(item.line_id)
        if not line: raise DomainError('LINE_MISMATCH', '售后行不属于原订单')
        money, quantity = Decimal('0.00'), 0
        for case in prior:
            for part in case.lines:
                if part['line_id'] != str(line.id): continue
                if case.refund_status != 'FAILED': money += Decimal(part['refund_amount'])
                if case.refund_status != 'FAILED' or case.stock_processed: quantity += part['return_quantity']
        if money + item.refund_amount > line.amount or quantity + item.return_quantity > line.quantity:
            raise DomainError('REFUND_LIMIT', '退款金额或退货数量超过原单剩余可售后额度（含待审批申请）')
        if (data.kind == 'REFUND_ONLY' and item.return_quantity or line.snapshot['kind'] != 'GOODS' and item.return_quantity):
            raise DomainError('RETURN_KIND', '仅退款和非实物行不得增加库存')
        if data.kind != 'REFUND_ONLY' and line.snapshot['kind'] == 'GOODS' and not item.return_quantity:
            raise DomainError('RETURN_QUANTITY', '商品退货或取消交付必须填写数量')
        frozen.append({**item.model_dump(mode='json'), 'product_id': str(line.product_id), 'snapshot': line.snapshot})
    row = AfterSale(store_id=user.store_id, order_id=order.id, actor_id=user.user_id, request_key=data.request_key,
        input_hash=ih, kind=data.kind, reason=data.reason, scenario=data.scenario, lines=frozen,
        amount=sum((x.refund_amount for x in data.lines), Decimal('0.00')))
    db.add(row); await db.flush(); event(db, user, row, 'REQUESTED', {'reason': data.reason})
    await db.commit(); return row


async def review(db, user, aid, data):
    require_role(user, 'MANAGER', 'ADMIN')
    row = await owned(db, AfterSale, aid, user, lock=True)
    target = 'APPROVED' if data.decision == 'APPROVE' else 'REJECTED'
    if row.status == target: return row
    if row.status != 'REQUESTED': raise DomainError('REVIEWED', '申请已处理，不能覆盖原审批')
    row.status, row.approved_by = target, user.user_id
    event(db, user, row, target, {'note': data.note}); await db.commit(); return row


async def receive(db, user, aid, data):
    require_role(user, 'WAREHOUSE', 'MANAGER', 'ADMIN')
    row = await owned(db, AfterSale, aid, user)
    await owned(db, SalesOrder, row.order_id, user, lock=True)
    row = await owned(db, AfterSale, aid, user, lock=True)
    evidence = data.model_dump(mode='json')
    if row.stock_processed:
        if row.return_evidence != evidence: raise DomainError('KEY_CONFLICT', '不能覆盖已经验收的退货证据')
        return row
    if row.status != 'APPROVED' or row.kind != 'RETURN_REFUND': raise DomainError('APPROVAL_REQUIRED', '仅已批准的实物退货可验收入库')
    if row.refund_status == 'FAILED': raise DomainError('REFUND_FAILED', '此退款已核实失败并释放未验收额度，请按后续有效申请验收，不能继续向失败单入库')
    await check_service(db, row)
    returns = {str(x.line_id): x.serials for x in data.lines}
    expected = {x['line_id']: x for x in row.lines if x['return_quantity']}
    if returns.keys() != expected.keys(): raise DomainError('LINE_MISMATCH', '须验收申请中的全部退货行')
    for part in sorted(expected.values(), key=lambda x: x['product_id']):
        serials, quantity, pid = returns[part['line_id']], part['return_quantity'], UUID(part['product_id'])
        if (part['snapshot']['tracking'] == 'SERIAL' and len(serials) != quantity or part['snapshot']['tracking'] != 'SERIAL' and serials):
            raise DomainError('SERIAL_COUNT', '验收序列号数量与退货数量不一致')
        stock = await locked_stock(db, user, pid)
        for serial in serials:
            device = await db.scalar(select(StockSerial).where(StockSerial.store_id == user.store_id, StockSerial.serial == serial).with_for_update())
            if not device or device.product_id != pid or device.order_id != row.order_id or device.status != 'SHIPPED':
                raise DomainError('SERIAL_MISMATCH', '必须退回原订单已出库且尚未退回的设备')
            device.status, device.order_id = 'AVAILABLE', None
        stock.quantity += quantity
        db.add(StockMovement(store_id=user.store_id, product_id=pid, after_sale_id=row.id, actor_id=user.user_id, quantity=quantity, serials=serials))
    row.stock_processed, row.return_evidence = True, evidence
    event(db, user, row, 'RETURN_RECEIVED', evidence); await db.commit(); return row


async def remaining_allocations(db, order, payment):
    cases = (await db.scalars(select(AfterSale).where(AfterSale.order_id == order.id, AfterSale.stock_processed.is_(True)))).all()
    cancelled = {}
    for case in cases:
        evidence = {x['line_id']: x['serials'] for x in case.return_evidence.get('lines', [])}
        parts = case.return_evidence.get('allocations', []) if case.kind == 'CANCEL_UNSHIPPED' else [
            {'product_id':x['product_id'], 'quantity':x['return_quantity'], 'serials':evidence.get(x['line_id'],[])} for x in case.lines if x['return_quantity']]
        for part in parts:
            entry = cancelled.setdefault(part['product_id'], {'quantity': 0, 'serials': []})
            entry['quantity'] += part['quantity']; entry['serials'].extend(part['serials'])
    return [{**a, 'quantity': a['quantity']-cancelled.get(a['product_id'], {}).get('quantity', 0),
        'serials': [s for s in a['serials'] if s not in cancelled.get(a['product_id'], {}).get('serials', [])]}
        for a in payment.allocations if a['quantity'] > cancelled.get(a['product_id'], {}).get('quantity', 0)]


async def release_cancelled(db, user, row, order, payment):
    allocations = {x['product_id']: x for x in await remaining_allocations(db, order, payment)}
    released = []
    for part in sorted(row.lines, key=lambda x: x['product_id']):
        quantity, pid = part['return_quantity'], UUID(part['product_id'])
        if not quantity: continue
        allocation = allocations.get(str(pid))
        if not allocation or allocation['quantity'] < quantity: raise DomainError('ALLOCATION_CHANGED', '剩余交付数量不足，请核查原订单')
        stock = await locked_stock(db, user, pid); stock.reserved -= quantity
        serials = allocation['serials'][:quantity]
        for serial in serials:
            device = await db.scalar(select(StockSerial).where(StockSerial.store_id == user.store_id, StockSerial.serial == serial).with_for_update())
            if device.status != 'RESERVED' or device.order_id != row.order_id: raise DomainError('SERIAL_STATE', '预留设备已变化')
            device.status, device.order_id = 'AVAILABLE', None
        released.append({'product_id': str(pid), 'quantity': quantity, 'serials': serials})
    row.stock_processed, row.return_evidence = True, {'allocations': released, 'note': '退款核实成功，释放尚未交付的原单预留'}
    await db.flush()
    if not await remaining_allocations(db, order, payment): order.stock_status = 'NONE'
    event(db, user, row, 'RESERVATION_RELEASED', row.return_evidence)


async def check_service(db, row):
    job = await db.scalar(select(Installation).where(Installation.source_order_id == row.order_id).with_for_update())
    if job and job.status != 'CANCELLED':
        if job.status != 'COMPLETED': raise DomainError('SERVICE_PENDING', '关联装维尚未结束，请先处理装维取消或完成')
        if not row.service_resolution: raise DomainError('SERVICE_EVIDENCE', '已履约服务不可自动回退，须由店长记录人工处理证据')


async def submit(db, user, aid, *, lookup=False):
    require_role(user, 'FINANCE', 'MANAGER', 'ADMIN')
    row = await owned(db, AfterSale, aid, user)
    await owned(db, SalesOrder, row.order_id, user, lock=True)
    row = await owned(db, AfterSale, aid, user, lock=True)
    if row.refund_status in ('SUCCESS','FAILED'): return row
    if row.status != 'APPROVED': raise DomainError('APPROVAL_REQUIRED', '退款须先由店长审批')
    await check_service(db, row)
    payment = await db.scalar(select(Payment).where(Payment.order_id == row.order_id))
    payload = {'external_request_id': str(row.external_request_id), 'external_payment_id': str(payment.external_payment_id),
        'amount': str(row.amount), 'scenario': row.scenario}
    lookup = lookup or row.refund_status in ('PENDING','UNKNOWN')
    if row.refund_status == 'NONE':
        row.refund_status = 'PENDING'; event(db, user, row, 'REFUND_REQUESTED', payload)
    await db.commit()
    try:
        result = await boss.refund_request('GET', f'/mock/v1/refunds/by-request/{row.external_request_id}') if lookup else {'status':'NOT_FOUND'}
        if result['status'] == 'NOT_FOUND': result = await boss.refund_request('POST', '/mock/v1/refunds', payload)
    except DomainError: result = {'status':'UNKNOWN'}
    order = await owned(db, SalesOrder, row.order_id, user, lock=True)
    row = await owned(db, AfterSale, aid, user, lock=True)
    if row.refund_status in ('SUCCESS','FAILED'): return row
    status = result.get('status')
    if (status not in ('SUCCESS','FAILED') or not result.get('external_refund_id')
        or result.get('external_request_id') != payload['external_request_id'] or result.get('external_payment_id') != payload['external_payment_id']
        or result.get('amount') is None or Decimal(result['amount']) != row.amount): status = 'UNKNOWN'
    row.refund_status = status
    row.last_error = {'UNKNOWN': '退款结果未知，请按原请求号核对', 'FAILED': '模拟退款被拒绝，请保留原记录并人工处理'}.get(status)
    if status in ('SUCCESS','FAILED'):
        row.external_refund_id = UUID(result['external_refund_id'])
    if status == 'SUCCESS':
        row.refunded_at = utcnow()
        if row.kind == 'CANCEL_UNSHIPPED': await release_cancelled(db, user, row, order, payment)
        from app.modules.finance.adjustments import refund_adjustment
        await refund_adjustment(db, user, row)
    event(db, user, row, 'REFUND_'+status, {'external_request_id': str(row.external_request_id)})
    await db.commit(); return row


async def close(db, user, aid, data):
    require_role(user, 'MANAGER', 'ADMIN')
    source = await owned(db, AfterSale, aid, user)
    await owned(db, SalesOrder, source.order_id, user, lock=True)
    row = await owned(db, AfterSale, aid, user, lock=True)
    if row.status == 'CLOSED': return row
    if row.refund_status != 'SUCCESS' or any(x['return_quantity'] for x in row.lines) and not row.stock_processed:
        raise DomainError('UNRESOLVED_AFTERSALE', '须分别核实退款和实物退货或预留释放，未知结果不可关闭')
    await check_service(db, row)
    row.status = 'CLOSED'; event(db, user, row, 'CLOSED', {'note': data.note})
    await db.commit(); return row


async def resolve_failure(db, user, aid, data):
    require_role(user, 'MANAGER', 'ADMIN')
    row = await owned(db, AfterSale, aid, user)
    await owned(db, SalesOrder, row.order_id, user, lock=True)
    row = await owned(db, AfterSale, aid, user, lock=True)
    evidence = data.model_dump(mode='json')
    if row.refund_status != 'FAILED': raise DomainError('REFUND_NOT_FAILED', '仅明确失败的退款可作人工终结；未知结果须按原号核对')
    if row.status == 'CLOSED':
        previous = await db.scalar(select(AfterSaleEvent).where(AfterSaleEvent.after_sale_id == aid, AfterSaleEvent.action == 'FAILED_RESOLVED'))
        if not previous or previous.detail != evidence: raise DomainError('IMMUTABLE', '原失败处理依据不能覆盖')
        return row
    if row.status != 'APPROVED': raise DomainError('APPROVAL_REQUIRED', '仅已批准的失败申请可终结')
    if data.replacement_after_sale_id:
        replacement = await owned(db, AfterSale, data.replacement_after_sale_id, user)
        amounts = lambda r: {x['line_id']:Decimal(x['refund_amount']) for x in r.lines if Decimal(x['refund_amount'])}
        if (replacement.order_id != row.order_id or replacement.status != 'CLOSED' or replacement.refund_status != 'SUCCESS'
            or amounts(replacement) != amounts(row)):
            raise DomainError('REPLACEMENT_MISMATCH', '后续售后须属于原订单、已成功退款结案且逐行退款金额相同')
    elif row.stock_processed:
        raise DomainError('REPLACEMENT_REQUIRED', '货物已退库，须先关联已完成退款的后续售后单，不能直接结束客户退款义务')
    row.status = 'CLOSED'
    event(db, user, row, 'FAILED_RESOLVED', evidence)
    await db.commit(); return row
