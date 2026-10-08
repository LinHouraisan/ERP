from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
import pytest


def evidence():
    return SimpleNamespace(id=uuid4(), status='PUBLISHED', monthly_fee=Decimal('89.00'), one_time_fee=Decimal('0.00'),
        contract_months=12, promotion_months=12, valid_from=date(2026,1,1), valid_to=date(2027,12,31))


def test_price_mismatch_blocked_and_contract_omission_found():
    from app.modules.quality.rules import check_text
    p = evidence()
    status, findings = check_text('月费59元，合约12个月。', [p], date(2026,10,2))
    assert status == 'BLOCKED'
    assert any(f['rule_id']=='PRICE_MISMATCH' for f in findings)
    status, findings = check_text('月费89元，一次费0元。', [p], date(2026,10,2))
    assert any(f['rule_id']=='CONTRACT_OMISSION' for f in findings)


def test_incomplete_extraction_needs_review():
    from app.modules.quality.rules import check_text
    status, findings = check_text('这个方案总体比较适合您。', [], date(2026,10,2))
    assert status == 'NEEDS_REVIEW'
    assert findings


def test_expired_policy_blocks_text():
    from app.modules.quality.rules import check_text
    p = evidence()
    status, findings = check_text('月费89元，合约12个月。', [p], date(2028,1,1))
    assert status == 'BLOCKED'
    assert any(f['rule_id'] == 'EXPIRED_POLICY' and f['evidence_ids'] == [str(p.id)] for f in findings)


@pytest.mark.parametrize('target_type', ['MARKETING', 'REPLY'])
async def test_text_revision_keeps_original_and_cannot_bypass_block(client, target_type):
    from app.seed import seed_id
    original = (await client.post('/api/v1/quality-checks', json={
        'target_type': target_type, 'text': '月费59元，合约12个月。',
        'policy_version_ids': [str(seed_id('policy-1-1'))],
    })).json()
    qid = original['quality_check_id']
    assert original['status'] == 'BLOCKED'
    assert (await client.post(f'/api/v1/quality-checks/{qid}/reviews', json={
        'decision': 'CONFIRM', 'reason': '尝试跳过错误',
    })).status_code == 409
    revision = await client.post(f'/api/v1/quality-checks/{qid}/reviews', json={
        'decision': 'REVISE', 'reason': '按政策修正', 'revised_text': '月费89元，合约12个月。',
    })
    assert revision.status_code == 200, revision.text
    revised = (await client.get('/api/v1/quality-checks/' + revision.json()['revised_quality_check_id'])).json()
    assert revised['supersedes_id'] == qid and revised['status'] == 'NEEDS_REVIEW'
    assert (await client.get(f'/api/v1/quality-checks/{qid}')).json()['text'] == original['text']


async def test_revision_invalidates_confirmation(client):
    sid = (await client.post('/api/v1/service-sessions',json={'category':'PLAN'})).json()['service_id']
    snapshot = (await client.post(f'/api/v1/service-sessions/{sid}/account-query',json={'number':'19900000001'})).json()
    body = {'snapshot_id':snapshot['snapshot_id'],'demand':{'intent':'REDUCE_COST','must_keep':['broadband']}}
    r=await client.post(f'/api/v1/service-sessions/{sid}/recommendations',json=body)
    assert r.status_code==201, r.text
    rec=r.json(); candidate=next(c for c in rec['candidates'] if c['monthly_fee']=='89.00')
    q=await client.post(f"/api/v1/recommendations/{rec['recommendation_id']}/quality-checks",json={'candidate_id':candidate['candidate_id']})
    assert q.status_code==201, q.text
    qid=q.json()['quality_check_id']
    assert q.json()['status']=='PASS', q.text
    assert (await client.post(f'/api/v1/quality-checks/{qid}/reviews',json={'decision':'CONFIRM','reason':'已核对金额、宽带和合约'})).status_code==200
    await client.post(f'/api/v1/service-sessions/{sid}/recommendations',json=body)
    assert (await client.post(f'/api/v1/quality-checks/{qid}/reviews',json={'decision':'CONFIRM','reason':'重用旧确认'})).status_code==409
