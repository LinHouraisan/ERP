import asyncio
import os
from decimal import Decimal
from uuid import uuid4
from test_phase2_inventory import post
from test_phase2_sales import sale


async def earned_sale(client):
    from app.core.db import session_scope
    from app.modules.auth.models import User
    from app.modules.auth.service import hash_password
    from app.seed import DEMO_STORE
    _, _, body = await sale(client, stock_quantity=2)
    username = 'phase3-'+uuid4().hex[:12]
    async with session_scope() as db:
        owner = User(store_id=DEMO_STORE,username=username,password_hash=hash_password(os.environ['DEMO_PASSWORD']),role='STAFF')
        db.add(owner); await db.commit(); uid=str(owner.id)
    login = await post(client,'/auth/login',{'username':username,'password':os.environ['DEMO_PASSWORD']})
    client.headers['X-CSRF-Token']=login['csrf_token']
    order=await post(client,'/sales/orders',{**body,'request_key':str(uuid4())})
    await post(client,f"/sales/orders/{order['id']}/confirm",{})
    await post(client,f"/sales/orders/{order['id']}/pay",{'method':'CASH'})
    login=await post(client,'/auth/login',{'username':'admin','password':os.environ['DEMO_PASSWORD']})
    client.headers['X-CSRF-Token']=login['csrf_token']
    await post(client,f"/sales/orders/{order['id']}/dispatch",{})
    rule=await post(client,'/finance/rules',{'business_type':'SALE','valid_from':'2026-01-01','valid_to':'2099-12-31','rate':'0.10','employee_rate':'0.20','settlement_condition':'BILL_MATCHED'})
    await post(client,f"/finance/rules/{rule['id']}/publish",{})
    earning=await post(client,'/finance/accruals',{'source_type':'SALE','source_id':order['id']})
    return order,earning,uid


async def test_cross_period_partial_settlement_and_refund_offset(client):
    order, earning, uid = await earned_sale(client)
    first={'request_key':str(uuid4()),'period':'2098-11','source':'模拟首期账单','rows':[{'business_no':earning['business_no'],'earning_period':earning['period'],'amount':'10.00','received_amount':'10.00','is_final':False}]}
    await post(client,'/finance/bills',first)
    view=(await client.get('/api/v1/finance/earnings/'+earning['id'])).json()
    assert view['match_status']=='TIMING_DIFFERENCE' and view['available_commission']=='2.00'
    settlement={'request_key':str(uuid4()),'owner_id':uid,'period':'2098-11','amount':'2.00','earning_ids':[earning['id']],'note':'模拟首期发放'}
    batch=await post(client,'/finance/settlements',settlement)
    await post(client,f"/finance/settlements/{batch['id']}/confirm",{'note':'核对收款与提成规则'})
    await post(client,f"/finance/settlements/{batch['id']}/confirm",{'note':'核对收款与提成规则'})
    second={**first,'request_key':str(uuid4()),'period':'2098-12','rows':[{**first['rows'][0],'amount':'9.99','received_amount':'9.99','is_final':True}]}
    await post(client,'/finance/bills',second)
    candidates=[await post(client,'/finance/settlements',{**settlement,'period':'2098-12','request_key':str(uuid4())}) for _ in range(2)]
    responses=await asyncio.gather(*(client.post(f"/api/v1/finance/settlements/{b['id']}/confirm",json={'note':'并发确认剩余提成'}) for b in candidates))
    assert sorted(r.status_code for r in responses)==[200,409]
    case=await post(client,'/aftersales',{'request_key':str(uuid4()),'order_id':order['id'],'kind':'REFUND_ONLY','reason':'模拟半额补偿',
        'lines':[{'line_id':order['lines'][0]['id'],'refund_amount':'99.95','return_quantity':0}]})
    await post(client,f"/aftersales/{case['id']}/review",{'decision':'APPROVE','note':'确认补偿'})
    await post(client,f"/aftersales/{case['id']}/refund",{})
    view=(await client.get('/api/v1/finance/earnings/'+earning['id'])).json()
    assert view['expected_amount']=='19.99' and view['adjusted_expected']=='9.99'
    assert view['settled_commission']=='4.00' and view['available_commission']=='-2.00'
    assert len(view['adjustments'])==1
    # Later business for the same employee must consume the old debt first.
    from app.core.db import session_scope
    from app.modules.auth.models import User
    from uuid import UUID
    async with session_scope() as db: username=(await db.get(User,UUID(uid))).username
    auth=await post(client,'/auth/login',{'username':username,'password':os.environ['DEMO_PASSWORD']});client.headers['X-CSRF-Token']=auth['csrf_token']
    replacement=await post(client,'/sales/orders',{'request_key':str(uuid4()),'customer_id':order['customer_id'],'lines':[{'policy_version_id':order['lines'][0]['policy_version_id'],'quantity':1}]})
    await post(client,f"/sales/orders/{replacement['id']}/confirm",{})
    await post(client,f"/sales/orders/{replacement['id']}/pay",{'method':'CARD'})
    auth=await post(client,'/auth/login',{'username':'admin','password':os.environ['DEMO_PASSWORD']});client.headers['X-CSRF-Token']=auth['csrf_token']
    await post(client,f"/sales/orders/{replacement['id']}/dispatch",{})
    new=await post(client,'/finance/accruals',{'source_type':'SALE','source_id':replacement['id']})
    await post(client,'/finance/bills',{'request_key':str(uuid4()),'period':'2098-12','source':'模拟后续业务到账','rows':[{'business_no':new['business_no'],'earning_period':new['period'],'amount':'19.99','received_amount':'19.99'}]})
    release=await post(client,'/finance/settlements',{**settlement,'request_key':str(uuid4()),'period':'2098-12','earning_ids':[new['id']]})
    result=await post(client,f"/finance/settlements/{release['id']}/confirm",{'note':'先抵扣原订单退款造成的已发提成差额'})
    assert sorted(Decimal(l['amount']) for l in result['lines'])==[Decimal('-2.00'),Decimal('4.00')]


