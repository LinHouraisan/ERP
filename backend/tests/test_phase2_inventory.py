from uuid import uuid4


async def post(client, path, body):
    r = await client.post('/api/v1' + path, json=body)
    assert r.status_code < 300, r.text
    return r.json()


async def purchase(client, tracking='SERIAL', quantity=2):
    product = await post(client, '/products', {'name': '库存检查-' + uuid4().hex[:8], 'kind': 'GOODS', 'tracking': tracking})
    supplier = await post(client, '/inventory/suppliers', {'name': '模拟供应商', 'contact': '测试联系人'})
    body = {'supplier_id': supplier['id'], 'request_key': str(uuid4()), 'lines': [{'product_id': product['id'], 'quantity': quantity, 'unit_cost': '100.10'}]}
    order = await post(client, '/inventory/purchases', body)
    assert (await post(client, '/inventory/purchases', body))['id'] == order['id']
    await post(client, f"/inventory/purchases/{order['id']}/approve", {})
    return product, order


async def test_partial_receipt_replay_conflict_and_serial_unique(client):
    product, order = await purchase(client)
    serial = 'SN-' + uuid4().hex
    body = {'request_key': str(uuid4()), 'lines': [{'line_id': order['lines'][0]['id'], 'quantity': 1, 'serials': [serial]}]}
    path = f"/inventory/purchases/{order['id']}/receive"
    receipt = await post(client, path, body)
    assert (await post(client, path, body))['id'] == receipt['id']
    changed = {**body, 'lines': [{**body['lines'][0], 'quantity': 2, 'serials': [serial, 'another']}]}
    assert (await client.post('/api/v1' + path, json=changed)).status_code == 409
    duplicate = {**body, 'request_key': str(uuid4())}
    assert (await client.post('/api/v1' + path, json=duplicate)).status_code == 409
    final = {**duplicate, 'lines': [{**body['lines'][0], 'serials': ['SN-' + uuid4().hex]}]}
    await post(client, path, final)
    detail = (await client.get(f"/api/v1/inventory/purchases/{order['id']}")).json()
    assert detail['status'] == 'RECEIVED' and detail['lines'][0]['received_quantity'] == 2
    stock = (await client.get('/api/v1/inventory/stock')).json()['items']
    assert next(s for s in stock if s['product_id'] == product['id'])['available'] == 2
    movements = (await client.get('/api/v1/inventory/movements', params={'product_id': product['id']})).json()['items']
    assert len(movements) == 2 and sum(m['quantity'] for m in movements) == 2


async def test_inventory_permissions_and_cross_store(client):
    import os
    from app.core.db import session_scope
    from app.modules.auth.models import Store
    from app.modules.inventory.models import Supplier
    async with session_scope() as db:
        store = Store(name='隔离检查门店'); db.add(store); await db.flush()
        supplier = Supplier(store_id=store.id, name='其他门店', contact=''); db.add(supplier); await db.commit()
        supplier_id = str(supplier.id)
    r = await client.post('/api/v1/inventory/purchases', json={'supplier_id': supplier_id, 'request_key': str(uuid4()), 'lines': [{'product_id': str(uuid4()), 'quantity': 1, 'unit_cost': '1.00'}]})
    assert r.status_code == 404
    r = await client.post('/api/v1/auth/login', json={'username': 'staff', 'password': os.environ['DEMO_PASSWORD']})
    client.headers['X-CSRF-Token'] = r.json()['csrf_token']
    assert (await client.post('/api/v1/inventory/suppliers', json={'name': '越权', 'contact': ''})).status_code == 403
