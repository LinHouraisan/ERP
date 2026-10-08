import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from test_phase2_inventory import post
from test_phase2_sales import sale


async def test_installation_ownership_materials_completion_and_replay(client):
    order, _, _ = await sale(client, stock_quantity=1)
    await post(client, f"/sales/orders/{order['id']}/confirm", {})
    await post(client, f"/sales/orders/{order['id']}/pay", {'method': 'CASH'})
    appointment = (datetime.now(UTC)+timedelta(hours=2)).isoformat()
    work = await post(client, '/installations', {'source_order_id': order['id'], 'address': '模拟地址', 'appointment_at': appointment})
    from app.seed import seed_id
    from app.core.db import session_scope
    from app.modules.auth.models import User
    async with session_scope() as db:
        owner = await db.get(User, seed_id('INSTALLER'))
    await post(client, f"/installations/{work['id']}/dispatch", {'installer_id': str(owner.id)})
    # Staff cannot impersonate the installer.
    login = await post(client, '/auth/login', {'username': 'staff', 'password': os.environ['DEMO_PASSWORD']})
    client.headers['X-CSRF-Token'] = login['csrf_token']
    assert (await client.post(f"/api/v1/installations/{work['id']}/transition", json={'request_key': str(uuid4()), 'action': 'accept', 'note': '冒领'})).status_code == 403
    login = await post(client, '/auth/login', {'username': 'installer', 'password': os.environ['DEMO_PASSWORD']})
    client.headers['X-CSRF-Token'] = login['csrf_token']
    await post(client, f"/installations/{work['id']}/transition", {'request_key': str(uuid4()), 'action': 'accept', 'note': '模拟接单'})
    collect = {'request_key': str(uuid4()), 'action': 'collect', 'note': '领取销售设备'}
    assert (await client.post(f"/api/v1/installations/{work['id']}/transition", json=collect)).status_code == 409
    login = await post(client, '/auth/login', {'username': 'admin', 'password': os.environ['DEMO_PASSWORD']})
    client.headers['X-CSRF-Token'] = login['csrf_token']
    await post(client, f"/sales/orders/{order['id']}/dispatch", {})
    work = await post(client, f"/installations/{work['id']}/transition", collect)
    assert work['materials'][0]['serials']
    for action in ('arrive', 'install'):
        await post(client, f"/installations/{work['id']}/transition", {'request_key': str(uuid4()), 'action': action, 'note': '模拟现场记录'})
    body = {'request_key': str(uuid4()), 'action': 'complete', 'note': '模拟客户现场验收，非真实签名', 'customer_accepted': True}
    assert (await post(client, f"/installations/{work['id']}/transition", body))['status'] == 'COMPLETED'
    assert (await post(client, f"/installations/{work['id']}/transition", body))['status'] == 'COMPLETED'
    changed = {**body, 'note': '改变验收内容'}
    assert (await client.post(f"/api/v1/installations/{work['id']}/transition", json=changed)).status_code == 409


async def test_earnings_bill_matching_and_commission_gate(client):
    order, _, _ = await sale(client, stock_quantity=1)
    await post(client, f"/sales/orders/{order['id']}/confirm", {})
    await post(client, f"/sales/orders/{order['id']}/pay", {'method': 'CARD'})
    await post(client, f"/sales/orders/{order['id']}/dispatch", {})
    rule = await post(client, '/finance/rules', {'business_type': 'SALE', 'valid_from': '2026-01-01', 'valid_to': '2099-12-31', 'fixed_amount': '0.00', 'rate': '0.10', 'employee_rate': '0.20', 'settlement_condition': 'BILL_MATCHED'})
    await post(client, f"/finance/rules/{rule['id']}/publish", {})
    entry = await post(client, '/finance/accruals', {'source_type': 'SALE', 'source_id': order['id']})
    assert entry['expected_amount'] == '19.99' and entry['commission_amount'] == '4.00' and not entry['settleable']
    assert entry['actual_received'] is None and entry['current_due'] is None
    assert (await post(client, '/finance/accruals', {'source_type': 'SALE', 'source_id': order['id']}))['id'] == entry['id']
    bill = {'request_key': str(uuid4()), 'period': entry['period'], 'source': '人工录入模拟账单', 'rows': [{'business_no': entry['business_no'], 'amount': '19.99', 'received_amount': '19.99'}, {'business_no': 'UNKNOWN-'+str(uuid4()), 'amount': '20.00', 'received_amount': None}]}
    batch = await post(client, '/finance/bills', bill)
    assert next(r for r in batch['items'] if r['business_no'].startswith('UNKNOWN-'))['received_amount'] is None
    assert (await post(client, '/finance/bills', bill))['id'] == batch['id']
    entries = (await client.get('/api/v1/finance/earnings')).json()['items']
    refreshed = next(e for e in entries if e['id'] == entry['id'])
    assert refreshed['match_status'] == 'MATCHED' and refreshed['actual_received'] == '19.99' and refreshed['settleable']
    assert (await client.post('/api/v1/finance/bills', json={**bill, 'request_key': str(uuid4())})).status_code == 409
