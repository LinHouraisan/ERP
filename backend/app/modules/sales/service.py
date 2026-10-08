from datetime import datetime, time, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from app.core.config import business_date
from app.core.db import utcnow
from app.core.digests import content_hash
from app.core.errors import DomainError
from app.core.security import owned, require_role
from app.integrations import boss
from app.modules.accounts.models import Customer, AccountSnapshot, BusinessAccount
from app.modules.auth.models import Store, User
from app.modules.catalog.models import PolicyVersion, Product
from app.modules.catalog.service import effective
from app.modules.services.models import ServiceSession
from app.modules.acceptances.models import Acceptance
from app.modules.inventory.models import StockSerial, StockMovement
from app.modules.inventory.service import locked_stock
from app.modules.sales.models import SalesOrder, SalesLine, Payment, SalesEvent, DayClose
from app.modules.sales.schemas import payment_view


def event(db, user, oid, action, detail=None):
    db.add(SalesEvent(store_id=user.store_id, order_id=oid, actor_id=user.user_id, action=action, detail=detail or {}))


async def order_view(db, row):
    lines = (await db.scalars(select(SalesLine).where(SalesLine.order_id == row.id).order_by(SalesLine.id))).all()
    pay = await db.scalar(select(Payment).where(Payment.order_id == row.id))
    from app.modules.aftersales.models import AfterSale
    cases = (await db.scalars(select(AfterSale).where(AfterSale.order_id == row.id, AfterSale.status != 'REJECTED'))).all()
    remaining = {}
    for line in lines:
        parts = [(case,part) for case in cases for part in case.lines if part['line_id'] == str(line.id)]
        remaining[line.id] = {'refundable_amount':str(line.amount-sum((Decimal(p['refund_amount']) for c,p in parts if c.refund_status != 'FAILED'),Decimal('0.00'))),
            'returnable_quantity':line.quantity-sum(p['return_quantity'] for c,p in parts if c.refund_status != 'FAILED' or c.stock_processed)}
    return {'id': row.id, 'customer_id': row.customer_id, 'source_service_id': row.source_service_id, 'source_acceptance_id': row.source_acceptance_id,
        'status': row.status, 'stock_status': row.stock_status, 'total': str(row.total), 'created_at': row.created_at,
        'confirmed_by': row.confirmed_by, 'confirmed_at': row.confirmed_at, 'shipped_at': row.shipped_at,
        'lines': [{'id': x.id, 'policy_version_id': x.policy_version_id, 'product_id': x.product_id, 'quantity': x.quantity,
            'unit_price': str(x.unit_price), 'discount': str(x.discount), 'amount': str(x.amount), 'snapshot': x.snapshot, **remaining[x.id]} for x in lines],
        'after_sales':[{'id':c.id,'status':c.status,'refund_status':c.refund_status,'amount':str(c.amount)} for c in cases],
        'payment': payment_view(pay) if pay else None}


