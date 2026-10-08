import re
from uuid import uuid4
from sqlalchemy import select, func
from app.core.config import business_date
from app.core.digests import content_hash
from app.core.errors import DomainError
from app.core.security import owned
from app.modules.catalog.models import PolicyVersion
from app.modules.quality.models import QualityCheck, QualityReview
from app.modules.quality.rules import check_candidate, check_text
from app.modules.quality.schemas import QualityInput
from app.modules.recommendations.models import Recommendation
from app.modules.recommendations.ai_service import execute
from app.modules.recommendations.rules import RULE_VERSION
from app.modules.services.models import ServiceSession
from app.modules.services.service import event


async def create(db, user, data, supersedes_id=None):
    rec, candidate, sid = None, None, None
    pids = data.policy_version_ids
    if data.target_type == 'RECOMMENDATION':
        if data.target_id is None or data.candidate_id is None:
            raise DomainError('MISSING_TARGET', '请选择具体推荐方案', 422)
        rec = await owned(db, Recommendation, data.target_id, user)
        candidate = next((c for c in rec.candidates if c['candidate_id'] == str(data.candidate_id)), None)
        if candidate is None: raise DomainError('UNKNOWN_CANDIDATE', '候选不属于当前推荐', 422)
        pids = [candidate['policy_version_id']]
        sid = rec.service_id
    elif data.target_id is not None or not data.text.strip():
        raise DomainError('INVALID_TARGET', '独立文本需填写正文且不指定推荐 ID', 422)
    policies = [await owned(db, PolicyVersion, pid, user) for pid in pids]
    if candidate:
        status, findings = check_candidate(candidate, policies, business_date())
        if data.text:
            text_status, text_findings = check_text(data.text, policies, business_date())
            findings += text_findings
            if text_status == 'BLOCKED': status = 'BLOCKED'
            elif status == 'PASS': status = 'NEEDS_REVIEW'
    else:
        status, findings = check_text(data.text, policies, business_date())
    ih = content_hash({'recommendation_hash': rec.input_hash if rec else None, 'candidate_id': data.candidate_id, 'text': data.text, 'policies': list(map(str, pids))})
    payload = {'structured': bool(candidate and not data.text), 'candidate': candidate,
        'text': re.sub(r'\d{7,}', '[号码已脱敏]', data.text), 'evidence_ids': list(map(str, pids)),
        'policies': [{'id': str(p.id), 'monthly_fee': str(p.monthly_fee) if p.monthly_fee is not None else None, 'contract_months': p.contract_months} for p in policies]}
    run = await execute(db, user, 'quality', payload, 'quality-'+str(uuid4()), service_id=sid)
    if run.status == 'SUCCEEDED':
        findings += run.output['findings']
        if status == 'PASS' and (not run.output['complete'] or run.output['findings']): status = 'NEEDS_REVIEW'
    elif status == 'PASS': status = 'NEEDS_REVIEW'
    row = QualityCheck(store_id=user.store_id, target_type=data.target_type, target_id=data.target_id,
        candidate_id=data.candidate_id, input_hash=ih, rule_version=RULE_VERSION, status=status, text=data.text,
        policy_version_ids=list(map(str, pids)), findings=findings, ai_run_id=run.id, supersedes_id=supersedes_id)
    db.add(row); await db.flush()
    if sid: event(db, user, sid, 'QUALITY_CHECKED', {'quality_check_id': str(row.id), 'status': status})
    await db.commit()
    return row


async def require_current(db, user, rec):
    await owned(db, ServiceSession, rec.service_id, user, lock=True)
    latest = await db.scalar(select(func.max(Recommendation.revision)).where(Recommendation.service_id == rec.service_id))
    if latest != rec.revision:
        raise DomainError('STALE_RECOMMENDATION', '需求或方案已更新，请重新质检并确认')


async def review(db, user, qid, data):
    q = await owned(db, QualityCheck, qid, user)
    rec = await owned(db, Recommendation, q.target_id, user) if q.target_id else None
    if rec: await require_current(db, user, rec)
    q = await owned(db, QualityCheck, qid, user, lock=True)
    if data.decision == 'CONFIRM' and q.status == 'BLOCKED':
        raise DomainError('HARD_BLOCK', '硬规则阻断不能人工跳过，请修订后重新检查')
    row = QualityReview(store_id=user.store_id, quality_check_id=qid, reviewer_id=user.user_id, **data.model_dump())
    db.add(row); await db.flush()
    if rec: event(db, user, rec.service_id, 'QUALITY_REVIEWED', {'quality_check_id': str(qid), 'decision': data.decision, 'reason': data.reason})
    await db.commit()
    revised = None
    if data.decision == 'REVISE':
        revised = await create(db, user, QualityInput(target_type=q.target_type, target_id=q.target_id, candidate_id=q.candidate_id,
            text=data.revised_text, policy_version_ids=q.policy_version_ids), supersedes_id=q.id)
    return {'review_id': row.id, 'decision': row.decision, 'revised_quality_check_id': revised.id if revised else None}
