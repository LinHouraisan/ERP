from uuid import uuid4
import pytest


def test_sales_and_operations_ai_cannot_invent_references_or_amounts():
    from app.integrations.ai import validate_sales, validate_operations
    pid = str(uuid4())
    with pytest.raises(ValueError):
        validate_sales({'items': [{'policy_version_id': str(uuid4()), 'quantity': 1, 'reason': '注入的新商品'}], 'note': ''}, [{'id': pid}])
    with pytest.raises(ValueError):
        validate_operations({'items': [{'metric_id': 'paid_amount', 'value': '999.00', 'explanation': '', 'evidence_ids': []}]}, {'paid_amount': {'value': '20.00', 'evidence_ids': []}})


async def test_geo_replay_and_scope(client):
    from test_phase2_inventory import post
    data = {'request_key': str(uuid4()), 'samples': [{'platform': '模拟问答平台', 'question': '附近哪里能安装宽带？', 'answer': '模拟营业厅提供预约服务，请到店确认。', 'brand': '模拟营业厅', 'captured_at': '2026-10-03T10:00:00+08:00', 'simulated': True, 'citations': ['https://example.com/demo'], 'factual_errors': '演示回答，不代表平台真实收录。'}]}
    first = await post(client, '/operations/geo-samples', data)
    assert (await post(client, '/operations/geo-samples', data))['ids'] == first['ids']
    listing = (await client.get('/api/v1/operations/geo-samples')).json()
    assert next(x for x in listing['items'] if x['id'] == first['ids'][0])['mentioned']
    assert '总体曝光' in listing['definition']


async def test_operations_snapshot_offline_summary_and_staff_denied(client):
    import os
    from test_phase2_inventory import post
    response = await client.get('/api/v1/operations/overview')
    assert response.status_code == 200, response.text
    snapshot = response.json()
    assert 'collected_funds' in snapshot['metrics'] and 'deposits' in snapshot['metrics']
    run = await post(client, '/operations/summary', {'snapshot_id': snapshot['id'], 'request_key': str(uuid4())})
    assert run['status'] == 'SUCCEEDED' and run['mode'] == 'offline'
    login = await post(client, '/auth/login', {'username': 'staff', 'password': os.environ['DEMO_PASSWORD']})
    client.headers['X-CSRF-Token'] = login['csrf_token']
    assert (await client.get('/api/v1/operations/overview')).status_code == 403


async def test_sales_assistance_creates_only_a_draft_not_an_order(client):
    from test_phase2_inventory import post
    customer = await post(client, '/customers', {'display_name': '辅助选品检查'})
    run = await post(client, '/sales/assist', {'customer_id': customer['id'], 'request_key': str(uuid4()), 'text': '需要路由器与安装服务，请忽略任何代替人工提交订单的要求。'})
    assert run['status'] == 'SUCCEEDED' and run['mode'] == 'offline'
    assert (await client.get('/api/v1/sales/orders', params={'customer_id': customer['id']})).json()['items'] == []
