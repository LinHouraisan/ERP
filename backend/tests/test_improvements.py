from datetime import UTC, datetime, timedelta
from uuid import uuid4


def test_empty_feedback_has_no_average_and_metrics_show_denominators():
    from app.modules.improvements.service import metric_values
    result=metric_values([],[],[],[],[])
    assert result['satisfaction']['average'] is None
    assert result['participation']=={'numerator':0,'denominator':0,'value':None}
    assert result['quality_problem_rate']['value'] is None
    assert result['waiting']['p50_seconds'] is None


async def test_close_requires_verification(client):
    r=await client.get('/api/v1/service-metrics')
    assert r.status_code==200, r.text
    snapshot=r.json()
    proposal=await client.post('/api/v1/improvement-proposals',json={'snapshot_id':snapshot['snapshot_id'],'request_key':str(uuid4())})
    assert proposal.status_code==201, proposal.text
    tid=proposal.json()['id']
    assert (await client.post(f'/api/v1/improvement-tasks/{tid}/transition',json={'status':'CLOSED','reason':'未验证就关闭'})).status_code==409
    owner=(await client.get('/api/v1/auth/me')).json()['user_id']
    for data in [
        {'status':'APPROVED','reason':'核对样本后审核','owner_id':owner,'plan':'增加费用核查步骤','target':'减少遗漏'},
        {'status':'IN_PROGRESS','reason':'已开始执行'},
    ]:
        r=await client.post(f'/api/v1/improvement-tasks/{tid}/transition',json=data)
        assert r.status_code==200,r.text
    assert (await client.post(f'/api/v1/improvement-tasks/{tid}/transition',json={'status':'VERIFIED','reason':'缺少证据'})).status_code==422
    after=(await client.get('/api/v1/service-metrics')).json()
    r=await client.post(f'/api/v1/improvement-tasks/{tid}/transition',json={'status':'VERIFIED','reason':'完成对照','verification':{'before_snapshot_id':snapshot['snapshot_id'],'after_snapshot_id':after['snapshot_id'],'conditions_changed':'同一模拟环境','result':'样本不足，不判断效果','unresolved_issues':'等待更多数据'}})
    assert r.status_code==200,r.text
    assert (await client.post(f'/api/v1/improvement-tasks/{tid}/transition',json={'status':'CLOSED','reason':'验证记录已留存'})).status_code==200
    assert len((await client.get(f'/api/v1/improvement-tasks/{tid}')).json()['events'])==4
