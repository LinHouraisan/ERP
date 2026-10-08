import os
from uuid import uuid4
from test_phase2_inventory import post
from test_phase2_sales import sale


async def test_component_resolution_preserves_unknown_and_replacement_progress(client):
    order, _, body = await sale(client, stock_quantity=2)
    await post(client,f"/sales/orders/{order['id']}/confirm",{})
    await post(client,f"/sales/orders/{order['id']}/pay",{'method':'CARD','scenario':'SUCCESS_TIMEOUT'})
    tx=await post(client,'/transactions',{'request_key':str(uuid4()),'customer_id':order['customer_id'],'title':'异常组合核查','required':['SALE'],'order_ids':[order['id']]})
    assert tx['status']=='NEEDS_ATTENTION'
    assert tx['received_amount'] is None and tx['net_amount'] is None
    assert (await client.post(f"/api/v1/transactions/{tx['id']}/resolve-component",json={'link_id':tx['children'][0]['link_id'],'note':'不能跳过未知结果'})).status_code==409
    await post(client,f"/sales/orders/{order['id']}/reconcile",{})
    assert (await client.post(f"/api/v1/transactions/{tx['id']}/resolve-component",json={'link_id':tx['children'][0]['link_id'],'note':'不能跳过待交付'})).status_code==409
    await post(client,f"/sales/orders/{order['id']}/dispatch",{})
    cancelled=await post(client,'/sales/orders',{**body,'request_key':str(uuid4())})
    await post(client,f"/sales/orders/{cancelled['id']}/cancel",{})
    replacement=await post(client,'/sales/orders',{**body,'request_key':str(uuid4())})
    tx=await post(client,f"/transactions/{tx['id']}/links",{'order_ids':[cancelled['id'],replacement['id']]})
    ids={c['id']:c['link_id'] for c in tx['children']}
    resolution={'link_id':ids[cancelled['id']],'replacement_link_id':ids[replacement['id']],'note':'客户同意原报价作废，按新单交付'}
    resolved=await post(client,f"/transactions/{tx['id']}/resolve-component",resolution)
    assert resolved['status']=='PARTIAL'
    assert resolved['original_amount']=='599.70' and resolved['net_amount']=='199.90'
    assert (await client.post(f"/api/v1/transactions/{tx['id']}/resolve-component",json={**resolution,'note':'覆盖原证据'})).status_code==409
    todos=(await client.get('/api/v1/todos')).json()['items']
    assert any(t['source_id']==tx['id'] and t['url']==f"/transactions?id={tx['id']}" for t in todos)
    for role in ('finance','installer','admin2'):
        auth=await post(client,'/auth/login',{'username':role,'password':os.environ['DEMO_PASSWORD']});client.headers['X-CSRF-Token']=auth['csrf_token']
        items=(await client.get('/api/v1/todos')).json()['items']
        assert all(t['source_id']!=tx['id'] for t in items)
        if role=='installer': assert all(t['kind']=='INSTALLATION' and t['owner_id']==auth['user_id'] for t in items)
        response=await client.get('/api/v1/transactions/'+tx['id'])
        assert response.status_code==(404 if role=='admin2' else 403)