async def check_policy(db, user, policy, customer_id, acceptance_id):
    day = business_date()
    latest = await db.scalar(select(func.max(PolicyVersion.version)).where(PolicyVersion.product_id == policy.product_id,
        PolicyVersion.status == 'PUBLISHED', PolicyVersion.valid_from <= day, PolicyVersion.valid_to >= day))
    if not effective(policy, day) or policy.version != latest: raise DomainError('POLICY_CHANGED', '有效价格政策已变化，请重新生成订单并确认')
    product = await owned(db, Product, policy.product_id, user)
    store = await db.get(Store, user.store_id)
    conditions = policy.conditions
    if conditions.get('region') and conditions['region'] != store.region: raise DomainError('REGION_MISMATCH', '政策不适用于本门店地区')
    if product.kind == 'PACKAGE':
        accepted = await owned(db, Acceptance, acceptance_id, user) if acceptance_id else None
        if not accepted or accepted.status != 'SUCCESS' or accepted.external_payload.get('policy_version_id') != str(policy.id):
            raise DomainError('ACCEPTANCE_REQUIRED', '套餐收银须关联此政策已成功办理的受理单')
        from app.modules.aftersales.models import Reversal
        if await db.scalar(select(Reversal.id).where(Reversal.acceptance_id == accepted.id, Reversal.status != 'REJECTED')):
            raise DomainError('REVERSAL_PENDING', '原受理有冲正记录，不能继续按其收取套餐费用')
    elif conditions.get('verified_required', True) or conditions.get('new_customer_only') or conditions.get('minimum_tenure_months') or conditions.get('excludes_discount'):
        snapshot = await db.scalar(select(AccountSnapshot).join(BusinessAccount, AccountSnapshot.account_id == BusinessAccount.id).where(
            BusinessAccount.customer_id == customer_id, BusinessAccount.store_id == user.store_id).order_by(AccountSnapshot.source_time.desc()).limit(1))
        if snapshot is None or utcnow()-snapshot.source_time > timedelta(minutes=15): raise DomainError('FACTS_REQUIRED', '此优惠需要 15 分钟内的账号查询资料，请先查询')
        f = snapshot.payload
        if (conditions.get('verified_required', True) and f.get('verified') is not True
            or conditions.get('new_customer_only') and f.get('is_new_customer') is not True
            or conditions.get('minimum_tenure_months', 0) and (f.get('tenure_months') is None or f['tenure_months'] < conditions['minimum_tenure_months'])
            or conditions.get('excludes_discount') and (f.get('discounts') is None or conditions['excludes_discount'] in f['discounts'])):
            raise DomainError('INELIGIBLE', '优惠资格未知或不满足，请人工核实资料')
    if policy.one_time_fee is None: raise DomainError('UNKNOWN_PRICE', '一次费用未知，不能进入收银')
    discount = Decimal(conditions.get('sale_discount', '0.00'))
    if discount > policy.one_time_fee: raise DomainError('INVALID_DISCOUNT', '政策折扣超过一次费用，请联系管理员发布正确版本')
    return product, discount


async def create(db, user, data):
    require_role(user, 'STAFF', 'MANAGER', 'ADMIN')
    await owned(db, Customer, data.customer_id, user, lock=True)
    ih = content_hash(data.model_dump(mode='json'))
    existing = await db.scalar(select(SalesOrder).where(SalesOrder.store_id == user.store_id, SalesOrder.request_key == data.request_key))
    if existing:
        if existing.input_hash != ih: raise DomainError('KEY_CONFLICT', '同一请求号对应不同订单内容')
        return existing
    sid = data.source_service_id
    if data.source_acceptance_id:
        accepted = await owned(db, Acceptance, data.source_acceptance_id, user, lock=True)
        if sid and sid != accepted.service_id: raise DomainError('SOURCE_MISMATCH', '来源受理与接待不一致')
        sid = accepted.service_id
        used = await db.scalar(select(SalesOrder).where(SalesOrder.source_acceptance_id == accepted.id, SalesOrder.status != 'CANCELLED'))
        if used: raise DomainError('ALREADY_ORDERED', '此受理已经关联订单，请打开原订单')
    if sid:
        source = await owned(db, ServiceSession, sid, user)
        if source.customer_id != data.customer_id: raise DomainError('CUSTOMER_MISMATCH', '订单客户与来源接待不一致')
    lines, seen = [], set()
    for item in data.lines:
        p = await owned(db, PolicyVersion, item.policy_version_id, user)
        product, discount = await check_policy(db, user, p, data.customer_id, data.source_acceptance_id)
        if product.id in seen or product.kind == 'PACKAGE' and item.quantity != 1: raise DomainError('DUPLICATE_PRODUCT', '同一商品合并一行，套餐仅可按一次办理收费')
        seen.add(product.id)
        lines.append(SalesLine(store_id=user.store_id, product_id=product.id, policy_version_id=p.id, quantity=item.quantity,
            unit_price=p.one_time_fee, discount=discount, amount=((p.one_time_fee-discount)*item.quantity).quantize(Decimal('0.01')),
            snapshot={'name': product.name, 'kind': product.kind, 'tracking': product.tracking, 'version': p.version,
                'source': p.source, 'monthly_fee': str(p.monthly_fee) if p.monthly_fee is not None else None,
                'contract_months': p.contract_months, 'valid_from': str(p.valid_from), 'valid_to': str(p.valid_to), 'conditions': p.conditions,
                'receipt_category': 'COLLECTION' if product.kind == 'PACKAGE' else p.conditions.get('receipt_category', 'OPERATING')}))
    total = sum((x.amount for x in lines), Decimal('0.00'))
    if total > Decimal('9999999999.99'): raise DomainError('AMOUNT_LIMIT', '订单金额超过当前单据上限')
    rid = await db.scalar(insert(SalesOrder).values(store_id=user.store_id, customer_id=data.customer_id, source_service_id=sid,
        source_acceptance_id=data.source_acceptance_id, actor_id=user.user_id, request_key=data.request_key, input_hash=ih, total=total)
        .on_conflict_do_nothing().returning(SalesOrder.id))
    if rid is None: raise DomainError('KEY_CONFLICT', '订单请求号或来源已被另一笔单据使用')
    for line in lines: line.order_id = rid; db.add(line)
    event(db, user, rid, 'CREATED'); await db.commit()
    return await db.get(SalesOrder, rid)


