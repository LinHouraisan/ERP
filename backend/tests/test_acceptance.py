from uuid import uuid4, UUID


async def prepare(client, number):
    sid=(await client.post('/api/v1/service-sessions',json={'category':'PLAN'})).json()['service_id']
    snapshot=(await client.post(f'/api/v1/service-sessions/{sid}/account-query',json={'number':number})).json()
    demand={'snapshot_id':snapshot['snapshot_id'],'demand':{'intent':'REDUCE_COST','must_keep':['broadband']}}
    rec=(await client.post(f'/api/v1/service-sessions/{sid}/recommendations',json=demand)).json()
    candidate=next(c for c in rec['candidates'] if c['monthly_fee']=='89.00')
    quality=(await client.post(f"/api/v1/recommendations/{rec['recommendation_id']}/quality-checks",json={'candidate_id':candidate['candidate_id']})).json()
    qid=quality['quality_check_id']
    assert (await client.post(f'/api/v1/quality-checks/{qid}/reviews',json={'decision':'CONFIRM','reason':'核对费用合约和宽带'})).status_code==200
    r=await client.post('/api/v1/acceptances',json={'recommendation_id':rec['recommendation_id'],'candidate_id':candidate['candidate_id']},headers={'Idempotency-Key':str(uuid4())})
    assert r.status_code==201, r.text
    return r.json(),qid,sid,demand


async def test_success_timeout_reconcile_one_order(client,mock_account):
    db,uid,number=mock_account
    await db.execute("UPDATE boss.accounts SET scenario='SUCCESS_TIMEOUT' WHERE id=$1",uid)
    acceptance,qid,sid,demand=await prepare(client,number)
    body={'expected_version':acceptance['expected_version'],'quality_check_id':qid}
    r=await client.post(f"/api/v1/acceptances/{acceptance['acceptance_id']}/confirm",json=body)
    assert r.status_code==202, r.text
    assert r.json()['status']=='UNKNOWN'
    result=(await client.post(f"/api/v1/acceptances/{acceptance['acceptance_id']}/reconcile",json={})).json()
    assert result['status']=='SUCCESS', result
    assert result['external_request_id']==acceptance['external_request_id']
    assert await db.fetchval('SELECT count(*) FROM boss.acceptances WHERE external_request_id=$1',UUID(result['external_request_id']))==1
    assert (await client.post(f'/api/v1/service-sessions/{sid}/account-query',json={'number':number})).json()['payload']['monthly_fee']=='89.00'
    history=(await client.get(f'/api/v1/service-sessions/{sid}')).json()['snapshots']
    assert history[0]['payload']['monthly_fee']=='129.00'


async def test_stale_confirmation_rejected(client,mock_account):
    _,_,number=mock_account
    acceptance,qid,sid,demand=await prepare(client,number)
    await client.post(f'/api/v1/service-sessions/{sid}/recommendations',json=demand)
    r=await client.post(f"/api/v1/acceptances/{acceptance['acceptance_id']}/confirm",json={'expected_version':1,'quality_check_id':qid})
    assert r.status_code==409
    assert r.json()['code']=='STALE_RECOMMENDATION'


async def test_late_failure_cannot_overwrite_success(client,mock_account):
    _,_,number=mock_account
    acceptance,qid,_,_=await prepare(client,number)
    success=(await client.post(f"/api/v1/acceptances/{acceptance['acceptance_id']}/confirm",json={'expected_version':1,'quality_check_id':qid})).json()
    assert success['status']=='SUCCESS', success
    from app.core.db import session_scope
    from app.modules.acceptances.service import merge_result
    from app.modules.auth.schemas import CurrentUser
    actor=CurrentUser.model_validate((await client.get('/api/v1/auth/me')).json())
    async with session_scope() as db:
        row=await merge_result(db,actor,UUID(acceptance['acceptance_id']),{'status':'FAILED','external_request_id':acceptance['external_request_id'],'external_order_id':success['external_order_id']})
        assert row.status=='SUCCESS'


async def test_interrupted_submit_recovered_and_ended_service_idempotent(client,mock_account):
    _,_,number=mock_account
    acceptance,qid,sid,_=await prepare(client,number)
    from app.core.db import session_scope
    from app.modules.acceptances.service import prepare_confirmation
    from app.modules.acceptances.schemas import Confirmation
    from app.modules.auth.schemas import CurrentUser
    actor=CurrentUser.model_validate((await client.get('/api/v1/auth/me')).json())
    async with session_scope() as db:
        prepared=await prepare_confirmation(db,actor,UUID(acceptance['acceptance_id']),Confirmation(expected_version=1,quality_check_id=qid))
        assert prepared.status=='SUBMITTING'
    # A fresh request/session simulates recovery after the preparing process exits.
    recovered=(await client.post(f"/api/v1/acceptances/{acceptance['acceptance_id']}/reconcile",json={})).json()
    assert recovered['status']=='SUCCESS',recovered
    await client.post(f'/api/v1/service-sessions/{sid}/finish',json={})
    duplicate=await client.post('/api/v1/acceptances',json={'recommendation_id':acceptance['recommendation_id'],'candidate_id':acceptance['candidate_id']},headers={'Idempotency-Key':str(uuid4())})
    assert duplicate.status_code==201,duplicate.text
    assert duplicate.json()['acceptance_id']==acceptance['acceptance_id']
