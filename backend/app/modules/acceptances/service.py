from uuid import UUID, uuid4, uuid5
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from app.core.config import business_date
from app.core.db import utcnow
from app.core.digests import content_hash
from app.core.errors import DomainError
from app.core.security import owned
from app.integrations import boss
from app.modules.acceptances.models import Acceptance
from app.modules.accounts.models import AccountSnapshot, CustomerBusiness
from app.modules.catalog.models import PolicyVersion, Product
from app.modules.catalog.service import effective
from app.modules.quality.models import QualityCheck, QualityReview
from app.modules.quality.service import require_current
from app.modules.recommendations.models import Recommendation
from app.modules.recommendations.schemas import DemandProfile
from app.modules.recommendations.rules import recommend
from app.modules.services.models import ServiceSession
from app.modules.services.service import event, require_active
from app.modules.auth.models import Store

TERMINAL = {'SUCCESS', 'FAILED', 'CANCELLED'}


async def create(db, user, data, key):
    rec = await owned(db, Recommendation, data.recommendation_id, user)
    service = await owned(db, ServiceSession, rec.service_id, user, lock=True)
    ih = content_hash(data.model_dump(mode='json'))
    existing = await db.scalar(select(Acceptance).where(Acceptance.store_id == user.store_id, Acceptance.idempotency_key == key))
    if existing and existing.payload_hash != ih: raise DomainError('KEY_CONFLICT', '同一请求号对应不同受理内容')
    if existing is None:
        existing = await db.scalar(select(Acceptance).where(Acceptance.recommendation_id == rec.id, Acceptance.candidate_id == data.candidate_id))
    if existing:
        await db.commit(); return existing
    require_active(service)
    candidate = next((c for c in rec.candidates if c['candidate_id'] == str(data.candidate_id)), None)
    if candidate is None or candidate['eligibility'] != 'eligible':
        raise DomainError('INELIGIBLE', '此候选不能受理，请补齐资料或重新选择')
    rid = await db.scalar(insert(Acceptance).values(store_id=user.store_id, service_id=rec.service_id,
        recommendation_id=rec.id, candidate_id=data.candidate_id, idempotency_key=key, payload_hash=ih).on_conflict_do_nothing().returning(Acceptance.id))
    row = await db.get(Acceptance, rid) if rid else await db.scalar(select(Acceptance).where(Acceptance.store_id == user.store_id, Acceptance.idempotency_key == key))
    if row is None:
        row = await db.scalar(select(Acceptance).where(Acceptance.recommendation_id == rec.id, Acceptance.candidate_id == data.candidate_id))
    if row.payload_hash != ih: raise DomainError('KEY_CONFLICT', '同一请求号对应不同受理内容')
    if rid: event(db, user, row.service_id, 'ACCEPTANCE_DRAFTED', {'acceptance_id': str(row.id)})
    await db.commit()
    return row


async def prepare_confirmation(db, user, aid, data):
    row = await owned(db, Acceptance, aid, user)
    if row.status != 'DRAFT':
        return row
    rec = await owned(db, Recommendation, row.recommendation_id, user)
    snapshot = await owned(db, AccountSnapshot, rec.snapshot_id, user)
    number, account_type = snapshot.payload['number'], snapshot.payload['account_type']
    await db.commit()
    fresh = await boss.query_account(number, account_type)
    await require_current(db, user, rec)
    service = await owned(db, ServiceSession, rec.service_id, user)
    require_active(service)
    row = await owned(db, Acceptance, aid, user, lock=True)
    if row.status != 'DRAFT': return row
    if row.expected_version != data.expected_version: raise DomainError('STALE_VERSION', '受理版本已变化，请刷新后确认')
    q = await owned(db, QualityCheck, data.quality_check_id, user)
    if q.target_id != rec.id or q.candidate_id != row.candidate_id or q.status == 'BLOCKED':
        raise DomainError('QUALITY_REQUIRED', '此方案缺少有效质检，不可跳过阻断')
    review = await db.scalar(select(QualityReview).where(QualityReview.quality_check_id == q.id).order_by(QualityReview.created_at.desc(), QualityReview.id.desc()).limit(1))
    if review is None or review.decision != 'CONFIRM': raise DomainError('REVIEW_REQUIRED', '请先完成人工复核')
    if fresh.status != 'FOUND' or content_hash(fresh.payload.model_dump(mode='json', exclude_unset=True)) != content_hash(snapshot.payload):
        raise DomainError('FACTS_CHANGED', '账号资料已变化，请重新查询、推荐并确认')
    candidate = next(c for c in rec.candidates if c['candidate_id'] == str(row.candidate_id))
    policy = await owned(db, PolicyVersion, UUID(candidate['policy_version_id']), user)
    day = business_date()
    latest = await db.scalar(select(func.max(PolicyVersion.version)).where(PolicyVersion.product_id == policy.product_id,
        PolicyVersion.status == 'PUBLISHED', PolicyVersion.valid_from <= day, PolicyVersion.valid_to >= day))
    if not effective(policy, day) or policy.version != latest: raise DomainError('POLICY_CHANGED', '有效政策已更新，请重新推荐')
    store = await db.get(Store, user.store_id)
    if policy.conditions.get('region') and policy.conditions['region'] != store.region: raise DomainError('REGION_MISMATCH', '政策不适用于本门店地区')
    checked = recommend(snapshot.payload, DemandProfile.model_validate(rec.demand), [policy], day)
    valid = next((c for c in checked['candidates'] if c['policy_version_id'] == str(policy.id) and c['eligibility'] == 'eligible'), None)
    if valid is None or any(valid[k] != candidate[k] for k in ('monthly_fee','one_time_fee','contract_months','broadband')):
        raise DomainError('INELIGIBLE', '费用或资格复核未通过，请重新推荐')
    product = await owned(db, Product, policy.product_id, user)
    row.external_payload = {'external_request_id': str(row.external_request_id), 'account_id': str(fresh.payload.external_id),
        'policy_version_id': str(policy.id), 'product_id': str(product.id), 'product_name': product.name,
        'monthly_fee': candidate['monthly_fee'], 'one_time_fee': candidate['one_time_fee'], 'contract_months': candidate['contract_months'],
        'broadband': candidate['broadband'],
        'expected_source_time': fresh.source_time.isoformat()}
    row.quality_check_id, row.confirmed_by, row.confirmed_at, row.confirmation_hash = q.id, user.user_id, utcnow(), q.input_hash
    event(db, user, row.service_id, 'ACCEPTANCE_READY', {'acceptance_id': str(row.id), 'quality_check_id': str(q.id), 'input_hash': q.input_hash})
    row.status, row.expected_version = 'SUBMITTING', row.expected_version+1
    event(db, user, row.service_id, 'ACCEPTANCE_SUBMITTING', {'acceptance_id': str(row.id), 'external_request_id': str(row.external_request_id)})
    await db.commit()
    return row


