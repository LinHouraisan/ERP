from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import select
from app.core.config import business_date
from app.modules.aftersales.models import AfterSale
from app.modules.finance.models import Earning, EarningAdjustment


async def refund_adjustment(db, user, case):
    earning = await db.scalar(select(Earning).where(Earning.order_id == case.order_id).with_for_update())
    if earning is None: return
    existing = (await db.scalars(select(EarningAdjustment).where(EarningAdjustment.earning_id == earning.id, EarningAdjustment.after_sale_id.is_not(None)))).all()
    if any(x.after_sale_id == case.id for x in existing): return
    base = Decimal(earning.snapshot['base_amount'])
    if not base: return
    cases = (await db.scalars(select(AfterSale).where(AfterSale.order_id == case.order_id, AfterSale.refund_status == 'SUCCESS', AfterSale.refunded_at <= case.refunded_at))).all()
    refunded = sum((Decimal(line['refund_amount']) for c in cases for line in c.lines if line['snapshot']['receipt_category'] == 'OPERATING'), Decimal('0.00'))
    expected = -(earning.expected_amount*refunded/base).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    commission = -(earning.commission_amount*refunded/base).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    db.add(EarningAdjustment(store_id=user.store_id, earning_id=earning.id, after_sale_id=case.id, actor_id=user.user_id,
        period=business_date().strftime('%Y-%m'), expected_delta=expected-sum((x.expected_delta for x in existing), Decimal('0.00')),
        commission_delta=commission-sum((x.commission_delta for x in existing), Decimal('0.00')),
        reason='原单退款按冻结收益及提成比例冲回；原记录保留',
        snapshot={'operating_refunded': str(refunded), 'original_operating_base': str(base), 'rule': earning.snapshot['rule']}))


async def reversal_adjustment(db, user, reversal):
    earning = await db.scalar(select(Earning).where(Earning.acceptance_id == reversal.acceptance_id).with_for_update())
    if earning is None: return
    if await db.scalar(select(EarningAdjustment.id).where(EarningAdjustment.earning_id == earning.id, EarningAdjustment.reversal_id == reversal.id)): return
    adjustments = (await db.scalars(select(EarningAdjustment).where(EarningAdjustment.earning_id == earning.id))).all()
    db.add(EarningAdjustment(store_id=user.store_id, earning_id=earning.id, reversal_id=reversal.id, actor_id=user.user_id,
        period=business_date().strftime('%Y-%m'), expected_delta=-earning.expected_amount-sum((x.expected_delta for x in adjustments),Decimal('0.00')),
        commission_delta=-earning.commission_amount-sum((x.commission_delta for x in adjustments),Decimal('0.00')),
        reason='通信冲正已核实；冲回原收益，保留原受理及结算事实', snapshot={'rule':earning.snapshot['rule']}))
