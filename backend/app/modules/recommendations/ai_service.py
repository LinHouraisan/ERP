import time
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from app.core.config import Settings
from app.core.db import utcnow
from app.core.digests import content_hash
from app.core.errors import DomainError
from app.integrations import ai
from app.modules.recommendations.models import AIRun, PromptVersion


async def execute(db, user, scenario, payload, request_key, *, service_id=None, prompt_id=None):
    cfg = Settings()
    prompt = await db.scalar(select(PromptVersion).where(PromptVersion.store_id == user.store_id,
        PromptVersion.status == 'PUBLISHED', PromptVersion.scenario == scenario,
        *([PromptVersion.id == prompt_id] if prompt_id else [])).order_by(PromptVersion.version.desc()).limit(1))
    if prompt is None: raise DomainError('PROMPT_MISSING', '缺少已发布提示词，请由管理员配置')
    ih = content_hash({'scenario': scenario, 'payload': payload, 'prompt_id': prompt.id, 'mode': cfg.ai_mode, 'service_id': service_id})
    existing = await db.scalar(select(AIRun).where(AIRun.store_id == user.store_id, AIRun.request_key == request_key))
    if existing:
        if existing.input_hash != ih: raise DomainError('KEY_CONFLICT', '同一辅助请求号对应不同内容')
        return existing
    row = AIRun(id=uuid4(), store_id=user.store_id, service_id=service_id, prompt_version_id=prompt.id,
        scenario=scenario, request_key=request_key, input_hash=ih, mode=cfg.ai_mode,
        model='offline-fixture' if cfg.ai_mode == 'offline' else cfg.deepseek_model, input=payload)
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(select(AIRun).where(AIRun.store_id == user.store_id, AIRun.request_key == request_key))
        if existing and existing.input_hash == ih: return existing
        raise DomainError('KEY_CONFLICT', '同一辅助请求号对应不同内容') from None
    started = time.monotonic()
    usage, model = None, row.model
    try:
        output, usage, model = await ai.generate(scenario, payload, prompt.text)
        if scenario == 'explanation': output = ai.validate_explanation(output, payload['candidates'])
        elif scenario == 'sales': output = ai.validate_sales(output, payload['offers'])
        elif scenario == 'operations': output = ai.validate_operations(output, payload['metrics'])
        else: output = ai.SCHEMAS[scenario].model_validate(output).model_dump(mode='json')
        if scenario in ('quality', 'improvement'):
            allowed = set(payload.get('evidence_ids', []))
            cited = output.get('evidence_ids', []) if scenario == 'improvement' else [e for f in output['findings'] for e in f['evidence_ids']]
            if not set(cited).issubset(allowed): raise ValueError('Unknown evidence')
        values = {'status': 'SUCCEEDED', 'output': output, 'usage': usage, 'model': model}
    except Exception as error:
        values = {'status': 'FAILED', 'usage': getattr(error, 'usage', usage), 'model': getattr(error, 'model', model),
            'error': getattr(error, 'kind', type(error).__name__) + '：辅助不可用，请继续人工处理'}
    values['elapsed_ms'] = int((time.monotonic()-started)*1000)
    await db.execute(update(AIRun).where(AIRun.id == row.id, AIRun.status == 'RUNNING').values(**values))
    await db.commit()
    await db.refresh(row)
    return row


async def interrupt_expired(db, row):
    if row.status == 'RUNNING' and row.created_at < utcnow() - timedelta(seconds=65):
        await db.execute(update(AIRun).where(AIRun.id == row.id, AIRun.status == 'RUNNING').values(status='INTERRUPTED', error='调用超期或进程中断；可新建辅助请求，人工路径可用'))
        await db.commit(); await db.refresh(row)
    return row


def run_view(row):
    return {key: getattr(row, key) for key in ('id', 'scenario', 'service_id', 'prompt_version_id', 'mode', 'model', 'status', 'input_hash', 'output', 'usage', 'error', 'elapsed_ms', 'created_at')}
