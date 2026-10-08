from decimal import Decimal
from uuid import uuid4
import pytest
from pydantic import ValidationError


def test_unknown_candidate_rejected_and_prices_checked():
    from app.integrations.ai import validate_explanation
    candidate = {'candidate_id': str(uuid4()), 'monthly_fee': '89.00', 'one_time_fee': '0.00', 'contract_months': 12, 'evidence_ids': [str(uuid4())]}
    answer = {'items': [{**candidate, 'candidate_id': str(uuid4()), 'text': '方案说明'}]}
    with pytest.raises(ValueError): validate_explanation(answer, [candidate])
    answer['items'][0]['candidate_id'] = candidate['candidate_id']
    answer['items'][0]['monthly_fee'] = '59.00'
    with pytest.raises(ValueError): validate_explanation(answer, [candidate])


def test_prompt_injection_cannot_write():
    from app.integrations.ai import Explanation
    with pytest.raises(ValidationError):
        Explanation.model_validate({'items': [], 'sql': 'DROP TABLE app.users', 'acceptance_status': 'SUCCESS'})


async def test_ai_failure_keeps_manual_flow():
    from app.integrations.ai import generate
    result, usage, model = await generate('explanation', {'candidates': []}, '只返回 JSON', mode='offline')
    assert result == {'items': []}
    assert usage is None
    assert model == 'offline-fixture'


async def test_service_task_close_requires_note(client):
    sid = (await client.post('/api/v1/service-sessions', json={'category': 'FAULT'})).json()['service_id']
    r = await client.post('/api/v1/service-tasks', json={'service_id': sid, 'title': '网络排障', 'owner_role': 'STAFF'})
    assert r.status_code == 201, r.text
    tid = r.json()['id']
    assert (await client.post(f'/api/v1/service-tasks/{tid}/transition', json={'status': 'CLOSED', 'note': ''})).status_code == 422
    assert (await client.post(f'/api/v1/service-tasks/{tid}/transition', json={'status': 'IN_PROGRESS', 'note': '开始检查'})).status_code == 200
    r = await client.post(f'/api/v1/service-tasks/{tid}/transition', json={'status': 'CLOSED', 'note': '已记录排查结果，客户恢复使用'})
    assert r.status_code == 200


async def test_ai_failure_is_persisted_and_manual_query_still_works(client, monkeypatch):
    from app.integrations import ai
    async def unavailable(*args, **kwargs):
        raise TimeoutError('simulated outage')
    monkeypatch.setattr(ai, 'generate', unavailable)
    sid = (await client.post('/api/v1/service-sessions', json={'category': 'PLAN'})).json()['service_id']
    response = await client.post(f'/api/v1/service-sessions/{sid}/analyze', json={'request_key': str(uuid4()), 'text': '降费'})
    assert response.status_code == 200, response.text
    run = response.json()
    assert run['status'] == 'FAILED'
    assert (await client.get(f"/api/v1/ai-runs/{run['id']}")).json()['status'] == 'FAILED'
    assert (await client.post(f'/api/v1/service-sessions/{sid}/account-query', json={'number': '19900000001'})).status_code == 200


async def test_deepseek_adapter_contract_without_network(monkeypatch):
    from types import SimpleNamespace
    import langchain_deepseek
    from app.integrations.ai import generate
    monkeypatch.setenv('DEEPSEEK_API_KEY','offline-contract-test')
    calls=[]
    class FakeModel:
        def __init__(self,**kwargs):
            assert kwargs['api_base']=='https://api.deepseek.com'
            assert kwargs['max_retries']==0 and kwargs['temperature']==0
            assert kwargs['extra_body']=={'thinking':{'type':'disabled'}}
        def bind(self,**kwargs):
            assert kwargs['response_format']=={'type':'json_object'}
            return self
        async def ainvoke(self,messages,**kwargs):
            calls.append(list(messages))
            return SimpleNamespace(content='not-json' if len(calls)==1 else '{"complete":true,"findings":[]}',usage_metadata={'input_tokens':10,'output_tokens':5,'total_tokens':15},response_metadata={'model_name':'test-deepseek'})
    monkeypatch.setattr(langchain_deepseek,'ChatDeepSeek',FakeModel)
    output,usage,model=await generate('quality',{'structured':True},'固定提示词',mode='deepseek')
    assert output=={'complete':True,'findings':[]}
    assert usage=={'input_tokens':20,'output_tokens':10,'total_tokens':30} and model=='test-deepseek'
    assert len(calls)==2


async def test_invalid_model_content_keeps_reported_usage(client,monkeypatch):
    from app.integrations import ai
    async def invalid(*args,**kwargs):return {'intent':'NOT_AN_INTENT'},{'input_tokens':10,'output_tokens':5,'total_tokens':15},'fake-model'
    monkeypatch.setattr(ai,'generate',invalid)
    sid=(await client.post('/api/v1/service-sessions',json={'category':'PLAN'})).json()['service_id']
    run=(await client.post(f'/api/v1/service-sessions/{sid}/analyze',json={'request_key':str(uuid4()),'text':'模拟需求'})).json()
    assert run['status']=='FAILED'
    assert run['usage']=={'input_tokens':10,'output_tokens':5,'total_tokens':15}
