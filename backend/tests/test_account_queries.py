async def test_missing_fee_stays_unknown_and_query_history_keeps_snapshot(client):
    response = await client.post('/api/v1/service-sessions', json={'category': 'PLAN'})
    assert response.status_code == 201, response.text
    sid = response.json()['service_id']
    snapshots = []
    for _ in range(2):
        r = await client.post(f'/api/v1/service-sessions/{sid}/account-query', json={'number': '19900000004', 'account_type': 'MOBILE'})
        assert r.status_code == 200, r.text
        s = r.json()
        assert s['payload']['monthly_fee'] is None
        assert s['completeness'] == 'PARTIAL'
        assert s['source_time'] and s['fetched_at']
        snapshots.append(s['snapshot_id'])
    assert snapshots[0] != snapshots[1]
    detail = (await client.get(f'/api/v1/service-sessions/{sid}')).json()
    assert len(detail['snapshots']) == 2


async def test_missing_account_and_timeout_are_distinct(client):
    sid = (await client.post('/api/v1/service-sessions', json={'category': 'PLAN'})).json()['service_id']
    missing = await client.post(f'/api/v1/service-sessions/{sid}/account-query', json={'number': '19999999999', 'account_type': 'MOBILE'})
    assert missing.status_code == 200
    assert missing.json()['status'] == 'NOT_FOUND'
    failed = await client.post(f'/api/v1/service-sessions/{sid}/account-query', json={'number': '19900000012', 'account_type': 'MOBILE'})
    assert failed.status_code == 504
    assert failed.json()['code'] == 'BOSS_TIMEOUT'
