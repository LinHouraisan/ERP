import asyncio
from uuid import uuid4
from test_phase2_inventory import post, purchase


async def sale(client, quantity=1, stock_quantity=2, tracking='SERIAL'):
    product, po = await purchase(client, tracking, stock_quantity)
    serials = ['SN-' + uuid4().hex for _ in range(stock_quantity)] if tracking == 'SERIAL' else []
    await post(client, f"/inventory/purchases/{po['id']}/receive", {'request_key': str(uuid4()), 'lines': [{'line_id': po['lines'][0]['id'], 'quantity': stock_quantity, 'serials': serials}]})
    policy = await post(client, f"/products/{product['id']}/policy-versions", {'valid_from': '2026-01-01', 'valid_to': '2099-12-31', 'monthly_fee': '0.00', 'one_time_fee': '199.99', 'contract_months': 0, 'broadband': None, 'source': '模拟销售政策', 'conditions': {'verified_required': False, 'sale_discount': '0.09'}})
    await post(client, f"/policy-versions/{policy['id']}/publish", {})
    customer = await post(client, '/customers', {'display_name': '模拟购物客户', 'address': '演示市演示路 1 号'})
    body = {'request_key': str(uuid4()), 'customer_id': customer['id'], 'lines': [{'policy_version_id': policy['id'], 'quantity': quantity}]}
    order = await post(client, '/sales/orders', body)
    assert (await post(client, '/sales/orders', body))['id'] == order['id']
    return order, product, body


async def test_payment_unknown_reconcile_dispatch_once_and_money(client):
    order, product, _ = await sale(client, quantity=2)
    assert order['total'] == '399.80'
    await post(client, f"/sales/orders/{order['id']}/confirm", {})
    payment = await post(client, f"/sales/orders/{order['id']}/pay", {'method': 'WECHAT', 'scenario': 'SUCCESS_TIMEOUT'})
    assert payment['status'] == 'UNKNOWN'
    repeat = await post(client, f"/sales/orders/{order['id']}/pay", {'method': 'WECHAT', 'scenario': 'SUCCESS_TIMEOUT'})
    assert repeat['external_request_id'] == payment['external_request_id']
    assert (await client.post(f"/api/v1/sales/orders/{order['id']}/pay", json={'method': 'CASH'})).status_code == 409
    reconciled = await post(client, f"/sales/orders/{order['id']}/reconcile", {})
    assert reconciled['status'] == 'SUCCESS' and reconciled['external_request_id'] == payment['external_request_id']
    await post(client, f"/sales/orders/{order['id']}/dispatch", {})
    await post(client, f"/sales/orders/{order['id']}/dispatch", {})
    stock = (await client.get('/api/v1/inventory/stock')).json()['items']
    assert next(s for s in stock if s['product_id'] == product['id'])['quantity'] == 0
    serials = (await client.get('/api/v1/inventory/serials', params={'product_id': product['id']})).json()['items']
    assert len(serials) == 2 and all(s['status'] == 'SHIPPED' for s in serials)


async def test_two_payments_compete_for_last_item(client):
    order, _, body = await sale(client, stock_quantity=1)
    second = await post(client, '/sales/orders', {**body, 'request_key': str(uuid4())})
    for item in (order, second): await post(client, f"/sales/orders/{item['id']}/confirm", {})
    responses = await asyncio.gather(*(client.post(f"/api/v1/sales/orders/{x['id']}/pay", json={'method': 'CARD'}) for x in (order, second)))
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert next(r for r in responses if r.status_code == 200).json()['status'] == 'SUCCESS'
    assert next(r for r in responses if r.status_code == 409).json()['code'] == 'NO_STOCK'


async def test_changed_policy_requires_new_confirmation(client):
    order, product, _ = await sale(client)
    new = await post(client, f"/products/{product['id']}/policy-versions", {'valid_from': '2026-01-01', 'valid_to': '2099-12-31', 'monthly_fee': '0.00', 'one_time_fee': '209.00', 'contract_months': 0, 'broadband': None, 'source': '模拟新版', 'conditions': {'verified_required': False}})
    await post(client, f"/policy-versions/{new['id']}/publish", {})
    r = await client.post(f"/api/v1/sales/orders/{order['id']}/confirm", json={})
    assert r.status_code == 409 and r.json()['code'] == 'POLICY_CHANGED'


async def test_cashier_handover_claims_receipts_once(client):
    import os
    from app.core.db import session_scope
    from app.core.config import business_date
    from app.modules.auth.models import User
    from app.modules.auth.service import hash_password
    from app.seed import DEMO_STORE
    order, _, _ = await sale(client, stock_quantity=1)
    name = 'cashier-' + uuid4().hex[:12]
    async with session_scope() as db:
        user = User(store_id=DEMO_STORE, username=name, password_hash=hash_password(os.environ['DEMO_PASSWORD']), role='STAFF')
        db.add(user); await db.commit(); uid = str(user.id)
    login = await post(client, '/auth/login', {'username': name, 'password': os.environ['DEMO_PASSWORD']})
    client.headers['X-CSRF-Token'] = login['csrf_token']
    await post(client, f"/sales/orders/{order['id']}/confirm", {})
    await post(client, f"/sales/orders/{order['id']}/pay", {'method': 'CASH'})
    body = {'request_key': str(uuid4()), 'business_day': str(business_date()), 'cashier_id': uid, 'counted_cash': '199.00'}
    closing = await post(client, '/sales/day-closes', body)
    assert closing['difference'] == '-0.90' and closing['totals']['methods']['CASH'] == '199.90'
    detail = next(c for c in (await client.get('/api/v1/sales/day-closes')).json()['items'] if c['id'] == closing['id'])
    assert detail['payments'][0]['order_id'] == order['id'] and detail['payments'][0]['amount'] == '199.90'
    assert (await post(client, '/sales/day-closes', body))['id'] == closing['id']
    assert (await client.post('/api/v1/sales/day-closes', json={**body, 'request_key': str(uuid4())})).status_code == 409
