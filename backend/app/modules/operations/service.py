from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.core.db import utcnow
from app.core.errors import DomainError
from app.core.digests import content_hash
from app.core.security import require_role
from app.modules.auth.models import Store
from app.modules.sales.models import SalesOrder, SalesLine, Payment
from app.modules.inventory.models import Stock
from app.modules.acceptances.models import Acceptance
from app.modules.installations.models import Installation
from app.modules.finance.models import Earning
from app.modules.finance.service import earning_view
from app.modules.improvements.service import metrics as service_metrics
from app.modules.operations.models import OperationsSnapshot, GEOBatch, GEOSample


async def overview(db, user, start, end):
    require_role(user, 'MANAGER', 'ADMIN')
    if start >= end or (end-start).days > 366: raise DomainError('INVALID_RANGE', '请选择不超过一年的有效时间范围', 422)
    store = await db.get(Store, user.store_id)
    sales = (await db.scalars(select(SalesOrder).where(SalesOrder.store_id == user.store_id, SalesOrder.created_at >= start, SalesOrder.created_at < end))).all()
    paid = (await db.scalars(select(Payment).where(Payment.store_id == user.store_id, Payment.status == 'SUCCESS', Payment.settled_at >= start, Payment.settled_at < end))).all()
    lines = (await db.scalars(select(SalesLine).where(SalesLine.order_id.in_([p.order_id for p in paid])))).all()
    stocks = (await db.scalars(select(Stock).where(Stock.store_id == user.store_id))).all()
    accepted = (await db.scalars(select(Acceptance).where(Acceptance.store_id == user.store_id, Acceptance.status == 'SUCCESS', Acceptance.updated_at >= start, Acceptance.updated_at < end))).all()
    works = (await db.scalars(select(Installation).where(Installation.store_id == user.store_id, Installation.completed_at >= start, Installation.completed_at < end))).all()
    earnings = (await db.scalars(select(Earning).where(Earning.store_id == user.store_id, Earning.created_at >= start, Earning.created_at < end))).all()
    earning_data = [await earning_view(db, e) for e in earnings]
    from app.modules.aftersales.models import AfterSale, Reversal
    refunds = (await db.scalars(select(AfterSale).where(AfterSale.store_id == user.store_id, AfterSale.refund_status == 'SUCCESS', AfterSale.refunded_at >= start, AfterSale.refunded_at < end))).all()
    reversals = (await db.scalars(select(Reversal).where(Reversal.store_id == user.store_id, Reversal.status == 'SUCCESS', Reversal.updated_at >= start, Reversal.updated_at < end))).all()
    service = await service_metrics(db, user, start, end)
    values = {}

    def add(key, label, value, unit, definition, evidence, page):
        values[key] = {'label': label, 'value': str(value) if value is not None else '暂无数据', 'unit': unit,
            'definition': definition, 'evidence_ids': [str(e) for e in evidence], 'page': page}

    add('orders', '新建销售单', len(sales), '笔', '按订单创建时间，含未付款及已取消草稿', [s.id for s in sales], 'sales')
    add('paid_amount', '成功收款', sum((p.amount for p in paid), Decimal('0.00')), '元', '按支付核实成功时间；全部为模拟收款', [p.order_id for p in paid], 'sales')
    add('refunded_amount', '成功退款', sum((r.amount for r in refunds),Decimal('0.00')), '元', '按退款核实成功时间，原成功收款保留；不同统计期可能产生净流出', [r.id for r in refunds], 'aftersales')
    add('telecom_reversed', '通信冲正成功', len(reversals), '笔', '冲正与原成功受理分别留账', [r.id for r in reversals], 'reversals')
    for key, category, name in [('operating_receipts','OPERATING','经营类实收'),('collected_funds','COLLECTION','代收款'),('deposits','DEPOSIT','押金')]:
        chosen = [l for l in lines if l.snapshot['receipt_category'] == category]
        add(key, name, sum((l.amount for l in chosen), Decimal('0.00')), '元', '已成功收款的订单行按冻结分类汇总；实收不等于利润', list(dict.fromkeys(l.order_id for l in chosen)), 'sales')
    add('stock_units', '当前在库', sum(s.quantity for s in stocks), '件', '查询时点库存，包含已占用待出库；不按日期回溯', [s.product_id for s in stocks], 'inventory')
    add('stock_available', '当前可用库存', sum(s.quantity-s.reserved for s in stocks), '件', '查询时点在库扣除未释放的占用', [s.product_id for s in stocks], 'inventory')
    add('telecom_success', '通信办理成功', len(accepted), '笔', '按核实成功的记录更新时间，排除 UNKNOWN', [a.service_id for a in accepted], 'services')
    add('installation_completed', '客户验收完成', len(works), '单', '按客户验收完成时间', [w.id for w in works], 'installations')
    for key, name, field in [('estimated_earnings','调整后预估收益','adjusted_expected'),('received_earnings','已到账收益','actual_received'),('pending_commission','未结算提成（含扣回）','remaining_commission')]:
        known = [e for e in earning_data if e[field] is not None]
        total = sum((Decimal(e[field]) for e in known), Decimal('0.00')) if known or not earning_data else None
        add(key, name, total, '元', f'按收益台账创建时间选业务；到账为截至快照的账单到账；已知 {len(known)} 笔，未知 {len(earning_data)-len(known)} 笔，差异另行核对', [e.id for e in earnings], 'finance')
    add('settleable_commission', '可发提成（抵扣后）', sum((Decimal(e['available_commission']) for e in earning_data), Decimal('0.00')), '元', '按冻结规则及已到账比例计算，扣除已结算并保留退款负余额；全部为模拟结算', [e.id for e in earnings], 'finance')
    satisfaction = service.payload['satisfaction']
    add('satisfaction', '客户评分均值', round(satisfaction['average'], 2) if satisfaction['average'] is not None else None, '分',
        f"已结束接待的有效评价，样本 {satisfaction['sample_count']}；未评价不补分", service.evidence['service_ids'], 'services')
    waiting = service.payload['waiting']
    add('waiting', '等待 P90', waiting['p90_seconds'], '秒', f"按票创建时间选取，最近秩法，样本 {waiting['sample_count']}", service.evidence['queue_ticket_ids'], 'queue')
    quality = service.payload['quality_problem_rate']
    add('quality', '质检问题 / 已检输入', f"{quality['numerator']}/{quality['denominator']}", '项', '确定性阻断或人工驳回/修订；按输入摘要去重，不等于客户评分', service.evidence['quality_check_ids'], 'quality')
    snapshot = OperationsSnapshot(store_id=user.store_id, filters={'from': start.isoformat(), 'to': end.isoformat(), 'timezone': 'Asia/Shanghai',
        'store_name': store.name, 'interval': '左闭右开', 'as_of': utcnow().isoformat(), 'simulated': True}, metrics=values)
    db.add(snapshot); await db.commit(); return snapshot


async def import_geo(db, user, data):
    require_role(user, 'MANAGER', 'ADMIN')
    ih = content_hash(data.model_dump(mode='json'))
    bid = await db.scalar(insert(GEOBatch).values(store_id=user.store_id, actor_id=user.user_id, request_key=data.request_key, input_hash=ih)
        .on_conflict_do_nothing().returning(GEOBatch.id))
    row = await db.scalar(select(GEOBatch).where(GEOBatch.store_id == user.store_id, GEOBatch.request_key == data.request_key))
    if row.input_hash != ih: raise DomainError('KEY_CONFLICT', '同一采样请求号对应不同回答')
    if bid:
        for s in data.samples:
            db.add(GEOSample(store_id=user.store_id, batch_id=bid, **{**s.model_dump(), 'citations': [str(url) for url in s.citations]}, mentioned=s.brand.casefold() in s.answer.casefold()))
        await db.commit()
    return {'ids': list((await db.scalars(select(GEOSample.id).where(GEOSample.batch_id == row.id).order_by(GEOSample.created_at, GEOSample.id))).all())}