async def confirm(db, user, oid):
    require_role(user, 'STAFF', 'MANAGER', 'ADMIN')
    row = await owned(db, SalesOrder, oid, user, lock=True)
    if row.status == 'CONFIRMED': return row
    if row.status != 'DRAFT': raise DomainError('INVALID_STATE', '仅草稿可确认')
    for line in (await db.scalars(select(SalesLine).where(SalesLine.order_id == oid))).all():
        await check_policy(db, user, await owned(db, PolicyVersion, line.policy_version_id, user), row.customer_id, row.source_acceptance_id)
    row.status, row.confirmed_by, row.confirmed_at = 'CONFIRMED', user.user_id, utcnow()
    event(db, user, oid, 'CONFIRMED'); await db.commit(); return row


async def cancel(db, user, oid):
    require_role(user, 'STAFF', 'MANAGER', 'ADMIN')
    row = await owned(db, SalesOrder, oid, user, lock=True)
    pay = await db.scalar(select(Payment).where(Payment.order_id == oid))
    if pay and pay.status != 'FAILED': raise DomainError('CANNOT_CANCEL', '已有收款请求，请先核对；本阶段不以取消订单代替退款')
    if row.status != 'CANCELLED': row.status = 'CANCELLED'; event(db, user, oid, 'CANCELLED')
    await db.commit(); return row


async def pay(db, user, oid, data):
    require_role(user, 'STAFF', 'MANAGER', 'ADMIN')
    await owned(db, User, user.user_id, user, lock=True)
    row = await owned(db, SalesOrder, oid, user, lock=True)
    existing = await db.scalar(select(Payment).where(Payment.order_id == oid))
    if existing:
        if existing.method != data.method or existing.scenario != data.scenario: raise DomainError('KEY_CONFLICT', '原付款请求的方式与内容不能更换')
        return existing
    if row.status != 'CONFIRMED': raise DomainError('CONFIRM_REQUIRED', '请先人工核对并确认订单')
    lines = (await db.scalars(select(SalesLine).where(SalesLine.order_id == oid).order_by(SalesLine.product_id))).all()
    allocations = []
    for line in lines:
        # Recheck a newer policy before committing a financial request; old confirmation cannot authorize new prices.
        await check_policy(db, user, await owned(db, PolicyVersion, line.policy_version_id, user), row.customer_id, row.source_acceptance_id)
        if line.snapshot['kind'] != 'GOODS': continue
        stock = await locked_stock(db, user, line.product_id)
        if stock.quantity-stock.reserved < line.quantity: raise DomainError('NO_STOCK', '可用库存不足，请补货后再收款')
        serials = []
        if line.snapshot['tracking'] == 'SERIAL':
            devices = (await db.scalars(select(StockSerial).where(StockSerial.store_id == user.store_id, StockSerial.product_id == line.product_id,
                StockSerial.status == 'AVAILABLE').order_by(StockSerial.created_at, StockSerial.id).limit(line.quantity).with_for_update())).all()
            if len(devices) != line.quantity: raise DomainError('NO_STOCK', '可用设备数量不足')
            for device in devices: device.status, device.order_id = 'RESERVED', oid; serials.append(device.serial)
        stock.reserved += line.quantity
        allocations.append({'product_id': str(line.product_id), 'quantity': line.quantity, 'serials': serials})
    payment = Payment(store_id=user.store_id, order_id=oid, cashier_id=user.user_id, amount=row.total,
        method=data.method, scenario=data.scenario, allocations=allocations)
    db.add(payment); await db.flush()
    row.stock_status = 'RESERVED' if allocations else 'NONE'
    event(db, user, oid, 'PAYMENT_REQUESTED', {'external_request_id': str(payment.external_request_id)})
    await db.commit()
    return await submit(db, user, payment)


def external_payload(payment):
    return {'external_request_id': str(payment.external_request_id), 'order_id': str(payment.order_id),
        'amount': str(payment.amount), 'method': payment.method, 'scenario': payment.scenario}


