"""Append resumable stage-three examples through the named local demo API."""
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
from urllib.parse import urlparse
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo
import httpx
from dotenv import dotenv_values

root=Path(__file__).resolve().parents[1]
values=dotenv_values(root/'.env')
ledger=root/'.local/phase3-data-ledger.json'


def sid(name): return str(uuid5(NAMESPACE_URL,'erp-phase1-demo/'+name))


async def main():
    if values.get('APP_ENV')!='demo' or urlparse(values.get('DATABASE_URL','')).path!='/erp_demo' or values.get('WEB_ORIGIN')!='http://127.0.0.1:5173':
        raise SystemExit('Only the named local demo environment is allowed')
    state=json.loads(ledger.read_text(encoding='utf-8')) if ledger.exists() else {}
    def save(): ledger.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000/api/v1',timeout=90,trust_env=False) as api:
        api.headers['Origin']=values['WEB_ORIGIN']
        async def login(name):
            r=await api.post('/auth/login',json={'username':name,'password':values['DEMO_PASSWORD']})
            if r.status_code!=200: raise RuntimeError('Demo login failed')
            api.headers['X-CSRF-Token']=r.json()['csrf_token']
        async def get(path):
            r=await api.get(path)
            if r.status_code!=200: raise RuntimeError(f'GET {path}: {r.status_code}')
            return r.json()
        async def step(name,path,body,**kwargs):
            if name in state: return state[name]
            r=await api.post(path,json=body,**kwargs)
            if r.status_code>=300: raise RuntimeError(f'{name}: HTTP {r.status_code}, code={r.json().get("code")}')
            state[name]=r.json();save();print(name+': saved',flush=True)
            return state[name]
        async def order(name,items,customer,second=False):
            await login('staff2' if second else 'staff')
            prefix='store-2-policy-' if second else 'phase2-policy-'
            row=await step(name+'/order','/sales/orders',{'request_key':'phase3-'+name,'customer_id':customer,
                'lines':[{'policy_version_id':sid(prefix+k+'-1'),'quantity':q} for k,q in items]})
            await step(name+'/confirm',f"/sales/orders/{row['id']}/confirm",{})
            await step(name+'/pay',f"/sales/orders/{row['id']}/pay",{'method':'CARD'})
            await login('admin2' if second else 'admin')
            return row
        async def dispatch(name,row): await step(name+'/dispatch',f"/sales/orders/{row['id']}/dispatch",{})
        async def earn(name,row): return await step(name+'/earning','/finance/accruals',{'source_type':'SALE','source_id':row['id']})
        async def bill(name,earning,amount,period,final=True,received='same'):
            return await step(name,'/finance/bills',{'request_key':'phase3-'+name,'period':period,'source':'第三阶段模拟账单：'+name,
                'rows':[{'business_no':earning['business_no'],'earning_period':earning['period'],'line_key':name,
                    'amount':amount,'received_amount':amount if received=='same' else received,'is_final':final}]})
        async def settle(name,earning,amount,period,second=False):
            batch=await step(name,'/finance/settlements',{'request_key':'phase3-'+name,'owner_id':sid('store-2-STAFF' if second else 'STAFF'),
                'period':period,'amount':amount,'earning_ids':[earning['id']],'note':'模拟分批结算，自动先抵扣历史负余额'})
            return await step(name+'/confirm',f"/finance/settlements/{batch['id']}/confirm",{'note':'模拟核对到账、冻结规则及前期扣回；未向任何真实账户付款'})
        async def aftersale(name,row,kind,amount,quantity=0,scenario='NORMAL'):
            case=await step(name,'/aftersales',{'request_key':'phase3-'+name,'order_id':row['id'],'kind':kind,'reason':'模拟：'+name,
                'scenario':scenario,'lines':[{'line_id':row['lines'][0]['id'],'refund_amount':amount,'return_quantity':quantity}]})
            await step(name+'/review',f"/aftersales/{case['id']}/review",{'decision':'APPROVE','note':'模拟核对原收款及客户申请'})
            return case
        async def transfer(name,key,quantity,received,close_loss=False):
            await login('admin')
            row=await step(name,'/transfers',{'request_key':'phase3-'+name,'destination_store_id':sid('store-2'),
                'product_id':sid('phase2-product-'+key),'quantity':quantity,'note':'模拟两店调拨：'+name})
            await step(name+'/review',f"/transfers/{row['id']}/review",{'decision':'APPROVE','note':'模拟店长确认同主体二店需求'})
            sent=await step(name+'/dispatch',f"/transfers/{row['id']}/dispatch",{'note':'按单核对商品后模拟发货'})
            await login('admin2')
            await step(name+'/receive',f"/transfers/{row['id']}/receive",{'request_key':'phase3-'+name+'-receive','quantity':received,
                'serials':sent['serials'][:received],'note':'模拟二店验收，差额继续单列在途'})
            if close_loss:
                await login('admin')
                await step(name+'/resolve',f"/transfers/{row['id']}/resolve",{'note':'模拟承运差异核实，批准剩余在途按损耗结案','write_off_remaining':True})
            return row

        await login('admin')
        if 'period' not in state:
            now=datetime.now(ZoneInfo('Asia/Shanghai'))
            state['period']=now.strftime('%Y-%m');state['next_period']=(now.replace(day=28)+timedelta(days=4)).strftime('%Y-%m');save()
        period,next_period=state['period'],state['next_period']
        customer=await step('customer','/customers',{'display_name':'周女士（模拟·组合售后）','contact':'','address':'演示市联合路 30 号'})
        products={k:sid('phase2-product-'+k) for k in ('router','phone','cable')}
        quantities={'router':10,'phone':2,'cable':20}
        po=await step('stock/purchase','/inventory/purchases',{'request_key':'phase3-stock','supplier_id':sid('phase2-supplier-1'),
            'lines':[{'product_id':products[k],'quantity':q,'unit_cost':{'router':'185.00','phone':'780.00','cable':'8.00'}[k]} for k,q in quantities.items()]})
        await step('stock/approve',f"/inventory/purchases/{po['id']}/approve",{})
        await step('stock/receive',f"/inventory/purchases/{po['id']}/receive",{'request_key':'phase3-receipt','lines':[
            {'line_id':line['id'],'quantity':line['quantity'],'serials':[] if line['product_id']==products['cable'] else [f'P3-{line["product_id"][:8]}-{i:03}' for i in range(line['quantity'])]} for line in po['lines']]})

        original=await order('部分退货',[('router',2)],customer['id']);await dispatch('部分退货',original)
        transaction=await step('return/transaction','/transactions',{'request_key':'phase3-return-transaction','customer_id':customer['id'],'title':'模拟·两台路由器交付后退一台','required':['SALE'],'order_ids':[original['id']]})
        earning=await earn('部分退货',original)
        first=(Decimal(earning['expected_amount'])/2).quantize(Decimal('.01'))
        await bill('first-bill',earning,str(first),period,False)
        half=(Decimal(earning['commission_amount'])/2).quantize(Decimal('.01'))
        await settle('first-settlement',earning,str(half),period)
        await bill('second-bill',earning,str(Decimal(earning['expected_amount'])-first),next_period)
        await settle('second-settlement',earning,str(Decimal(earning['commission_amount'])-half),next_period)
        returned=await aftersale('退回一台路由器',original,'RETURN_REFUND','279.00',1)
        source=await get('/sales/orders/'+original['id'])
        serial=next(a for a in source['payment']['allocations'] if a['product_id']==products['router'])['serials'][0]
        await step('return/receive',f"/aftersales/{returned['id']}/receive",{'note':'模拟设备外观及原序列号验收通过','lines':[{'line_id':original['lines'][0]['id'],'serials':[serial]}]})
        await step('return/refund',f"/aftersales/{returned['id']}/refund",{})
        await step('return/close',f"/aftersales/{returned['id']}/close",{'note':'退款已核实，原设备已归库，原收款和分期提成记录保留'})
        await bill('refund-bill',earning,'-27.90',next_period)

        replacement=await order('后续新购抵扣',[('phone',1)],customer['id']);await dispatch('后续新购抵扣',replacement)
        newearning=await earn('后续新购抵扣',replacement);await bill('offset-new-bill',newearning,newearning['expected_amount'],next_period)
        await settle('offset-settlement',newearning,str(Decimal(newearning['commission_amount'])-half),next_period)
        pending=await order('未交付取消',[('router',1)],customer['id'])
        cancel=await aftersale('未交付全额取消',pending,'CANCEL_UNSHIPPED','279.00',1)
        await step('cancel/refund',f"/aftersales/{cancel['id']}/refund",{})
        await step('cancel/close',f"/aftersales/{cancel['id']}/close",{'note':'模拟退款成功，设备预留释放，无虚构退库流水'})
        unknown=await order('退款结果待核对',[('cable',1)],customer['id']);await dispatch('退款结果待核对',unknown)
        unknown_case=await aftersale('模拟退款成功但返回超时',unknown,'REFUND_ONLY','5.00',scenario='SUCCESS_TIMEOUT')
        await step('unknown/refund',f"/aftersales/{unknown_case['id']}/refund",{})

        blocked=await order('安装现场受阻',[('router',1),('install',1)],customer['id']);await dispatch('安装现场受阻',blocked)
        job=await step('blocked/job','/installations',{'source_order_id':blocked['id'],'address':'演示市联合路 30 号','appointment_at':'2026-10-04T10:00:00+08:00'})
        await step('blocked/dispatch',f"/installations/{job['id']}/dispatch",{'installer_id':sid('INSTALLER')})
        for action in ('accept','collect','arrive'):
            await step('blocked/'+action,f"/installations/{job['id']}/transition",{'request_key':'phase3-blocked-'+action,'action':action,'note':'模拟现场处理',
                'materials':[{'product_id':products['cable'],'quantity':1}] if action=='collect' else []})
        await step('blocked/issue',f"/installations/{job['id']}/issue",{'note':'模拟现场无电，设备和耗材由原装维保管，待客户确认改约'})
        await step('blocked/transaction','/transactions',{'request_key':'phase3-blocked-tx','customer_id':customer['id'],'title':'模拟·设备已交付，现场安装受阻','required':['SALE','INSTALLATION'],'order_ids':[blocked['id']],'installation_ids':[job['id']]})

        service=await step('telecom/service','/service-sessions',{'category':'PLAN'})
        query=await step('telecom/query',f"/service-sessions/{service['service_id']}/account-query",{'number':'19900000014'})
        rec=await step('telecom/recommendation',f"/service-sessions/{service['service_id']}/recommendations",{'snapshot_id':query['snapshot_id'],'demand':{'intent':'REDUCE_COST','must_keep':['broadband']}})
        candidate=next(c for c in rec['candidates'] if c['monthly_fee']=='89.00')
        quality=await step('telecom/quality',f"/recommendations/{rec['recommendation_id']}/quality-checks",{'candidate_id':candidate['candidate_id']})
        await step('telecom/review',f"/quality-checks/{quality['quality_check_id']}/reviews",{'decision':'CONFIRM','reason':'模拟客户知悉资费、合约及宽带条件，人工复核演示'})
        acceptance=await step('telecom/acceptance','/acceptances',{'recommendation_id':rec['recommendation_id'],'candidate_id':candidate['candidate_id']},headers={'Idempotency-Key':'phase3-telecom-acceptance'})
        await step('telecom/confirm',f"/acceptances/{acceptance['acceptance_id']}/confirm",{'expected_version':acceptance['expected_version'],'quality_check_id':quality['quality_check_id']})
        await step('telecom/earning','/finance/accruals',{'source_type':'TELECOM','source_id':acceptance['acceptance_id']})
        reversal=await step('telecom/reversal','/reversals',{'request_key':'phase3-reversal','acceptance_id':acceptance['acceptance_id'],'reason':'模拟客户撤回套餐变更，恢复办理前账号事实','scenario':'SUCCESS_TIMEOUT'})
        await step('telecom/reversal-review',f"/reversals/{reversal['id']}/review",{'decision':'APPROVE','note':'模拟核对新受理保存的办理前快照'})
        await step('telecom/reversal-submit',f"/reversals/{reversal['id']}/submit",{})
        await step('telecom/reversal-reconcile',f"/reversals/{reversal['id']}/reconcile",{})
        telecom_source=await get('/service-sessions/'+service['service_id'])
        await step('telecom/transaction','/transactions',{'request_key':'phase3-telecom-tx','customer_id':telecom_source['customer_id'],'title':'模拟·通信成功后冲正，保留原成功记录','required':['TELECOM'],'acceptance_ids':[acceptance['acceptance_id']]})

        await transfer('设备调拨完成','router',2,2)
        await transfer('耗材短到待核查','cable',5,3)
        await transfer('耗材短到核损结案','cable',3,2,True)
        await login('admin')
        stock=next(s for s in (await get('/inventory/stock'))['items'] if s['product_id']==products['cable'])
        count=await step('count','/inventory/counts',{'request_key':'phase3-count','product_id':products['cable'],'actual_quantity':stock['quantity']-1,'note':'模拟盘亏一条网线，等待负责人复核'})
        await step('count/review',f"/inventory/counts/{count['id']}/review",{'decision':'APPROVE','note':'模拟复核损耗证据，仅以差异流水调整库存'})
        case=await step('difference/open','/finance/cases',{'request_key':'phase3-open-case','earning_id':newearning['id'],'owner_id':sid('FINANCE'),
            'kind':'ADJUSTMENT','proposed_delta':'2.00','reason':'模拟运营方额外补发两元，待负责人审批','due_at':'2026-10-06T12:00:00+08:00'})
        await login('admin2')
        second=await step('second/customer','/customers',{'display_name':'赵先生（模拟·二店购机）','address':'演示市二店路 2 号','contact':''})
        second_order=await order('二店销售',[('router',1)],second['id'],True);await dispatch('二店销售',second_order)
        second_earning=await earn('二店销售',second_order);await bill('second-store-bill',second_earning,second_earning['expected_amount'],period)
        await settle('second-store-settlement',second_earning,second_earning['commission_amount'],period,True)
        state['complete']=True;save()
        print('Stage-three demo examples ready; unresolved refund and short delivery intentionally retained for review.')


if __name__=='__main__': asyncio.run(main())
