from math import ceil
from statistics import median
from sqlalchemy import select
from app.core.errors import DomainError
from app.core.security import owned, require_role
from app.modules.auth.models import User
from app.modules.feedback.models import Feedback
from app.modules.improvements.models import MetricsSnapshot, ImprovementTask, ImprovementEvent
from app.modules.quality.models import QualityCheck, QualityReview
from app.modules.queue.models import QueueTicket
from app.modules.recommendations.models import Recommendation
from app.modules.recommendations.ai_service import execute
from app.modules.services.models import ServiceSession
from app.modules.installations.models import Installation


def ratio(numerator, denominator):
    return {'numerator': numerator, 'denominator': denominator, 'value': numerator/denominator if denominator else None}


def durations(values):
    values = sorted(values)
    return {'sample_count': len(values), 'p50_seconds': median(values) if values else None,
        'p90_seconds': values[ceil(.9*len(values))-1] if values else None, 'sample_insufficient': len(values) < 5}


def metric_values(services, feedback, tickets, checks, reviews):
    reviewed_problems = {r.quality_check_id for r in reviews if r.decision in ('REJECT','REVISE')}
    checked = {q.input_hash for q in checks}
    problems = {q.input_hash for q in checks if q.status == 'BLOCKED' or q.id in reviewed_problems}
    scores = [r.score for r in feedback]
    return {'schema_version': 1, 'completed_services': len(services), 'preset_services': sum(s.preset for s in services),
        'participation': ratio(len(feedback), len(services)),
        'satisfaction': {'sample_count': len(scores), 'average': sum(scores)/len(scores) if scores else None, 'distribution': {str(n): scores.count(n) for n in range(1,6)}},
        'waiting': durations([q.round_wait_seconds for q in tickets if q.round_wait_seconds is not None]),
        'cumulative_waiting': durations([q.cumulative_wait_seconds for q in tickets if q.called_at is not None]),
        'service_duration': durations([max(0,(s.ended_at-s.created_at).total_seconds()) for s in services]),
        'cancelled': sum(q.status=='CANCELLED' for q in tickets), 'missed': sum(q.status=='MISSED' for q in tickets),
        'quality_problem_rate': ratio(len(problems),len(checked))}


async def metrics(db, user, start, end, category=None):
    require_role(user, 'MANAGER', 'ADMIN')
    if start >= end: raise DomainError('INVALID_RANGE', '开始时间必须早于结束时间', 422)
    where = [ServiceSession.store_id == user.store_id, ServiceSession.status == 'ENDED', ServiceSession.ended_at >= start, ServiceSession.ended_at < end]
    if category: where.append(ServiceSession.category == category)
    services = (await db.scalars(select(ServiceSession).where(*where))).all()
    feedback = (await db.scalars(select(Feedback).join(ServiceSession, ServiceSession.id == Feedback.service_id).where(*where))).all()
    tq = select(QueueTicket).where(QueueTicket.store_id == user.store_id, QueueTicket.created_at >= start, QueueTicket.created_at < end)
    if category: tq = tq.where(QueueTicket.category == category)
    tickets = (await db.scalars(tq)).all()
    qq = select(QualityCheck).where(QualityCheck.store_id == user.store_id, QualityCheck.created_at >= start, QualityCheck.created_at < end)
    if category: qq = qq.join(Recommendation, Recommendation.id == QualityCheck.target_id).join(ServiceSession, ServiceSession.id == Recommendation.service_id).where(ServiceSession.category == category)
    checks = (await db.scalars(qq)).all()
    reviews = (await db.scalars(select(QualityReview).where(QualityReview.quality_check_id.in_([q.id for q in checks])))).all()
    result = metric_values(services, feedback, tickets, checks, reviews)
    installations = (await db.scalars(select(Installation).where(Installation.store_id == user.store_id, Installation.created_at >= start, Installation.created_at < end))).all() if category is None else []
    result['fulfillment'] = {'sample_count': len(installations), 'completed': sum(w.status == 'COMPLETED' for w in installations),
        'pending': sum(w.status != 'COMPLETED' for w in installations), 'definition': '按创建时间选安装工单，观察当前交付状态；类别筛选时不混入安装样本'}
    evidence = {'service_ids': [str(s.id) for s in services], 'feedback_ids': [str(f.id) for f in feedback],
        'queue_ticket_ids': [str(q.id) for q in tickets], 'quality_check_ids': [str(q.id) for q in checks], 'installation_ids': [str(w.id) for w in installations]}
    filters = {'from': start.isoformat(), 'to': end.isoformat(), 'category': category,
        'cohort': '服务按结束时间；排队和质检按创建时间；左闭右开；质检按输入摘要去重；问题含确定性阻断及人工驳回/修订', 'percentile': 'p90 使用最近秩法'}
    row = MetricsSnapshot(store_id=user.store_id, filters=filters, payload=result, evidence=evidence)
    db.add(row); await db.commit()
    return row


