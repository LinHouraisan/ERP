"""Create traceable stage-two demo documents through the local application API."""
import argparse
import asyncio
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
from urllib.parse import urlparse
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo
import httpx
from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
values = dotenv_values(root/'.env')
ledger = root/'.local/phase2-data-ledger.json'


def seed_id(name):
    return str(uuid5(NAMESPACE_URL, 'erp-phase1-demo/'+name))


async def main(args):
    if values.get('APP_ENV') != 'demo' or urlparse(values.get('DATABASE_URL', '')).path != '/erp_demo' or values.get('WEB_ORIGIN') != 'http://127.0.0.1:5173':
        raise SystemExit('Only the named project demo environment on local ports is allowed')
    state = json.loads(ledger.read_text(encoding='utf-8')) if ledger.exists() else {}

    def save():
        ledger.parent.mkdir(exist_ok=True)
        ledger.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')

    async def balance():
        base = values.get('DEEPSEEK_BASE_URL', '').rstrip('/')
        if urlparse(base).scheme != 'https' or urlparse(base).hostname != 'api.deepseek.com': raise RuntimeError('Paid guard requires the official DeepSeek host')
        async with httpx.AsyncClient(timeout=20, trust_env=False) as c:
            r = await c.get(base+'/user/balance', headers={'Authorization':'Bearer '+values['DEEPSEEK_API_KEY']})
            if r.status_code != 200: raise RuntimeError('Balance unavailable; no paid call started')
            return Decimal(next(b['total_balance'] for b in r.json()['balance_infos'] if b['currency'] == 'CNY'))

    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000/api/v1', timeout=75, trust_env=False) as api:
        ready = await api.get('http://127.0.0.1:8000/health/ready')
        if ready.status_code != 200: raise RuntimeError('Migrate and restart the local services first')
        if args.live and ready.json()['ai_mode'] != 'deepseek': raise RuntimeError('Live samples require the configured DeepSeek adapter')
        api.headers['Origin'] = values['WEB_ORIGIN']
        response = await api.post('/auth/login', json={'username':'admin','password':values['DEMO_PASSWORD']})
        if response.status_code != 200: raise RuntimeError('Demo admin login failed')
        actor = response.json(); api.headers['X-CSRF-Token'] = actor['csrf_token']

        async def get(path):
            r = await api.get(path)
            if r.status_code != 200: raise RuntimeError(f'GET {path}: HTTP {r.status_code}')
            return r.json()

        async def step(name, path, data, paid=False):
            if name in state: return state[name]
            if paid:
                if not args.live: return None
                if 'starting_balance_cny' not in state: state['starting_balance_cny'] = str(await balance()); save()
                if Decimal(state['starting_balance_cny'])-await balance() >= args.max_spend_cny: raise RuntimeError('Demo spending guard reached')
            r = await api.post(path, json=data)
            if r.status_code >= 300: raise RuntimeError(f'{name}: HTTP {r.status_code}, code={r.json().get("code")}')
            state[name] = r.json(); save(); print(name+': saved', flush=True)
            return state[name]

        products = {key:seed_id('phase2-product-'+key) for key in ('router','phone','mesh','cable','install','deposit','collection')}
        policies = {key:seed_id('phase2-policy-'+key+'-1') for key in products}
        suppliers = [seed_id('phase2-supplier-1'),seed_id('phase2-supplier-2')]
        costs = {'router':'185.00','phone':'780.00','mesh':'260.00','cable':'8.00'}
        quantities = {'router':5,'phone':3,'mesh':4,'cable':60}
        po = await step('stock/purchase', '/inventory/purchases', {'request_key':'phase2-demo-stock-1', 'supplier_id':suppliers[0],
            'lines':[{'product_id':products[k],'quantity':q,'unit_cost':costs[k]} for k,q in quantities.items()]})
        await step('stock/approve', f"/inventory/purchases/{po['id']}/approve", {})
        receipt = []
        for line in po['lines']:
            key = next(k for k,pid in products.items() if pid == line['product_id'])
            receipt.append({'line_id':line['id'], 'quantity':line['quantity'], 'serials':[] if key == 'cable' else [f'DEMO-{key.upper()}-{i:03}' for i in range(1,line['quantity']+1)]})
        await step('stock/receive', f"/inventory/purchases/{po['id']}/receive", {'request_key':'phase2-demo-receipt-1','lines':receipt})
        partial = await step('partial/purchase', '/inventory/purchases', {'request_key':'phase2-demo-stock-2','supplier_id':suppliers[1], 'lines':[{'product_id':products['router'],'quantity':3,'unit_cost':'180.00'}]})
        await step('partial/approve', f"/inventory/purchases/{partial['id']}/approve", {})
        await step('partial/receive', f"/inventory/purchases/{partial['id']}/receive", {'request_key':'phase2-demo-receipt-2','lines':[{'line_id':partial['lines'][0]['id'],'quantity':1,'serials':['DEMO-ROUTER-006']}]})
        await step('pending/purchase', '/inventory/purchases', {'request_key':'phase2-demo-stock-3','supplier_id':suppliers[1], 'lines':[{'product_id':products['cable'],'quantity':100,'unit_cost':'7.50'}]})

        follow = await step('follow/service', '/service-sessions', {'category':'PLAN'})
        follow_id = follow['service_id']
        queried = await step('follow/query', f'/service-sessions/{follow_id}/account-query', {'number':'19900000013'})
        follow_detail = await get('/service-sessions/'+follow_id)
        cid = follow_detail['customer_id']
        await step('follow/customer', f'/customers/{cid}/edit', {'display_name':'陈女士（模拟·即将到期）','contact':'19900000013','address':'演示市东路 13 号'})
        await step('follow/task', f"/customers/{cid}/follow-up/{queried['snapshot_id']}", {})
        await step('follow/recommendation', f'/service-sessions/{follow_id}/recommendations', {'snapshot_id':queried['snapshot_id'],'demand':{'intent':'CONSULT','must_keep':['broadband']}})
        accepted = next((a for a in (await get('/acceptances'))['items'] if a['status'] == 'SUCCESS'), None)
        source_id = accepted['service_id'] if accepted else follow_id
        source = await get('/service-sessions/'+source_id)
        customer = source['customer_id']
        await step('normal/customer', f'/customers/{customer}/edit', {'display_name':'林先生（模拟·家庭组网）','contact':source['snapshots'][-1]['payload']['number'],'address':'演示市家庭路 8 号'})

        async def order(name, items, method='WECHAT', scenario='NORMAL', linked=False):
            row = await step(name+'/order', '/sales/orders', {'request_key':'phase2-demo-'+name, 'customer_id':customer,
                'source_service_id':source_id if linked else None,'source_acceptance_id':accepted['acceptance_id'] if linked and accepted else None,
                'lines':[{'policy_version_id':policies[k],'quantity':q} for k,q in items]})
            await step(name+'/confirm', f"/sales/orders/{row['id']}/confirm", {})
            pay = await step(name+'/pay', f"/sales/orders/{row['id']}/pay", {'method':method,'scenario':scenario})
            return row, pay

        normal, normal_pay = await order('normal', [('router',1),('install',1)], linked=True)
        if normal_pay['status'] != 'SUCCESS': raise RuntimeError('Normal payment requires reconciliation before continuing')
        await step('normal/dispatch', f"/sales/orders/{normal['id']}/dispatch", {})
        install = await step('normal/installation', '/installations', {'source_order_id':normal['id'],'address':'演示市家庭路 8 号','appointment_at':'2026-10-03T14:00:00+08:00'})
        await step('normal/assign', f"/installations/{install['id']}/dispatch", {'installer_id':seed_id('INSTALLER')})
        for action in ('accept','collect','arrive','install','complete'):
            await step('normal/'+action, f"/installations/{install['id']}/transition", {'request_key':'phase2-demo-install-'+action,'action':action,
                'note':'模拟演示：'+{'accept':'装维接单','collect':'领取销售路由器和两条额外网线','arrive':'已到模拟现场','install':'网络测试正常','complete':'已模拟取得客户验收确认，非真实签名'}[action],
                'materials':[{'product_id':products['cable'],'quantity':2}] if action == 'collect' else [], 'customer_accepted':action == 'complete'})
        sales_earning = await step('normal/sale-earning', '/finance/accruals', {'source_type':'SALE','source_id':normal['id']})
        work_earning = await step('normal/install-earning', '/finance/accruals', {'source_type':'INSTALLATION','source_id':install['id']})
        telecom_earning = await step('normal/telecom-earning', '/finance/accruals', {'source_type':'TELECOM','source_id':accepted['acceptance_id']}) if accepted else None
        pending, _ = await order('pending', [('phone',1),('deposit',1),('collection',1)], method='CASH')
        awaiting = await step('pending/installation', '/installations', {'source_order_id':pending['id'],'address':'演示市新居路 16 号','appointment_at':'2026-10-04T10:00:00+08:00'})
        await step('pending/assign', f"/installations/{awaiting['id']}/dispatch", {'installer_id':seed_id('INSTALLER')})
        await step('pending/reschedule', f"/installations/{awaiting['id']}/reschedule", {'appointment_at':'2026-10-05T14:00:00+08:00','note':'模拟客户改约，保留原派工记录并退回待派'})
        period = sales_earning['period']
        bill_rows = [{'business_no':sales_earning['business_no'],'amount':sales_earning['expected_amount'],'received_amount':sales_earning['expected_amount']},
            {'business_no':work_earning['business_no'],'amount':'25.00','received_amount':None},
            {'business_no':'SIMULATED-MISSING-INTERNAL-001','amount':'15.00','received_amount':'0.00'}]
        if telecom_earning: bill_rows.append({'business_no':telecom_earning['business_no'],'amount':telecom_earning['expected_amount'],'received_amount':telecom_earning['expected_amount']})
        await step('bills/import', '/finance/bills', {'request_key':'phase2-demo-bill-1','period':period,'source':'二阶段人工模拟账单：匹配、金额差异、缺内部单据','rows':bill_rows})
        day = datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
        closing = await step('close/create', '/sales/day-closes', {'request_key':'phase2-demo-close-1','business_day':day,'cashier_id':actor['user_id'],'counted_cash':pending['total']})
        await step('close/confirm', f"/sales/day-closes/{closing['id']}/confirm", {'note':'模拟核对完成，经营款、代收款、押金与支付方式分列；未发生真实收款'})
        await order('unknown', [('mesh',1)], scenario='SUCCESS_TIMEOUT')
        await order('declined', [('cable',3)], method='CARD', scenario='DECLINED')
        await step('geo/import', '/operations/geo-samples', {'request_key':'phase2-demo-geo-1','samples':[
            {'platform':'模拟平台 A','question':'本地宽带安装需要哪些准备？','answer':'模拟营业厅可登记安装需求，价格和时段以店内确认结果为准。','brand':'模拟营业厅','captured_at':'2026-10-03T09:00:00+08:00','simulated':True,'citations':['https://example.com/demo/installation'],'factual_errors':'模拟回答，未用于证明平台收录或曝光'},
            {'platform':'模拟平台 B','question':'哪里可以买到路由器？','answer':'可以在正规电子产品销售渠道购买，购买前确认保修政策。','brand':'模拟营业厅','captured_at':'2026-10-03T09:10:00+08:00','simulated':True,'citations':[],'factual_errors':'未出现品牌，仅为未命中样本'},
            {'platform':'模拟平台 C','question':'安装费是多少？','answer':'模拟营业厅所有安装都免费。','brand':'模拟营业厅','captured_at':'2026-10-03T09:20:00+08:00','simulated':True,'citations':[],'factual_errors':'与本地已发布的 80 元模拟安装政策不一致，需核查说明，不能据此承诺免费'}]})
        await step('follow/finish', f'/service-sessions/{follow_id}/finish', {})
        if 'operations/snapshot' not in state: state['operations/snapshot'] = await get('/operations/overview'); save()
        await step('ai/sales', '/sales/assist', {'request_key':'phase2-demo-sales-ai','customer_id':customer,'source_service_id':source_id,'text':'客户已保留现有宽带，希望比较路由器和组网节点，说明安装选择；只给人工草稿。'}, paid=True)
        await step('ai/operations', '/operations/summary', {'request_key':'phase2-demo-operations-ai','snapshot_id':state['operations/snapshot']['id'],'question':'概括销售、设备交付和收益到账的情况，指出金额差异与待核查事项，不归责个人。'}, paid=True)
        if args.live: state['ending_balance_cny'] = str(await balance())
        state['complete'] = True; save()
        print('Stage-two simulated data saved; one UNKNOWN payment is retained for original-request reconciliation.')
        if args.live: print('Observed balance change (CNY):', Decimal(state['starting_balance_cny'])-Decimal(state['ending_balance_cny']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--demo', action='store_true', required=True)
    parser.add_argument('--live', action='store_true'); parser.add_argument('--max-spend-cny', type=Decimal, default=Decimal('0.50'))
    asyncio.run(main(parser.parse_args()))
