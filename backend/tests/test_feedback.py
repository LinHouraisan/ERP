from datetime import timedelta
from uuid import UUID
from sqlalchemy import update


async def ended_service(client):
    sid=(await client.post('/api/v1/service-sessions',json={'category':'OTHER'})).json()['service_id']
    await client.post(f'/api/v1/service-sessions/{sid}/finish',json={})
    r=await client.post(f'/api/v1/service-sessions/{sid}/feedback-link',json={})
    assert r.status_code==200, r.text
    return sid,r.json()['token']


async def test_feedback_is_once_per_service(client):
    sid,token=await ended_service(client)
    body={'token':token,'score':4,'tags':['解释清晰度'],'comment':'解释清楚'}
    first=await client.post('/api/v1/public/feedback',json=body)
    assert first.status_code==200, first.text
    second=await client.post('/api/v1/public/feedback',json=body)
    assert first.json()==second.json()
    assert (await client.post('/api/v1/public/feedback',json={**body,'score':1})).status_code==409
    assert (await client.post('/api/v1/public/feedback',json={**body,'score':0})).status_code==422


async def test_expired_token_rejected_and_unrated_service_is_not_zero(client):
    sid,token=await ended_service(client)
    from app.core.db import session_scope,utcnow
    from app.modules.feedback.models import FeedbackToken
    async with session_scope() as db:
        await db.execute(update(FeedbackToken).where(FeedbackToken.service_id==UUID(sid)).values(expires_at=utcnow()-timedelta(seconds=1)))
        await db.commit()
    assert (await client.post('/api/v1/public/feedback',json={'token':token,'score':5})).status_code==410
    detail=(await client.get(f'/api/v1/service-sessions/{sid}/feedback')).json()
    assert detail['feedback'] is None
