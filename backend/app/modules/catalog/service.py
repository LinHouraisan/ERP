from sqlalchemy import func, select

from app.core.errors import DomainError
from app.core.security import owned, require_role
from app.modules.catalog.models import PolicyVersion, Product


def effective(policy, day):
    return policy.status == 'PUBLISHED' and policy.valid_from <= day <= policy.valid_to


async def create_policy(db, user, product_id, data):
    require_role(user, 'ADMIN')
    await owned(db, Product, product_id, user, lock=True)
    version = (await db.scalar(select(func.max(PolicyVersion.version)).where(PolicyVersion.product_id == product_id)) or 0) + 1
    policy = PolicyVersion(store_id=user.store_id, product_id=product_id, version=version, **{**data.model_dump(), 'conditions': data.conditions.model_dump(mode='json')})
    db.add(policy)
    await db.commit()
    return policy


async def publish(db, user, policy_id):
    require_role(user, 'ADMIN')
    policy = await owned(db, PolicyVersion, policy_id, user, lock=True)
    if policy.status != 'PUBLISHED':
        policy.status = 'PUBLISHED'
        await db.commit()
    return policy


async def edit_policy(db, user, policy_id, data):
    require_role(user, 'ADMIN')
    policy = await owned(db, PolicyVersion, policy_id, user, lock=True)
    if policy.status == 'PUBLISHED':
        raise DomainError('IMMUTABLE_VERSION', '已发布政策不可覆盖，请新建版本')
    for key, value in {**data.model_dump(), 'conditions': data.conditions.model_dump(mode='json')}.items():
        setattr(policy, key, value)
    await db.commit()
    return policy
