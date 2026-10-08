import asyncio
from uuid import uuid4
from test_phase2_inventory import post
from test_phase2_sales import sale


async def test_failed_refund_cannot_receive_released_return_quantity(client):
    order, product, _ = await sale(client, stock_quantity=1, tracking='QUANTITY')
    await post(client,f"/sales/orders/{order['id']}/confirm",{})
    await post(client,f"/sales/orders/{order['id']}/pay",{'method':'CARD'})
    await post(client,f"/sales/orders/{order['id']}/dispatch",{})
    body={'request_key':str(uuid4()),'order_id':order['id'],'kind':'RETURN_REFUND','reason':'核实失败后重新申请',
        'scenario':'DECLINED','lines':[{'line_id':order['lines'][0]['id'],'refund_amount':'199.90','return_quantity':1}]}
    first=await post(client,'/aftersales',body)
    await post(client,f"/aftersales/{first['id']}/review",{'decision':'APPROVE','note':'模拟批准'})
    assert (await post(client,f"/aftersales/{first['id']}/refund",{}))['refund_status']=='FAILED'
    second=await post(client,'/aftersales',{**body,'request_key':str(uuid4()),'scenario':'NORMAL'})
    await post(client,f"/aftersales/{second['id']}/review",{'decision':'APPROVE','note':'模拟替代申请'})
    receipt={'note':'实际仅收到原售出的一件','lines':[{'line_id':order['lines'][0]['id'],'serials':[]}]}
    assert (await client.post(f"/api/v1/aftersales/{first['id']}/receive",json=receipt)).status_code==409
    await post(client,f"/aftersales/{second['id']}/receive",receipt)
    stock=next(s for s in (await client.get('/api/v1/inventory/stock')).json()['items'] if s['product_id']==product['id'])
    assert stock['quantity']==1


async def test_failed_cancel_can_close_with_evidence_and_resume_delivery(client):
    order,_,_=await sale(client,stock_quantity=1)
    await post(client,f"/sales/orders/{order['id']}/confirm",{})
    await post(client,f"/sales/orders/{order['id']}/pay",{'method':'CARD'})
    case=await post(client,'/aftersales',{'request_key':str(uuid4()),'order_id':order['id'],'kind':'CANCEL_UNSHIPPED','reason':'模拟取消失败后继续原订单','scenario':'DECLINED',
        'lines':[{'line_id':order['lines'][0]['id'],'refund_amount':'199.90','return_quantity':1}]})
    await post(client,f"/aftersales/{case['id']}/review",{'decision':'APPROVE','note':'模拟批准'})
    assert (await client.post(f"/api/v1/aftersales/{case['id']}/resolve-failure",json={'note':'未核实不能结束'})).status_code==409
    await post(client,f"/aftersales/{case['id']}/refund",{})
    done=await post(client,f"/aftersales/{case['id']}/resolve-failure",{'note':'已核实原退款失败，客户决定继续原订单并接受交付'})
    assert done['status']=='CLOSED' and done['refund_status']=='FAILED'
    assert (await post(client,f"/sales/orders/{order['id']}/dispatch",{}))['stock_status']=='SHIPPED'


async def test_received_return_failed_refund_needs_completed_replacement(client):
    order,_,_=await sale(client,stock_quantity=1,tracking='QUANTITY')
    for action,body in [('confirm',{}),('pay',{'method':'CARD'}),('dispatch',{})]:
        await post(client,f"/sales/orders/{order['id']}/{action}",body)
    body={'request_key':str(uuid4()),'order_id':order['id'],'kind':'RETURN_REFUND','reason':'退库后退款拒绝','scenario':'DECLINED',
        'lines':[{'line_id':order['lines'][0]['id'],'refund_amount':'199.90','return_quantity':1}]}
    first=await post(client,'/aftersales',body)
    await post(client,f"/aftersales/{first['id']}/review",{'decision':'APPROVE','note':'核实原单'})
    await post(client,f"/aftersales/{first['id']}/receive",{'note':'验收原商品','lines':[{'line_id':order['lines'][0]['id'],'serials':[]}]})
    await post(client,f"/aftersales/{first['id']}/refund",{})
    resolution={'note':'保留失败回执，后续退款义务已履行'}
    assert (await client.post(f"/api/v1/aftersales/{first['id']}/resolve-failure",json=resolution)).status_code==409
    second=await post(client,'/aftersales',{**body,'request_key':str(uuid4()),'kind':'REFUND_ONLY','scenario':'NORMAL',
        'lines':[{**body['lines'][0],'return_quantity':0}]})
    await post(client,f"/aftersales/{second['id']}/review",{'decision':'APPROVE','note':'原请求已明确失败，另立退款处理单'})
    await post(client,f"/aftersales/{second['id']}/refund",{})
    await post(client,f"/aftersales/{second['id']}/close",{'note':'只补退款，不重复入库'})
    resolution['replacement_after_sale_id']=second['id']
    closed=await post(client,f"/aftersales/{first['id']}/resolve-failure",resolution)
    assert closed['status']=='CLOSED' and closed['refund_status']=='FAILED'
    assert (await client.post(f"/api/v1/aftersales/{first['id']}/resolve-failure",json={**resolution,'note':'覆盖原依据'})).status_code==409


