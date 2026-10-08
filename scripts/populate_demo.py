"""Add first-stage simulated business records through the real local APIs.

Progress stays in .local so rerunning resumes without redoing completed paid calls.
This does not confirm evaluation labels or claim real customer/operating outcomes.
"""
import argparse
import asyncio
from decimal import Decimal
import json
from pathlib import Path
from urllib.parse import urlparse
import httpx
from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
values = dotenv_values(root / '.env')
parser = argparse.ArgumentParser()
parser.add_argument('--live', action='store_true', help='Explicitly authorize paid DeepSeek demo calls')
parser.add_argument('--max-spend-cny', type=Decimal, default=Decimal('2'))
args = parser.parse_args()
if values.get('APP_ENV') != 'demo' or urlparse(values.get('DATABASE_URL', '')).path != '/erp_demo':
    raise SystemExit('Only this project demo environment is allowed')
ledger = root / '.local/demo-data-ledger.json'
state = json.loads(ledger.read_text(encoding='utf-8')) if ledger.exists() else {}


def save():
    ledger.parent.mkdir(exist_ok=True)
    ledger.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


async def main():
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000/api/v1', timeout=75) as api, httpx.AsyncClient(
        base_url='http://127.0.0.1:8001/mock/v1', timeout=10,
        headers={'Authorization': 'Bearer ' + values['BOSS_TOKEN']},
    ) as mock:
        ready = (await api.get('http://127.0.0.1:8000/health/ready')).json()
        if ready.get('ai_mode') != 'deepseek' or not args.live:
            raise SystemExit('Enable DeepSeek locally and pass --live for this data population')
        api.headers['Origin'] = values['WEB_ORIGIN']
        login = await api.post('/auth/login', json={'username': 'admin', 'password': values['DEMO_PASSWORD']})
        if login.status_code != 200: raise RuntimeError('Local admin login failed')
        actor = login.json()
        api.headers['X-CSRF-Token'] = actor['csrf_token']

        async def balance():
            base = values['DEEPSEEK_BASE_URL'].rstrip('/')
            if urlparse(base).scheme != 'https' or urlparse(base).hostname != 'api.deepseek.com':
                raise RuntimeError('Balance guard requires the official DeepSeek host')
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(base + '/user/balance', headers={'Authorization': 'Bearer ' + values['DEEPSEEK_API_KEY']})
                if response.status_code != 200: raise RuntimeError('Cannot read balance; no paid call started')
                return Decimal(next(b['total_balance'] for b in response.json()['balance_infos'] if b['currency'] == 'CNY'))

        if 'starting_balance_cny' not in state:
            state['starting_balance_cny'] = str(await balance())
            save()

        async def step(name, path, data=None, *, paid=False, method='POST', headers=None):
            if name in state: return state[name]
            if paid and Decimal(state['starting_balance_cny']) - await balance() >= args.max_spend_cny:
                raise RuntimeError('Demo spending limit reached; completed records preserved')
            response = await api.request(method, path, json=data, headers=headers)
            if response.status_code >= 300:
                raise RuntimeError(f'{name}: HTTP {response.status_code}, code={response.json().get("code")}')
            state[name] = response.json()
            save()
            print(f'{name}: saved', flush=True)
            return state[name]

        async def new_service(name, category='PLAN'):
            return (await step(name + '/service', '/service-sessions', {'category': category}))['service_id']

        async def recommend(name, sid, number, demand):
            snapshot = await step(name + '/query', f'/service-sessions/{sid}/account-query', {'number': number})
            return await step(name + '/recommendation', f'/service-sessions/{sid}/recommendations', {'snapshot_id': snapshot['snapshot_id'], 'demand': demand})

        async def finish(name, sid, score=None, comment=''):
            await step(name + '/finish', f'/service-sessions/{sid}/finish', {})
            if score is not None:
                link = await step(name + '/feedback-link', f'/service-sessions/{sid}/feedback-link', {})
                await step(name + '/feedback', '/public/feedback', {'token': link['token'], 'score': score, 'tags': ['解释清晰度'], 'comment': '模拟演示评价：' + comment})

        async def task(name, sid, title, target='OPEN'):
            row = await step(name + '/task', '/service-tasks', {'service_id': sid, 'title': title, 'owner_role': 'STAFF'})
            if target in ('IN_PROGRESS', 'CLOSED'):
                await step(name + '/task-start', f"/service-tasks/{row['id']}/transition", {'status': 'IN_PROGRESS', 'note': '模拟处理：已登记并核查说明'})
            if target == 'CLOSED':
                await step(name + '/task-close', f"/service-tasks/{row['id']}/transition", {'status': 'CLOSED', 'note': '模拟咨询说明完成；未执行真实装维验收'})

        async def ticket(name, category):
            public = await step(name + '/take', '/public/queue-tickets', {'category': category})
            if name + '/ticket' not in state:
                items = (await api.get('/queue-tickets')).json()['items']
                state[name + '/ticket'] = next(t for t in items if t['ticket_number'] == public['ticket_number'])
                save()
            return state[name + '/ticket']

        windows = (await api.get('/windows')).json()['items']
        async def call(name, t, index):
            result = await step(name + '/call', f"/windows/{windows[index]['id']}/call-next", {})
            if not result['ticket'] or result['ticket']['id'] != t['id']:
                raise RuntimeError('Another ticket already occupies this window; it was not modified further')

        normal = await ticket('normal', 'PLAN')
        await call('normal', normal, 0)
        serving = await step('normal/start', f"/queue-tickets/{normal['id']}/start", {})
        sid = serving['service_id']
        analysis = await step('normal/analyze', f'/service-sessions/{sid}/analyze', {'request_key': 'demo-data-normal-analyze-20261003', 'text': '模拟需求：当前129元，希望月费在100元以内，必须保留宽带，同时登记网络间歇卡顿问题。'}, paid=True)
        if analysis['status'] != 'SUCCEEDED': raise RuntimeError('Inspect saved demand run before continuing')
        rec = await recommend('normal', sid, '19900000001', {'intent': 'REDUCE_COST', 'budget': '100.00', 'must_keep': ['broadband'], 'issues': ['网络间歇卡顿']})
        explanation = await step('normal/explain', f"/recommendations/{rec['recommendation_id']}/explain", {'request_key': 'demo-data-normal-explain-20261003'}, paid=True)
        if explanation['status'] != 'SUCCEEDED': raise RuntimeError('Inspect saved explanation run before continuing')

        async def accept(name, sid, rec, number, scenario='NORMAL'):
            candidate = next(c for c in rec['candidates'] if c['monthly_fee'] == '89.00' and c['eligibility'] == 'eligible')
            assert candidate['one_time_fee'] == '0.00' and candidate['broadband'] is True and candidate['contract_months'] == 12
            quality = await step(name + '/quality', f"/recommendations/{rec['recommendation_id']}/quality-checks", {'candidate_id': candidate['candidate_id']}, paid=True)
            if quality['status'] == 'BLOCKED': raise RuntimeError('Hard quality block; inspect rather than bypass')
            await step(name + '/review', f"/quality-checks/{quality['quality_check_id']}/reviews", {'decision': 'CONFIRM', 'reason': '模拟人工复核：核对89元月费、0元一次费、12个月合约与保留宽带；仅演示业务'})
            draft = await step(name + '/draft', '/acceptances', {'recommendation_id': rec['recommendation_id'], 'candidate_id': candidate['candidate_id']}, headers={'Idempotency-Key': 'demo-data-' + name + '-20261003'})
            try:
                response = await mock.post(f'/scenarios/accounts/{number}', json={'scenario': scenario})
                response.raise_for_status()
                result = await step(name + '/submit', f"/acceptances/{draft['acceptance_id']}/confirm", {'expected_version': draft['expected_version'], 'quality_check_id': quality['quality_check_id']})
            finally:
                response = await mock.post(f'/scenarios/accounts/{number}', json={'scenario': 'NORMAL'})
                response.raise_for_status()
            expected = {'NORMAL': 'SUCCESS', 'SUCCESS_TIMEOUT': 'UNKNOWN', 'REJECT': 'FAILED'}[scenario]
            assert result['status'] == expected, (name, result['status'])
            return result

        await accept('normal', sid, rec, '19900000001')
        await step('normal/query-after', f'/service-sessions/{sid}/account-query', {'number': '19900000001'})
        await task('normal', sid, '模拟咨询：解释新合约和宽带保留', 'CLOSED')
        await finish('normal', sid, 5, '费用和新合约解释清楚，模拟办理已完成')

        for name, number, scenario in [('unknown', '19900000007', 'SUCCESS_TIMEOUT'), ('rejected', '19900000008', 'REJECT')]:
            sid = await new_service(name)
            rec = await recommend(name, sid, number, {'intent': 'REDUCE_COST', 'must_keep': ['broadband']})
            await accept(name, sid, rec, number, scenario)
            await finish(name, sid)

        examples = [
            ('missing', '19900000004', 'PLAN', {'intent':'REDUCE_COST'}, 'NEEDS_INFO', '模拟核查：补齐来源系统月费', 'OPEN', None),
            ('contract', '19900000002', 'PLAN', {'intent':'REDUCE_COST'}, 'NEEDS_INFO', '模拟核查：确认在约变更条件', 'OPEN', None),
            ('fault', '19900000006', 'FAULT', {'intent':'FAULT','issues':['网络故障']}, 'SERVICE_TASK', '模拟报障：待后续处理，不代表装维完成', 'IN_PROGRESS', 2),
            ('keep', '19900000005', 'OTHER', {'intent':'KEEP_CURRENT'}, 'NEEDS_INFO', '模拟核查：实名状态未知，补齐后再决策', 'OPEN', 3),
            ('keep-current', '19900000003', 'OTHER', {'intent':'KEEP_CURRENT'}, 'KEEP_CURRENT', '模拟咨询：合约已结束，尊重客户保留当前套餐的要求', 'CLOSED', None),
            ('no-match', '19900000010', 'PLAN', {'intent':'REDUCE_COST','budget':'30.00'}, 'NO_MATCH', '模拟咨询：30元预算暂无匹配套餐', 'CLOSED', 4),
        ]
        for name, number, category, demand, expected, title, target, score in examples:
            sid = await new_service(name, category)
            rec = await recommend(name, sid, number, demand)
            assert rec['outcome'] == expected, (name, rec['outcome'])
            await task(name, sid, title, target)
            await finish(name, sid, score, title)

        products = (await api.get('/products')).json()['items']
        product = next(p for p in products if p['name'] == '融合89')
        policies = (await api.get(f"/products/{product['id']}/policy-versions")).json()['items']
        policy = next(p for p in policies if p['status'] == 'PUBLISHED' and p['version'] == 1)
        wrong = await step('text/wrong', '/quality-checks', {'target_type':'MARKETING','text':'月费59元，一次费0元，合约12个月。','policy_version_ids':[policy['id']]}, paid=True)
        assert wrong['status'] == 'BLOCKED'
        await step('text/revision', f"/quality-checks/{wrong['quality_check_id']}/reviews", {'decision':'REVISE','reason':'模拟修订：按已发布政策纠正59元错价','revised_text':'月费89元，一次费0元，合约12个月；其他条件以已发布政策核对。'}, paid=True)
        reply = await step('text/reply', '/quality-checks', {'target_type':'REPLY','text':'月费89元，可直接办理。','policy_version_ids':[policy['id']]}, paid=True)
        assert reply['status'] == 'BLOCKED'

        requeue = await ticket('requeue', 'OTHER')
        await call('requeue', requeue, 2)
        for action in ('miss', 'requeue', 'cancel'):
            await step('requeue/' + action, f"/queue-tickets/{requeue['id']}/{action}", {'reason':'模拟演示：过号、重排后客户取消'})
        missed = await ticket('missed', 'OTHER')
        await call('missed', missed, 2)
        await step('missed/miss', f"/queue-tickets/{missed['id']}/miss", {'reason':'模拟演示：客户暂未到窗口'})
        called = await ticket('called', 'FAULT')
        await call('called', called, 1)
        await ticket('waiting-plan', 'PLAN')
        await ticket('waiting-other', 'OTHER')

        before = await step('improvement/before', '/service-metrics', method='GET')
        proposal = await step('improvement/proposal', '/improvement-proposals', {'snapshot_id':before['snapshot_id'],'request_key':'demo-data-improvement-20261003'}, paid=True)
        tid = proposal['id']
        await step('improvement/approve', f'/improvement-tasks/{tid}/transition', {'status':'APPROVED','reason':'模拟审核：依据统计快照核查建议','owner_id':actor['user_id'],'plan':'核查待补资料与故障服务记录，完善费用和等待说明','target':'保留完整解释与后续处理证据；不预设改善幅度'})
        await step('improvement/start', f'/improvement-tasks/{tid}/transition', {'status':'IN_PROGRESS','reason':'模拟执行：已检查本批服务记录'})
        after = await step('improvement/after', '/service-metrics', method='GET')
        await step('improvement/verify', f'/improvement-tasks/{tid}/transition', {'status':'VERIFIED','reason':'模拟验证：相同环境记录已保留','verification':{'before_snapshot_id':before['snapshot_id'],'after_snapshot_id':after['snapshot_id'],'conditions_changed':'同一批模拟数据，未收集真实新增经营样本','result':'样本不足，不认定服务质量或经营效果改善','unresolved_issues':'待真实授权样本与业务人员核对'}})
        await step('improvement/close', f'/improvement-tasks/{tid}/transition', {'status':'CLOSED','reason':'模拟流程验证已留痕，未声称真实效果'})
        await step('improvement/open', '/improvement-tasks', {'snapshot_id':after['snapshot_id'],'suggestion':'模拟待办：跟踪未知受理和缺资料服务，按原请求号核对，禁止换号重办'})
        state['ending_balance_cny'] = str(await balance())
        state['complete'] = True
        save()
        print('Demo data populated; one UNKNOWN acceptance is deliberately retained for original-request reconciliation.', flush=True)
        print('Observed balance change (CNY):', Decimal(state['starting_balance_cny'])-Decimal(state['ending_balance_cny']))


if __name__ == '__main__': asyncio.run(main())
