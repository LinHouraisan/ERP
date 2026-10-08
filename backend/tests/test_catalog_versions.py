from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select, func, update
from sqlalchemy.exc import DBAPIError


async def test_published_policy_is_immutable():
    from app.seed import seed_demo, DEMO_STORE
    from app.modules.catalog.models import PolicyVersion
    from app.core.db import session_scope
    await seed_demo()
    async with session_scope() as db:
        policy = await db.scalar(select(PolicyVersion).where(PolicyVersion.store_id == DEMO_STORE))
        with pytest.raises(DBAPIError):
            await db.execute(update(PolicyVersion).where(PolicyVersion.id == policy.id).values(monthly_fee=Decimal('1.00')))
            await db.commit()


async def test_seed_is_idempotent_and_policy_date_boundaries():
    from app.seed import seed_demo, DEMO_STORE
    from app.modules.catalog.models import Product, PolicyVersion
    from app.modules.services.models import ServiceSession
    from app.modules.catalog.service import effective
    from app.core.db import session_scope
    await seed_demo()
    await seed_demo()
    async with session_scope() as db:
        from app.seed import seed_id, PRODUCTS
        assert await db.scalar(select(func.count()).select_from(Product).where(Product.id.in_([seed_id(f'product-{i}') for i in range(len(PRODUCTS))]))) == 8
        assert await db.scalar(select(func.count()).select_from(ServiceSession).where(ServiceSession.store_id == DEMO_STORE, ServiceSession.preset.is_(True))) == 20
        p = await db.scalar(select(PolicyVersion).where(PolicyVersion.store_id == DEMO_STORE))
        assert effective(p, p.valid_from)
        assert effective(p, p.valid_to)
        assert not effective(p, date(2030, 1, 1))


async def test_future_version_does_not_hide_current_policy(client,mock_account):
    from app.seed import seed_id,DEMO_STORE
    from app.modules.catalog.models import PolicyVersion
    from app.core.db import session_scope
    _,_,number=mock_account
    async with session_scope() as db:
        p=await db.get(PolicyVersion,seed_id('policy-1-1'))
        version=(await db.scalar(select(func.max(PolicyVersion.version)).where(PolicyVersion.product_id==p.product_id)))+1
        db.add(PolicyVersion(store_id=DEMO_STORE,product_id=p.product_id,version=version,status='PUBLISHED',valid_from=date(2099,1,1),valid_to=date(2099,12,31),monthly_fee=Decimal('88.00'),one_time_fee=Decimal('0.00'),contract_months=12,promotion_months=12,broadband=True,conditions=p.conditions,source='仅专用测试库的未来版本'))
        await db.commit()
    sid=(await client.post('/api/v1/service-sessions',json={'category':'PLAN'})).json()['service_id']
    snapshot=(await client.post(f'/api/v1/service-sessions/{sid}/account-query',json={'number':number})).json()
    rec=(await client.post(f'/api/v1/service-sessions/{sid}/recommendations',json={'snapshot_id':snapshot['snapshot_id'],'demand':{'intent':'REDUCE_COST','must_keep':['broadband']}})).json()
    assert any(c['policy_version_id']==str(seed_id('policy-1-1')) for c in rec['candidates'])
