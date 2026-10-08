from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from app.core.config import business_date
from app.core.digests import content_hash
from app.core.errors import DomainError
from app.core.security import owned
from app.modules.accounts.models import AccountSnapshot
from app.modules.catalog.models import PolicyVersion, Product
from app.modules.recommendations.models import Recommendation, PromptVersion
from app.modules.recommendations.rules import RULE_VERSION, recommend
from app.modules.services.models import ServiceSession
from app.modules.services.service import require_active, event
from app.modules.auth.models import Store


async def create(db, user, sid, data):
    service = await owned(db, ServiceSession, sid, user, lock=True)
    require_active(service)
    snapshot = await owned(db, AccountSnapshot, data.snapshot_id, user)
    if snapshot.service_id != sid:
        raise DomainError('SNAPSHOT_MISMATCH', '请选择本次接待的查询快照')
    day = business_date()
    policies = (await db.scalars(select(PolicyVersion).join(Product, Product.id == PolicyVersion.product_id).where(
        PolicyVersion.store_id == user.store_id, PolicyVersion.status == 'PUBLISHED', PolicyVersion.valid_from <= day,
        PolicyVersion.valid_to >= day, Product.kind == 'PACKAGE').ext(distinct_on(PolicyVersion.product_id)).order_by(PolicyVersion.product_id, PolicyVersion.version.desc()))).all()
    previous = await db.scalar(select(Recommendation).where(Recommendation.service_id == sid).order_by(Recommendation.revision.desc()).limit(1))
    store = await db.get(Store, user.store_id)
    policies = [p for p in policies if not p.conditions.get('region') or p.conditions['region'] == store.region]
    result = recommend(snapshot.payload, data.demand, policies, day)
    prompt = await db.scalar(select(PromptVersion).where(PromptVersion.store_id == user.store_id, PromptVersion.scenario == 'explanation', PromptVersion.status == 'PUBLISHED').order_by(PromptVersion.version.desc()).limit(1))
    values = {'snapshot_id': snapshot.id, 'prompt_version_id': prompt.id if prompt else None, 'demand': data.demand.model_dump(mode='json'), 'rule_version': RULE_VERSION, **result}
    row = Recommendation(store_id=user.store_id, service_id=sid, revision=previous.revision+1 if previous else 1,
        supersedes_id=previous.id if previous else None, input_hash=content_hash(values), **values)
    db.add(row); await db.flush()
    event(db, user, sid, 'RECOMMENDED', {'recommendation_id': str(row.id), 'revision': row.revision})
    await db.commit()
    return row
