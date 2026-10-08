import os
from uuid import uuid4
from test_phase2_inventory import post, purchase


async def login(client,username):
    auth=await post(client,'/auth/login',{'username':username,'password':os.environ['DEMO_PASSWORD']})
    client.headers['X-CSRF-Token']=auth['csrf_token']


async def test_transfer_in_transit_partial_wrong_serial_and_store_boundaries(client):
    from app.seed import SECOND_STORE
    sku='TEST-'+uuid4().hex.upper()
    first=await post(client,'/products',{'name':'模拟调拨设备','kind':'GOODS','tracking':'SERIAL','sku':sku})
    supplier=await post(client,'/inventory/suppliers',{'name':'模拟调拨供应商'})
    po=await post(client,'/inventory/purchases',{'supplier_id':supplier['id'],'request_key':str(uuid4()),'lines':[{'product_id':first['id'],'quantity':2,'unit_cost':'20.00'}]})
    await post(client,f"/inventory/purchases/{po['id']}/approve",{})
    serials=['SN-'+uuid4().hex for _ in range(2)]
    await post(client,f"/inventory/purchases/{po['id']}/receive",{'request_key':str(uuid4()),'lines':[{'line_id':po['lines'][0]['id'],'quantity':2,'serials':serials}]})
    await login(client,'admin2')
    second=await post(client,'/products',{'name':'二店同编码设备','kind':'GOODS','tracking':'SERIAL','sku':sku})
    assert (await client.get('/api/v1/inventory/purchases/'+po['id'])).status_code==404
    await login(client,'admin')
    transfer=await post(client,'/transfers',{'request_key':str(uuid4()),'destination_store_id':str(SECOND_STORE),'product_id':first['id'],'quantity':2,'note':'同主体调拨'})
    await post(client,f"/transfers/{transfer['id']}/review",{'decision':'APPROVE','note':'核对两店商品编码'})
    shipped=await post(client,f"/transfers/{transfer['id']}/dispatch",{'note':'两台设备已交运'})
    assert shipped['in_transit']==2
    assert (await client.post(f"/api/v1/transfers/{transfer['id']}/receive",json={'request_key':str(uuid4()),'quantity':2,'serials':serials,'note':'冒领'})).status_code==404
    await login(client,'warehouse2')
    receipt={'request_key':str(uuid4()),'quantity':2,'serials':[serials[0],'WRONG-'+uuid4().hex],'note':'一台序列号不符，隔离待核'}
    received=await post(client,f"/transfers/{transfer['id']}/receive",receipt)
    assert received['status']=='DISCREPANCY' and received['received_quantity']==1 and received['in_transit']==1
    await post(client,f"/transfers/{transfer['id']}/receive",receipt)
    assert (await client.get('/api/v1/finance/earnings')).status_code==403
    final=await post(client,f"/transfers/{transfer['id']}/receive",{'request_key':str(uuid4()),'quantity':1,'serials':[serials[1]],'note':'补送并核实原序列号'})
    assert final['status']=='RECEIVED' and final['in_transit']==0
    dest=next(s for s in (await client.get('/api/v1/inventory/stock')).json()['items'] if s['product_id']==second['id'])
    assert dest['quantity']==2
    await login(client,'admin')
    source=next(s for s in (await client.get('/api/v1/inventory/stock')).json()['items'] if s['product_id']==first['id'])
    assert source['quantity']==0
    states=(await client.get('/api/v1/inventory/serials',params={'product_id':first['id']})).json()['items']
    assert all(s['status']=='TRANSFERRED' for s in states)


async def test_stock_count_requires_fresh_snapshot_and_does_not_erase_reservations(client):
    product,po=await purchase(client,tracking='QUANTITY',quantity=5)
    await post(client,f"/inventory/purchases/{po['id']}/receive",{'request_key':str(uuid4()),'lines':[{'line_id':po['lines'][0]['id'],'quantity':4,'serials':[]}]})
    stale=await post(client,'/inventory/counts',{'request_key':str(uuid4()),'product_id':product['id'],'actual_quantity':3,'note':'实盘少一件'})
    await post(client,f"/inventory/purchases/{po['id']}/receive",{'request_key':str(uuid4()),'lines':[{'line_id':po['lines'][0]['id'],'quantity':1,'serials':[]}]})
    assert (await client.post(f"/api/v1/inventory/counts/{stale['id']}/review",json={'decision':'APPROVE','note':'旧盘点'})).status_code==409
    fresh=await post(client,'/inventory/counts',{'request_key':str(uuid4()),'product_id':product['id'],'actual_quantity':4,'note':'重盘并附差异说明'})
    await post(client,f"/inventory/counts/{fresh['id']}/review",{'decision':'APPROVE','note':'核对短少依据'})
    await post(client,f"/inventory/counts/{fresh['id']}/review",{'decision':'APPROVE','note':'核对短少依据'})
    stock=next(s for s in (await client.get('/api/v1/inventory/stock')).json()['items'] if s['product_id']==product['id'])
    assert stock['quantity']==4
    from test_phase2_sales import sale
    order,held,_=await sale(client,stock_quantity=1)
    await post(client,f"/sales/orders/{order['id']}/confirm",{})
    await post(client,f"/sales/orders/{order['id']}/pay",{'method':'CARD'})
    assert (await client.post('/api/v1/inventory/counts',json={'request_key':str(uuid4()),'product_id':held['id'],'actual_quantity':0,'note':'不得抹除客户预留'})).status_code==409
