import argparse
import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4
from sqlalchemy import select
from app import models
from app.core.config import Settings
from app.core.db import session_scope
from app.core.digests import content_hash
from app.modules.auth.schemas import CurrentUser
from app.modules.evaluations.metrics import issue_metrics
from app.modules.evaluations.models import EvaluationRun, EvaluationResult
from app.modules.evaluations.schemas import EvaluationCase
from app.modules.quality.rules import check_candidate, check_text
from app.modules.recommendations.ai_service import execute
from app.modules.recommendations.models import PromptVersion
from app.modules.recommendations.rules import RULE_VERSION
from app.seed import DEMO_STORE, seed_id


def load_cases(path):
    cases=[EvaluationCase.model_validate_json(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if len({c.id for c in cases})!=len(cases): raise ValueError('重复用例 ID')
    return cases


def validate_live(cases,max_calls,*,smoke=False):
    if smoke and any(c.split!='dev' for c in cases): raise ValueError('联网试跑仅使用开发集，不能消耗保留集')
    if not smoke and any(c.review_status!='CONFIRMED' or not c.reviewer for c in cases): raise ValueError('真实评测需先完成人工核对并填写核对人')
    if max_calls is None or max_calls < 2*len(cases): raise ValueError('需显式设置调用预算；每例最多含一次格式修复，共 2 次请求')


async def run_batch(cases,prompt_version,live=False,max_calls=None,*,smoke=False):
    if smoke and not live: raise ValueError('联网试跑需显式 --live')
    if live: validate_live(cases,max_calls,smoke=smoke)
    cfg=Settings()
    if live and not cfg.deepseek_api_key.get_secret_value(): raise ValueError('请在本地环境配置 DeepSeek 密钥')
    os.environ['AI_MODE']='deepseek' if live else 'offline'
    user=CurrentUser(user_id=seed_id('ADMIN'),store_id=DEMO_STORE,username='admin',role='ADMIN',csrf_token='cli')
    async with session_scope() as db:
        prompt=await db.scalar(select(PromptVersion).where(PromptVersion.store_id==user.store_id,PromptVersion.scenario=='quality',PromptVersion.version==prompt_version,PromptVersion.status=='PUBLISHED'))
        if not prompt: raise ValueError('指定的质检提示词版本未发布')
        run=EvaluationRun(id=uuid4(),store_id=user.store_id,prompt_version_id=prompt.id,settings={
            'mode':'live' if live else 'offline','model':cfg.deepseek_model if live else 'offline-fixture',
            'purpose':'connection_smoke' if smoke else 'quality_evaluation','thinking':'disabled' if live else None,
            'rule_version':RULE_VERSION,'data_hash':content_hash([c.model_dump(mode='json') for c in cases]),
            'prompt_hash':content_hash(prompt.text),'split':cases[0].split,'case_count':len(cases),
            'labels_confirmed':all(c.review_status=='CONFIRMED' and c.reviewer for c in cases),
            'temperature':0,'max_tokens':2000,'timeout_seconds':60,'max_attempts_per_case':2,
            'call_budget':max_calls,'scope':'pipeline problem IDs; incomplete cases excluded and counted separately'})
        db.add(run); await db.flush()
        rows=[]
        for case in cases:
            row=EvaluationResult(store_id=user.store_id,run_id=run.id,case_id=case.id,input=case.model_dump(mode='json'))
            rows.append(row); db.add(row)
        await db.commit()  # Persist the batch and every pending case before any model call.
        pairs=[]; failed=0
        try:
            for case,row in zip(cases,rows):
                status,findings=check_candidate(case.candidate,case.policies,case.business_date) if case.candidate else check_text(case.text,case.policies,case.business_date)
                payload={'structured':bool(case.candidate and not case.text),'candidate':case.candidate,'text':case.text,
                    'facts':case.facts,'demand':case.demand,'business_date':case.business_date.isoformat(),
                    'policies':[p.model_dump(mode='json') for p in case.policies],
                    'evidence_ids':[str(p.id) for p in case.policies],
                    'issue_vocabulary':['PRICE_MISMATCH','EXPIRED_POLICY','CONTRACT_OMISSION','UNKNOWN_FACT','UNKNOWN_ELIGIBILITY','INCOMPLETE_EXTRACTION','CONTRACT_CONFLICT','CONDITION_OMISSION','COMPOUND_NEED_OMISSION']}
                ai=await execute(db,user,'quality',payload,f'eval-{run.id}-{case.id}',prompt_id=prompt.id)
                row.ai_run_id,row.status,row.error=ai.id,ai.status,ai.error
                row.deterministic_findings=findings
                actual={f['rule_id'] for f in findings}
                if ai.status=='SUCCEEDED':
                    actual.update(f['rule_id'] for f in ai.output['findings'])
                    row.actual_issue_ids=sorted(actual)
                    pairs.append((case.expected_issue_ids,actual))
                else: failed+=1
                await db.commit()
            run.metrics={**({} if smoke else issue_metrics(pairs)),'evaluated_cases':len(pairs),'failed_cases':failed,'total_cases':len(cases)}
            run.status='COMPLETED'; await db.commit()
        except BaseException:
            await db.rollback()
            run.status='INTERRUPTED'; await db.commit()
            raise
        return {'run_id':str(run.id),'settings':run.settings,'metrics':run.metrics}


def main():
    parser=argparse.ArgumentParser(description='离线默认；真实评测必须显式 --live 并完成人工核对。保留集仅在冻结后运行。')
    parser.add_argument('--cases',type=Path,default=Path('evaluation/cases.jsonl'))
    parser.add_argument('--split',choices=['dev','holdout'],required=True)
    parser.add_argument('--prompt-version',required=True)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--smoke',action='store_true',help='仅开发集联网试跑：保留待核对标签，不计算精确率、召回率或对比效果')
    parser.add_argument('--max-calls',type=int)
    args=parser.parse_args()
    cases=[c for c in load_cases(args.cases) if c.split==args.split]
    if not cases: parser.error('所选集合为空')
    result=asyncio.run(run_batch(cases,int(args.prompt_version.removeprefix('V')),args.live,args.max_calls,smoke=args.smoke))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