async def test_partial_return_refund_unknown_replay_and_transaction(client):
    order, product, _ = await sale(client, quantity=2, stock_quantity=2)
    await post(client, f"/sales/orders/{order['id']}/confirm", {})
    payment = await post(client, f"/sales/orders/{order['id']}/pay", {'method':'CARD'})
    await post(client, f"/sales/orders/{order['id']}/dispatch", {})
    transaction = await post(client, '/transactions', {'request_key':str(uuid4()), 'customer_id':order['customer_id'], 'title':'模拟组合交易', 'required':['SALE'], 'order_ids':[order['id']]})
    assert transaction['status'] == 'COMPLETED'
    body = {'request_key':str(uuid4()), 'order_id':order['id'], 'kind':'RETURN_REFUND', 'reason':'模拟退回其中一台设备', 'scenario':'SUCCESS_TIMEOUT',
        'lines':[{'line_id':order['lines'][0]['id'], 'refund_amount':'199.90', 'return_quantity':1}]}
    case = await post(client, '/aftersales', body)
    assert (await post(client, '/aftersales', body))['id'] == case['id']
    await post(client, f"/aftersales/{case['id']}/review", {'decision':'APPROVE', 'note':'核对原单后批准'})
    receipt = {'note':'原设备完整，序列号核对通过', 'lines':[{'line_id':order['lines'][0]['id'], 'serials':[payment['allocations'][0]['serials'][0]]}]}
    await post(client, f"/aftersales/{case['id']}/receive", receipt)
    await post(client, f"/aftersales/{case['id']}/receive", receipt)
    unknown = await post(client, f"/aftersales/{case['id']}/refund", {})
    assert unknown['refund_status'] == 'UNKNOWN'
    assert (await client.get('/api/v1/transactions/'+transaction['id'])).json()['net_amount'] is None
    resolved = await post(client, f"/aftersales/{case['id']}/reconcile", {})
    assert resolved['refund_status'] == 'SUCCESS' and resolved['external_request_id'] == unknown['external_request_id']
    await post(client, f"/aftersales/{case['id']}/close", {'note':'模拟退款与退库均已核实'})
    stock = next(x for x in (await client.get('/api/v1/inventory/stock')).json()['items'] if x['product_id']==product['id'])
    assert stock['quantity'] == 1
    excessive = {**body, 'request_key':str(uuid4()), 'kind':'REFUND_ONLY', 'lines':[{'line_id':order['lines'][0]['id'], 'refund_amount':'399.80', 'return_quantity':0}]}
    assert (await client.post('/api/v1/aftersales', json=excessive)).status_code == 409
    final = (await client.get('/api/v1/transactions/'+transaction['id'])).json()
    assert final['status'] == 'COMPLETED_WITH_ADJUSTMENTS' and final['refunded_amount'] == '199.90'


async def test_concurrent_refund_applications_reserve_the_remaining_amount(client):
    order, _, _ = await sale(client, stock_quantity=1)
    await post(client, f"/sales/orders/{order['id']}/confirm", {})
    await post(client, f"/sales/orders/{order['id']}/pay", {'method':'WECHAT'})
    body = {'order_id':order['id'], 'kind':'REFUND_ONLY', 'reason':'模拟部分价格补偿', 'lines':[{'line_id':order['lines'][0]['id'], 'refund_amount':'149.93', 'return_quantity':0}]}
    responses = await asyncio.gather(*(client.post('/api/v1/aftersales',json={**body,'request_key':str(uuid4())}) for _ in range(2)))
    assert sorted(r.status_code for r in responses) == [200,409]