async def submit(db, user, payment):
    payload = external_payload(payment); await db.commit()
    try: result = await boss.payment_request('POST', '/mock/v1/payments', payload)
    except DomainError: result = {'status': 'UNKNOWN'}
    return await merge(db, user, payment.order_id, result)


async def merge(db, user, oid, result):
    row = await owned(db, SalesOrder, oid, user, lock=True)
    payment = await db.scalar(select(Payment).where(Payment.order_id == oid).with_for_update().execution_options(populate_existing=True))
    if payment.status in ('SUCCESS', 'FAILED'): return payment
    status = result.get('status')
    if status not in ('SUCCESS', 'FAILED') or not result.get('external_payment_id') or any(str(result.get(k)) != str(v) for k, v in
        {'external_request_id': payment.external_request_id, 'order_id': oid, 'amount': payment.amount, 'method': payment.method}.items()):
        status = 'UNKNOWN'
    if status == 'FAILED':
        for allocation in sorted(payment.allocations, key=lambda x: x['product_id']):
            stock = await locked_stock(db, user, UUID(allocation['product_id'])); stock.reserved -= allocation['quantity']
        for serial in (await db.scalars(select(StockSerial).where(StockSerial.order_id == oid).with_for_update())).all():
            serial.status, serial.order_id = 'AVAILABLE', None
        row.stock_status = 'NONE'
    payment.status = status
    if status in ('SUCCESS', 'FAILED'):
        payment.external_payment_id, payment.settled_at = UUID(result['external_payment_id']), utcnow()
        payment.last_error = '模拟支付拒绝，库存已释放' if status == 'FAILED' else None
    else: payment.last_error = '收款结果未知，库存保留；请按原请求号核对'
    event(db, user, oid, 'PAYMENT_'+status, {'external_request_id': str(payment.external_request_id)})
    await db.commit(); return payment


async def reconcile(db, user, oid):
    require_role(user, 'STAFF', 'MANAGER', 'ADMIN', 'FINANCE')
    await owned(db, SalesOrder, oid, user)
    payment = await db.scalar(select(Payment).where(Payment.order_id == oid))
    if payment is None: raise DomainError('PAYMENT_MISSING', '此订单尚未提交收款')
    if payment.status in ('SUCCESS', 'FAILED'): return payment
    rid = payment.external_request_id; await db.commit()
    try:
        result = await boss.payment_request('GET', f'/mock/v1/payments/by-request/{rid}')
        if result['status'] == 'NOT_FOUND': return await submit(db, user, payment)
    except DomainError: result = {'status': 'UNKNOWN'}
    return await merge(db, user, oid, result)


async def dispatch(db, user, oid):
    require_role(user, 'WAREHOUSE', 'MANAGER', 'ADMIN')
    order = await owned(db, SalesOrder, oid, user, lock=True)
    payment = await db.scalar(select(Payment).where(Payment.order_id == oid))
    if payment is None or payment.status != 'SUCCESS': raise DomainError('PAYMENT_REQUIRED', '成功收款后才能出库')
    if order.stock_status != 'RESERVED': return order
    from app.modules.aftersales.models import AfterSale
    from app.modules.aftersales.service import remaining_allocations
    hold = await db.scalar(select(AfterSale.id).where(AfterSale.order_id == oid, AfterSale.status.in_(['REQUESTED','APPROVED']), AfterSale.kind == 'CANCEL_UNSHIPPED').limit(1))
    if hold: raise DomainError('AFTERSALE_PENDING', '订单有取消交付申请，须先处理售后')
    allocations = await remaining_allocations(db, order, payment)
    for allocation in sorted(allocations, key=lambda x: x['product_id']):
        pid = UUID(allocation['product_id']); stock = await locked_stock(db, user, pid)
        stock.quantity -= allocation['quantity']; stock.reserved -= allocation['quantity']
        db.add(StockMovement(store_id=user.store_id, product_id=pid, order_id=oid, actor_id=user.user_id,
            quantity=-allocation['quantity'], serials=allocation['serials']))
    for serial in (await db.scalars(select(StockSerial).where(StockSerial.order_id == oid).with_for_update())).all():
        if serial.status != 'RESERVED': raise DomainError('SERIAL_STATE', '设备状态发生变化，请核查')
        serial.status = 'SHIPPED'
    order.stock_status, order.shipped_at = 'SHIPPED', utcnow()
    event(db, user, oid, 'DISPATCHED'); await db.commit(); return order