async def propose(db, user, data):
    require_role(user, 'MANAGER', 'ADMIN')
    snapshot = await owned(db, MetricsSnapshot, data.snapshot_id, user)
    evidence = [eid for ids in snapshot.evidence.values() for eid in ids]
    run = await execute(db, user, 'improvement', {'metrics': snapshot.payload, 'evidence_ids': evidence}, data.request_key)
    existing = await db.scalar(select(ImprovementTask).where(ImprovementTask.ai_run_id == run.id))
    if existing: return existing
    suggestion = run.output if run.status == 'SUCCEEDED' else {'suggestion': 'AI 辅助失败，请人工核查统计快照并拟定计划', 'evidence_ids': evidence}
    row = ImprovementTask(store_id=user.store_id, snapshot_id=snapshot.id, ai_run_id=run.id, suggestion=suggestion)
    db.add(row); await db.commit()
    return row


async def transition(db, user, tid, data):
    require_role(user, 'MANAGER', 'ADMIN')
    row = await owned(db, ImprovementTask, tid, user, lock=True)
    allowed = {'PROPOSED': {'APPROVED','REJECTED'}, 'APPROVED': {'IN_PROGRESS','REJECTED'}, 'IN_PROGRESS': {'VERIFIED'}, 'VERIFIED': {'CLOSED'}}
    if data.status not in allowed.get(row.status,set()): raise DomainError('INVALID_TRANSITION', '需按审核、处理、验证、关闭顺序推进')
    if data.status == 'APPROVED':
        if not data.owner_id or not (data.plan or '').strip() or not (data.target or '').strip():
            raise DomainError('PLAN_REQUIRED', '审核时必须指定负责人、计划和目标', 422)
        await owned(db, User, data.owner_id, user)
        row.owner_id, row.plan, row.target = data.owner_id, data.plan, data.target
    if data.status == 'VERIFIED':
        if data.verification is None: raise DomainError('VERIFICATION_REQUIRED', '请提供前后统计快照与验证结论', 422)
        before = await owned(db, MetricsSnapshot, data.verification.before_snapshot_id, user)
        after = await owned(db, MetricsSnapshot, data.verification.after_snapshot_id, user)
        if before.id != row.snapshot_id or after.id == before.id or after.created_at <= before.created_at:
            raise DomainError('INVALID_VERIFICATION', '前后快照需对应本任务并有明确先后顺序')
        row.verification = {**data.verification.model_dump(mode='json'), 'before_sample_count': before.payload['completed_services'], 'after_sample_count': after.payload['completed_services'], 'before_filters': before.filters, 'after_filters': after.filters}
    if data.status == 'CLOSED' and not row.verification: raise DomainError('VERIFICATION_REQUIRED', '没有验证记录不能关闭')
    db.add(ImprovementEvent(store_id=user.store_id, task_id=tid, actor_id=user.user_id, from_status=row.status, to_status=data.status, reason=data.reason))
    row.status = data.status
    await db.commit()
    return row
