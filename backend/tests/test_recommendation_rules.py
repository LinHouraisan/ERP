from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4


def policy(fee='89.00', broadband=True, once='0.00'):
    return SimpleNamespace(id=uuid4(), product_id=uuid4(), status='PUBLISHED', version=1,
        valid_from=date(2026,1,1), valid_to=date(2027,12,31), monthly_fee=Decimal(fee),
        one_time_fee=Decimal(once) if once else None, broadband=broadband, contract_months=12,
        promotion_months=12, conditions={'verified_required': True})


def facts():
    return {'monthly_fee': '129.00', 'broadband': True, 'contract_end': None, 'verified': True,
            'restrictions': [], 'is_new_customer': False, 'tenure_months': 24, 'discounts': []}


def test_recommendation_preserves_broadband_and_exact_known_difference():
    from app.modules.recommendations.rules import recommend
    from app.modules.recommendations.schemas import DemandProfile
    p89, p79 = policy(), policy('79.00', False)
    result = recommend(facts(), DemandProfile(intent='REDUCE_COST', must_keep=['broadband']), [p89, p79], date(2026,10,2))
    assert result['outcome'] == 'OPTIONS'
    assert len(result['candidates']) == 1
    assert result['candidates'][0]['monthly_difference'] == '40.00'
    assert result['candidates'][0]['contract_months'] == 12


def test_unknown_fees_contract_boundary_and_service_task():
    from app.modules.recommendations.rules import recommend
    from app.modules.recommendations.schemas import DemandProfile
    demand = DemandProfile(intent='REDUCE_COST', must_keep=['broadband'], issues=['网络故障'])
    result = recommend(facts(), demand, [policy(once=None)], date(2026,10,2))
    assert result['candidates'][0]['eligibility'] == 'unknown'
    assert result['candidates'][0]['one_time_fee'] is None
    assert result['service_tasks']
    f=facts(); f['contract_end']='2026-10-02'
    assert recommend(f,demand,[policy()],date(2026,10,2))['outcome']=='NEEDS_INFO'
    assert recommend(f,demand,[policy()],date(2026,10,3))['outcome']=='OPTIONS'
    f['monthly_fee']=None
    assert recommend(f,demand,[policy()],date(2026,10,3))['outcome']=='NEEDS_INFO'


def test_keep_current_and_no_matching_plan():
    from app.modules.recommendations.rules import recommend
    from app.modules.recommendations.schemas import DemandProfile
    assert recommend(facts(),DemandProfile(intent='KEEP_CURRENT'),[policy()],date(2026,10,2))['outcome']=='KEEP_CURRENT'
    assert recommend(facts(),DemandProfile(intent='REDUCE_COST',budget='30.00'),[policy()],date(2026,10,2))['outcome']=='NO_MATCH'


async def test_service_task_requires_progress_and_keeps_service_history(client):
    sid = (await client.post('/api/v1/service-sessions', json={'category':'FAULT'})).json()['service_id']
    task = (await client.post('/api/v1/service-tasks', json={
        'service_id':sid, 'title':'网络排障', 'owner_role':'STAFF',
    })).json()
    path = f"/api/v1/service-tasks/{task['id']}/transition"
    assert task['status'] == 'OPEN'
    assert (await client.post(path, json={'status':'CLOSED','note':'跳过处理'})).status_code == 409
    for state in ('IN_PROGRESS', 'CLOSED'):
        response = await client.post(path, json={'status':state,'note':'记录模拟处理结果'})
        assert response.status_code == 200 and response.json()['status'] == state
    detail = (await client.get(f'/api/v1/service-sessions/{sid}')).json()
    assert detail['status'] == 'ACTIVE'
    assert [e['detail']['to'] for e in detail['events'] if e['action']=='TASK_TRANSITION'] == ['IN_PROGRESS','CLOSED']
    other = (await client.post('/api/v1/service-tasks', json={
        'service_id':sid, 'title':'取消的咨询任务', 'owner_role':'MANAGER',
    })).json()
    cancelled = await client.post(f"/api/v1/service-tasks/{other['id']}/transition", json={'status':'CANCELLED','note':'客户取消咨询'})
    assert cancelled.status_code == 200 and cancelled.json()['status'] == 'CANCELLED'
