from datetime import UTC, datetime, timedelta
from uuid import uuid4
from test_phase2_inventory import post
from test_phase2_sales import sale
from test_acceptance import prepare


async def test_cancel_unshipped_releases_only_selected_reservations(client):
    order, product, _ = await sale(client, quantity=2, stock_quantity=2)
    await post(client, f"/sales/orders/{order['id']}/confirm", {})
    await post(client, f"/sales/orders/{order['id']}/pay", {'method':'CASH'})
    case = await post(client, '/aftersales', {'request_key':str(uuid4()), 'order_id':order['id'], 'kind':'CANCEL_UNSHIPPED', 'reason':'客户减少一台',
        'lines':[{'line_id':order['lines'][0]['id'],'refund_amount':'199.90','return_quantity':1}]})
    assert (await client.post(f"/api/v1/sales/orders/{order['id']}/dispatch",json={})).status_code == 409
    await post(client, f"/aftersales/{case['id']}/review", {'decision':'APPROVE','note':'核实尚未交货'})
    await post(client, f"/aftersales/{case['id']}/refund", {})
    await post(client, f"/aftersales/{case['id']}/close", {'note':'退款成功且已释放预留'})
    await post(client, f"/sales/orders/{order['id']}/dispatch", {})
    stock = next(s for s in (await client.get('/api/v1/inventory/stock')).json()['items'] if s['product_id']==product['id'])
    assert (stock['quantity'],stock['reserved']) == (1,0)


async def test_installation_block_reschedule_does_not_issue_material_twice(client):
    order, product, _ = await sale(client, quantity=1, stock_quantity=3, tracking='QUANTITY')
    await post(client, f"/sales/orders/{order['id']}/confirm", {})
    await post(client, f"/sales/orders/{order['id']}/pay", {'method':'CARD'})
    await post(client, f"/sales/orders/{order['id']}/dispatch", {})
    appointment = (datetime.now(UTC)+timedelta(days=1)).isoformat()
    work = await post(client, '/installations', {'source_order_id':order['id'],'address':'模拟地址','appointment_at':appointment})
    installer = (await client.get('/api/v1/installations/installers')).json()['items'][0]['id']
    await post(client, f"/installations/{work['id']}/dispatch", {'installer_id':installer})
    for action in ('accept','collect','arrive'):
        await post(client, f"/installations/{work['id']}/transition", {'request_key':str(uuid4()),'action':action,'note':'模拟执行',
            'materials':[{'product_id':product['id'],'quantity':1}] if action=='collect' else []})
    blocked = await post(client, f"/installations/{work['id']}/issue", {'note':'现场无电，设备和耗材保管待复访'})
    assert blocked['status']=='BLOCKED'
    await post(client, f"/installations/{work['id']}/reschedule", {'appointment_at':appointment,'note':'客户恢复供电后复访'})
    await post(client, f"/installations/{work['id']}/dispatch", {'installer_id':installer,'note':'原人员继续保管领料'})
    for action in ('accept','collect'):
        await post(client, f"/installations/{work['id']}/transition", {'request_key':str(uuid4()),'action':action,'note':'复访使用原领料'})
    stock = next(s for s in (await client.get('/api/v1/inventory/stock')).json()['items'] if s['product_id']==product['id'])
    assert stock['quantity']==1
    cancelled = await post(client, f"/installations/{work['id']}/cancel", {'note':'客户取消，未使用耗材验收入库', 'materials_confirmed':True,
        'returned_materials':[{'product_id':product['id'],'quantity':1,'serials':[]}]})
    assert cancelled['status']=='CANCELLED'
    stock = next(s for s in (await client.get('/api/v1/inventory/stock')).json()['items'] if s['product_id']==product['id'])
    assert stock['quantity']==2


async def test_telecom_reversal_timeout_preserves_original_success(client, mock_account):
    external, uid, number = mock_account
    accepted,qid,_,_ = await prepare(client, number)
    result = await post(client, f"/acceptances/{accepted['acceptance_id']}/confirm", {'expected_version':1,'quality_check_id':qid})
    assert result['status']=='SUCCESS'
    body = {'request_key':str(uuid4()),'acceptance_id':accepted['acceptance_id'],'reason':'客户取消模拟套餐','scenario':'SUCCESS_TIMEOUT'}
    case = await post(client, '/reversals', body)
    await post(client, f"/reversals/{case['id']}/review", {'decision':'APPROVE','note':'核实套餐未再次变更'})
    unknown = await post(client, f"/reversals/{case['id']}/submit", {})
    assert unknown['status']=='UNKNOWN'
    done = await post(client, f"/reversals/{case['id']}/reconcile", {})
    assert done['status']=='SUCCESS' and done['external_request_id']==unknown['external_request_id']
    assert str(await external.fetchval('SELECT monthly_fee FROM boss.accounts WHERE id=$1',uid))=='129.00'
    assert await external.fetchval('SELECT status FROM boss.acceptances WHERE external_request_id=$1',__import__('uuid').UUID(result['external_request_id']))=='SUCCESS'