async def test_reconciliation_requires_approval_and_unknown_receipt_stays_unknown(client):
    from datetime import UTC,datetime,timedelta
    _,earning,_=await earned_sale(client)
    actor=(await client.get('/api/v1/auth/me')).json()
    case=await post(client,'/finance/cases',{'request_key':str(uuid4()),'earning_id':earning['id'],'owner_id':actor['user_id'],
        'kind':'ADJUSTMENT','proposed_delta':'1.00','reason':'模拟运营方补发一元收益','due_at':(datetime.now(UTC)+timedelta(days=2)).isoformat()})
    assert (await client.post(f"/api/v1/finance/cases/{case['id']}/close",json={'note':'尚未批准不能关闭','manual':True})).status_code==409
    auth=await post(client,'/auth/login',{'username':'finance','password':os.environ['DEMO_PASSWORD']});client.headers['X-CSRF-Token']=auth['csrf_token']
    assert (await client.post(f"/api/v1/finance/cases/{case['id']}/approve-adjustment",json={'note':'越权批准'})).status_code==403
    auth=await post(client,'/auth/login',{'username':'admin','password':os.environ['DEMO_PASSWORD']});client.headers['X-CSRF-Token']=auth['csrf_token']
    await post(client,f"/finance/cases/{case['id']}/approve-adjustment",{'note':'模拟补发通知已核实'})
    await post(client,f"/finance/cases/{case['id']}/approve-adjustment",{'note':'模拟补发通知已核实'})
    await post(client,'/finance/bills',{'request_key':str(uuid4()),'period':earning['period'],'source':'模拟补发后账单','rows':[{'business_no':earning['business_no'],'amount':'20.99','received_amount':None}]})
    refreshed=(await client.get('/api/v1/finance/earnings/'+earning['id'])).json()
    assert refreshed['adjusted_expected']=='20.99' and refreshed['adjusted_commission']=='4.20' and refreshed['actual_received'] is None
    assert (await client.post(f"/api/v1/finance/cases/{case['id']}/close",json={'note':'未核实到账不能自动关闭'})).status_code==409
    final=await post(client,f"/finance/cases/{case['id']}/close",{'note':'模拟补发差额核实完毕，到账仍未知，保留账面待收','manual':True})
    assert final['status']=='CLOSED'


async def test_cash_handover_includes_refund_once_after_original_close(client):
    from app.core.config import business_date
    order, _, uid = await earned_sale(client)
    body={'request_key':str(uuid4()),'business_day':str(business_date()),'cashier_id':uid,'counted_cash':'199.90'}
    original=await post(client,'/sales/day-closes',body)
    case=await post(client,'/aftersales',{'request_key':str(uuid4()),'order_id':order['id'],'kind':'REFUND_ONLY','reason':'模拟现金补偿',
        'lines':[{'line_id':order['lines'][0]['id'],'refund_amount':'50.00','return_quantity':0}]})
    await post(client,f"/aftersales/{case['id']}/review",{'decision':'APPROVE','note':'核对现金原单'})
    await post(client,f"/aftersales/{case['id']}/refund",{})
    closing=await post(client,'/sales/day-closes',{**body,'request_key':str(uuid4()),'counted_cash':'-50.00'})
    assert closing['difference']=='0.00' and closing['totals']['refunds']=='50.00'
    assert closing['totals']['payment_ids']==[] and closing['totals']['refund_ids']==[case['id']]
    assert original['totals']['refunds']=='0.00'
    assert (await client.post('/api/v1/sales/day-closes',json={**body,'request_key':str(uuid4())})).status_code==409