async def merge_result(db, user, aid, result):
    row = await owned(db, Acceptance, aid, user, lock=True)
    if row.status in TERMINAL:
        await db.commit(); return row
    if result.get('external_request_id') and str(row.external_request_id) != str(result['external_request_id']):
        raise DomainError('BOSS_INVALID_RESPONSE', '外部请求号不一致，需继续核查', 502)
    status = {'SUCCESS':'SUCCESS','FAILED':'FAILED','PROCESSING':'SUBMITTED'}.get(result.get('status'), 'UNKNOWN')
    if status in ('SUCCESS','FAILED','SUBMITTED') and not result.get('external_order_id'): status = 'UNKNOWN'
    if row.external_order_id and result.get('external_order_id') and str(row.external_order_id) != str(result['external_order_id']):
        status = 'UNKNOWN'
    before = row.status
    row.status, row.expected_version = status, row.expected_version+1
    row.last_error = result.get('reason') if status != 'UNKNOWN' else '外部结果尚未查明，请按原请求号核对'
    if result.get('external_order_id') and status != 'UNKNOWN': row.external_order_id = UUID(str(result['external_order_id']))
    if status == 'SUCCESS':
        rec = await owned(db, Recommendation, row.recommendation_id, user)
        snapshot = await owned(db, AccountSnapshot, rec.snapshot_id, user)
        await db.execute(insert(CustomerBusiness).values(store_id=user.store_id,
            customer_id=uuid5(user.store_id, str(snapshot.payload['customer_external_id'])), account_id=snapshot.account_id,
            acceptance_id=row.id, external_order_id=row.external_order_id, source='BOSS_MOCK_ACCEPTANCE',
            observed_at=utcnow(), payload=row.external_payload).on_conflict_do_nothing())
    event(db, user, row.service_id, 'ACCEPTANCE_RESULT', {'acceptance_id': str(aid), 'from': before, 'to': row.status, 'external_request_id': str(row.external_request_id)})
    await db.commit()
    return row


async def submit(db, user, row):
    aid, payload = row.id, row.external_payload
    await db.commit()
    try: result = await boss.submit(payload)
    except DomainError: result = {'status': 'UNKNOWN'}
    return await merge_result(db, user, aid, result)


async def confirm(db, user, aid, data):
    original = await owned(db, Acceptance, aid, user)
    if original.status != 'DRAFT': return original
    row = await prepare_confirmation(db, user, aid, data)
    if row.status == 'SUBMITTING': return await submit(db, user, row)
    return row


async def reconcile(db, user, aid):
    row = await owned(db, Acceptance, aid, user)
    if row.status not in ('SUBMITTING','SUBMITTED','UNKNOWN'): return row
    request_id = row.external_request_id
    await db.commit()
    try:
        result = await boss.lookup(request_id)
        if result['status'] == 'NOT_FOUND':
            # Mock guarantees persistent idempotency: only the original key and content may be retried.
            return await submit(db, user, row)
    except DomainError: result = {'status': 'UNKNOWN'}
    return await merge_result(db, user, aid, result)


async def cancel(db, user, aid):
    row = await owned(db, Acceptance, aid, user, lock=True)
    if row.status != 'DRAFT': raise DomainError('CANNOT_CANCEL', '仅未提交草稿可取消；外部受理不能据此撤单')
    row.status, row.expected_version = 'CANCELLED', row.expected_version+1
    event(db, user, row.service_id, 'ACCEPTANCE_CANCELLED', {'acceptance_id': str(aid)})
    await db.commit()
    return row