async def day_close(db, user, data):
    require_role(user, 'STAFF', 'MANAGER', 'ADMIN', 'FINANCE')
    if user.role == 'STAFF' and data.cashier_id != user.user_id: raise DomainError('FORBIDDEN', '只能交接自己的收款', 403)
    await owned(db, User, data.cashier_id, user, lock=True)
    ih = content_hash(data.model_dump(mode='json'))
    old = await db.scalar(select(DayClose).where(DayClose.store_id == user.store_id, DayClose.request_key == data.request_key))
    if old:
        if old.input_hash != ih: raise DomainError('KEY_CONFLICT', '交接请求号对应不同内容')
        return old
    start = datetime.combine(data.business_day, time(), ZoneInfo('Asia/Shanghai')); end = start+timedelta(days=1)
    q = select(Payment).where(Payment.store_id == user.store_id, Payment.cashier_id == data.cashier_id, Payment.created_at >= start,
        Payment.created_at < end, Payment.day_close_id.is_(None))
    payments = (await db.scalars(q.with_for_update())).all()
    if any(p.status in ('PENDING', 'UNKNOWN') for p in payments): raise DomainError('UNRESOLVED_PAYMENT', '此班次有未核明的收款，请先按原请求号核对')
    paid = [p for p in payments if p.status == 'SUCCESS']
    from app.modules.aftersales.models import AfterSale
    refund_query = select(AfterSale).join(Payment, Payment.order_id == AfterSale.order_id).where(
        AfterSale.store_id == user.store_id, Payment.cashier_id == data.cashier_id, AfterSale.day_close_id.is_(None))
    if await db.scalar(refund_query.where(AfterSale.refund_status.in_(['PENDING','UNKNOWN'])).limit(1)):
        raise DomainError('UNRESOLVED_REFUND', '有退款结果尚未核明，请先按原请求号核对')
    refunds = (await db.scalars(refund_query.where(AfterSale.refund_status == 'SUCCESS', AfterSale.refunded_at >= start, AfterSale.refunded_at < end).with_for_update(of=AfterSale))).all()
    if not paid and not refunds: raise DomainError('EMPTY_CLOSE', '没有尚未交接的成功收款或退款')
    methods = {method: sum((p.amount for p in paid if p.method == method), Decimal('0.00')) for method in ('CASH','CARD','WECHAT','ALIPAY')}
    refund_methods = {k: Decimal('0.00') for k in methods}
    for refund in refunds:
        original = await db.scalar(select(Payment).where(Payment.order_id == refund.order_id))
        refund_methods[original.method] += refund.amount
    categories = {k: Decimal('0.00') for k in ('OPERATING', 'COLLECTION', 'DEPOSIT')}
    for line in (await db.scalars(select(SalesLine).where(SalesLine.order_id.in_([p.order_id for p in paid])))).all(): categories[line.snapshot['receipt_category']] += line.amount
    refund_categories = {k: Decimal('0.00') for k in categories}
    for refund in refunds:
        for line in refund.lines: refund_categories[line['snapshot']['receipt_category']] += Decimal(line['refund_amount'])
    net_methods = {k: methods[k]-refund_methods[k] for k in methods}
    row = DayClose(store_id=user.store_id, actor_id=user.user_id, cashier_id=data.cashier_id, business_day=data.business_day,
        request_key=data.request_key, input_hash=ih, counted_cash=data.counted_cash, difference=data.counted_cash-net_methods['CASH'],
        totals={'methods': {k: str(v) for k,v in methods.items()}, 'categories': {k:str(v) for k,v in categories.items()},
            'payment_ids': [str(p.id) for p in paid], 'refund_ids':[str(r.id) for r in refunds], 'refunds': str(sum((r.amount for r in refunds),Decimal('0.00'))),
            'refund_methods':{k:str(v) for k,v in refund_methods.items()}, 'net_methods':{k:str(v) for k,v in net_methods.items()},
            'refund_categories':{k:str(v) for k,v in refund_categories.items()},
            'definition': '本次尚未交接的成功收退款；现金填写本次净交接额，退款支出可为负；代收与押金不计经营收入'})
    db.add(row); await db.flush()
    for p in paid: p.day_close_id = row.id
    for refund in refunds: refund.day_close_id = row.id
    await db.commit(); return row
